#!/usr/bin/env python3
"""SWE-bench Contributor Analyzer.

This script analyzes SWE-bench datasets to find instances where a specific GitHub
user has contributed, either as an author, commenter, or being mentioned in issues
and pull requests.

Datasets are automatically loaded from Hugging Face if not provided locally:
- princeton-nlp/SWE-bench
- princeton-nlp/SWE-bench_Verified
"""

import argparse
import configparser
import getpass
import json
import os
import sys
import time
from pathlib import Path

import keyring
import requests
from tqdm.auto import tqdm

# Constants
APP_NAME = "SWEBenchAnalyzer"
TOKEN_SERVICE = "github-token"
DATASETS = {
    "swe-bench": "princeton-nlp/SWE-bench",
    "swe-bench-verified": "princeton-nlp/SWE-bench_Verified",
}

# Configuration functions
def get_config():
    """Load configuration from file or create default."""
    config = configparser.ConfigParser()
    config_path = Path.home() / ".swe-bench-analyzer.ini"

    # Default configuration
    if not config_path.exists():
        config['General'] = {
            'username': '',
            'last_run': ''
        }
        config['Paths'] = {
            'cache_dir': '',
            'last_output': 'user_contributions.json'
        }
        config['Datasets'] = {
            'swe-bench': '',
            'swe-bench-verified': ''
        }
        save_config(config)
    else:
        config.read(config_path)

    # Ensure all sections exist
    for section in ['General', 'Paths', 'Datasets']:
        if section not in config:
            config[section] = {}

    return config

def save_config(config):
    """Save configuration to file."""
    config_path = Path.home() / ".swe-bench-analyzer.ini"
    with open(config_path, 'w') as f:
        config.write(f)

def get_github_token():
    """Get GitHub token from keyring or prompt user."""
    try:
        token = keyring.get_password(APP_NAME, TOKEN_SERVICE)
        if token:
            return token
    except Exception:
        pass

    # If no token or error, prompt user
    token = getpass.getpass("Enter your GitHub API token (input will be hidden): ")
    if token:
        try:
            keyring.set_password(APP_NAME, TOKEN_SERVICE, token)
        except Exception as e:
            print(f"Warning: Could not save token to keyring: {e}")

    return token

def download_huggingface_dataset(dataset_name, cache_dir=None):
    """Download dataset from Hugging Face."""
    try:
        from datasets import load_dataset

        print(f"Downloading dataset {dataset_name} from Hugging Face...")

        # Map shorthand names to full HF paths
        hf_dataset_name = DATASETS.get(dataset_name.lower(), dataset_name)

        # Create cache directory if needed
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

        # Load from Hugging Face
        dataset = load_dataset(hf_dataset_name, cache_dir=cache_dir)

        # Convert to our format
        instances = []
        for split in dataset:
            if split in dataset:
                for item in dataset[split]:
                    instances.append(item)

        print(f"Successfully loaded {len(instances)} instances from {hf_dataset_name}")

        # Save the cache location in config
        config = get_config()
        config['Datasets'][dataset_name.lower()] = str(Path(cache_dir) / dataset_name.lower() if cache_dir else "")
        save_config(config)

        return instances

    except ImportError:
        print("datasets library not found. Please install it using: pip install datasets")
        print("Then run the script again.")
        return []

    except Exception as e:
        print(f"Error downloading dataset from Hugging Face: {e}")
        print("Please check your internet connection and try again.")
        return []

def load_dataset(file_path_or_name, cache_dir=None):
    """Load the dataset from a JSON file or download from Hugging Face."""
    # Check if it's a local file
    path = Path(file_path_or_name)
    if path.exists() and path.is_file():
        try:
            with open(path, 'r') as f:
                # Check format (list or dict)
                first_char = f.read(1)
                f.seek(0)

                if first_char == '[':
                    # JSON array
                    return json.load(f)
                elif first_char == '{':
                    # JSON object
                    data = json.load(f)
                    if 'instances' in data:
                        return data['instances']
                    else:
                        # Return as list of instances
                        return [{"instance_id": k, **v} for k, v in data.items()]
                else:
                    # Try JSONL format
                    return [json.loads(line) for line in f if line.strip()]
        except Exception as e:
            print(f"Error loading dataset from file: {e}")
            return []
    else:
        # Not a local file, try to download from Hugging Face
        return download_huggingface_dataset(file_path_or_name, cache_dir)

def load_saved_results(file_path):
    """Load previously saved analysis results."""
    try:
        with open(file_path, 'r') as f:
            results = json.load(f)
        print(f"Loaded {len(results)} saved results from {file_path}")
        return results
    except Exception as e:
        print(f"Error loading saved results: {e}")
        return []

def print_results_summary(results):
    """Print a summary of the analysis results."""
    if not results:
        print("No contributions found.")
        return

    print(f"\nFound {len(results)} instances with contributions:")

    # Group by repository
    repos = {}
    for result in results:
        repo = result.get('repo', 'Unknown')
        if repo not in repos:
            repos[repo] = []
        repos[repo].append(result)

    # Print summary by repository
    for repo, items in sorted(repos.items()):
        print(f"\n- {repo}: {len(items)} contributions")

        # Group by contribution type
        types = {}
        for item in items:
            for ctype in item.get('contribution_types', []):
                if ctype not in types:
                    types[ctype] = 0
                types[ctype] += 1

        # Print contribution types
        for ctype, count in sorted(types.items()):
            print(f"  - {ctype}: {count}")

    # Print detailed list
    print("\nDetailed contributions:")
    for idx, result in enumerate(results, 1):
        print(f"{idx}. {result['repo']} - {', '.join(result['contribution_types'])}")
        print(f"   Title: {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Created: {result['created_at']}")
        print()

def extract_repo_and_number(instance_id, repo=None):
    """Extract repository and PR/issue number from instance_id."""
    if repo:
        # If repo is provided separately, just extract the number
        parts = instance_id.split('-')
        if len(parts) >= 2:
            number = parts[-1]
            return repo, number

    # Format example: "sympy__sympy-22914"
    try:
        parts = instance_id.split('-', 1)
        repo_part = parts[0].replace('__', '/')
        number = parts[1]
        return repo_part, number
    except IndexError:
        return None, None

def check_text_for_username(text, username):
    """Check if username appears in text."""
    if not text or not username:
        return False

    # Convert to lowercase for case-insensitive matching
    text_lower = text.lower()
    username_lower = username.lower()

    # Common patterns for username mentions
    patterns = [
        f"@{username_lower}",  # @username mention
        f"{username_lower}:",  # Username: (common in comments)
        f"by {username_lower}",  # Attribution
        f"from {username_lower}",  # Attribution
        f"author: {username_lower}",  # Explicit authorship
    ]

    for pattern in patterns:
        if pattern in text_lower:
            return True

    return False

def fetch_github_issue_or_pr(repo, number, token, retries=3):
    """Fetch a GitHub issue or PR and its comments."""
    base_url = f"https://api.github.com/repos/{repo}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    def make_request(url, retry_count=0):
        """Make a GitHub API request with rate limit handling."""
        try:
            response = requests.get(url, headers=headers)

            # Check for rate limiting
            if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
                remaining = int(response.headers['X-RateLimit-Remaining'])
                if remaining == 0 and retry_count < retries:
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    wait_time = max(reset_time - time.time(), 0) + 1
                    print(f"Rate limit hit. Waiting {wait_time:.0f} seconds...")
                    time.sleep(wait_time)
                    return make_request(url, retry_count + 1)

            return response
        except requests.RequestException as e:
            if retry_count < retries:
                print(f"Request error: {e}. Retrying in 5 seconds...")
                time.sleep(5)
                return make_request(url, retry_count + 1)
            else:
                print(f"Failed after {retries} retries: {e}")
                return None

    # Try as a PR first
    pr_url = f"{base_url}/pulls/{number}"
    pr_response = make_request(pr_url)
    is_pr = pr_response and pr_response.status_code == 200

    if is_pr:
        item = pr_response.json()
    else:
        # If not a PR, try as an issue
        issue_url = f"{base_url}/issues/{number}"
        issue_response = make_request(issue_url)

        if not issue_response or issue_response.status_code != 200:
            status = issue_response.status_code if issue_response else "No response"
            print(f"Error fetching {issue_url}: {status}")
            return None, []

        item = issue_response.json()

    # Fetch comments
    comments = []
    if 'comments_url' in item and item['comments'] > 0:
        comments_response = make_request(item['comments_url'])
        if comments_response and comments_response.status_code == 200:
            comments = comments_response.json()

    # For PRs, also fetch review comments
    review_comments = []
    if is_pr and 'review_comments_url' in item and item.get('review_comments', 0) > 0:
        review_response = make_request(item['review_comments_url'])
        if review_response and review_response.status_code == 200:
            review_comments = review_response.json()

    all_comments = comments + review_comments

    return item, all_comments

def check_user_contribution(username, item, comments):
    """Check if the user contributed to this issue/PR."""
    if not item:
        return []

    contribution_types = []

    # Check if the user created the issue/PR
    if item.get('user', {}).get('login') == username:
        contribution_types.append("author")

    # Check if the user is assigned
    for assignee in item.get('assignees', []):
        if assignee.get('login') == username:
            contribution_types.append("assignee")
            break

    # Check if the user is mentioned in the body
    body = item.get('body', '')
    if body and check_text_for_username(body, username):
        contribution_types.append("mentioned_in_body")

    # Check comments
    for comment in comments:
        if comment is None:
            continue
            
        if comment.get('user', {}).get('login') == username:
            contribution_types.append("commenter")
            break

        # Check if mentioned in comments
        comment_body = comment.get('body', '')
        if comment_body and check_text_for_username(comment_body, username):
            contribution_types.append("mentioned_in_comment")
            break

    return contribution_types

def analyze_dataset_offline(dataset, username, output_file):
    """Analyze dataset without GitHub API (check dataset fields only)."""
    results = []

    for instance in tqdm(dataset, desc="Analyzing dataset"):
        contribution_found = False
        contribution_types = []

        # Check problem_statement
        if 'problem_statement' in instance and instance['problem_statement']:
            if check_text_for_username(instance['problem_statement'], username):
                contribution_types.append("mentioned_in_problem")
                contribution_found = True

        # Check hints_text
        if 'hints_text' in instance and instance['hints_text']:
            if check_text_for_username(instance['hints_text'], username):
                contribution_types.append("mentioned_in_hints")
                contribution_found = True

        if contribution_found:
            # Extract repo and number
            repo = instance.get('repo')
            instance_id = instance['instance_id']
            repo_name, number = extract_repo_and_number(instance_id, repo)

            # Get title from problem statement
            title = "Unknown"
            if 'problem_statement' in instance and instance['problem_statement']:
                problem_lines = instance['problem_statement'].split('\n')
                for line in problem_lines:
                    line = line.strip()
                    if line:
                        # Remove "Title: " prefix if present
                        if line.startswith("Title:"):
                            title = line[6:].strip()
                        else:
                            title = line
                        break

            # Create GitHub URL
            url = f"https://github.com/{repo_name}/issues/{number}" if repo_name and number else "Unknown"

            results.append({
                'instance_id': instance_id,
                'repo': repo_name or instance.get('repo', 'Unknown'),
                'contribution_types': contribution_types,
                'title': title,
                'url': url,
                'created_at': instance.get('created_at', 'Unknown'),
                'dataset_info': {
                    'problem_statement': instance.get('problem_statement', ''),
                    'hints_text': instance.get('hints_text', '')
                }
            })

    # Only save if output_file is specified
    if output_file:
        output_data = {
            "metadata": {
                "username": username,
                "analysis_mode": "offline",
                "date_analyzed": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(results)
            },
            "results": results
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

    return results

def analyze_dataset_with_github(dataset, username, token, output_file):
    """Analyze dataset using GitHub API for thorough checking."""
    results = []

    for instance in tqdm(dataset, desc="Analyzing with GitHub API"):
        # Extract repository and issue/PR number
        repo = instance.get('repo')
        instance_id = instance['instance_id']
        repo_name, number = extract_repo_and_number(instance_id, repo)

        if not repo_name or not number:
            print(f"Could not parse repository/number from: {instance_id}")
            continue

        # Fetch from GitHub API
        item, comments = fetch_github_issue_or_pr(repo_name, number, token)

        # Check contributions
        contribution_types = check_user_contribution(username, item, comments)

        # Also check dataset fields
        if 'problem_statement' in instance and check_text_for_username(instance['problem_statement'], username):
            contribution_types.append("mentioned_in_problem")

        if 'hints_text' in instance and check_text_for_username(instance['hints_text'], username):
            contribution_types.append("mentioned_in_hints")

        # If any contributions found, add to results
        if contribution_types:
            results.append({
                'instance_id': instance_id,
                'repo': repo_name,
                'contribution_types': list(set(contribution_types)),  # Remove duplicates
                'title': item.get('title', 'Unknown') if item else "Unknown",
                'url': item.get('html_url', f"https://github.com/{repo_name}/issues/{number}") if item else f"https://github.com/{repo_name}/issues/{number}",
                'created_at': item.get('created_at', instance.get('created_at', 'Unknown')) if item else instance.get('created_at', 'Unknown'),
                'dataset_info': {
                    'problem_statement': instance.get('problem_statement', ''),
                    'hints_text': instance.get('hints_text', '')
                },
                'github_info': {
                    'issue_found': item is not None,
                    'comment_count': len(comments) if comments else 0
                }
            })

        # Sleep to avoid rate limits
        time.sleep(0.2)

    # Only save if output_file is specified
    if output_file:
        output_data = {
            "metadata": {
                "username": username,
                "analysis_mode": "github_api",
                "date_analyzed": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(results)
            },
            "results": results
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

    return results

def analyze_multiple_datasets(datasets, username, token, output_file, use_github):
    """Analyze multiple datasets and combine the results."""
    all_results = []

    for dataset_name, dataset in datasets.items():
        print(f"Analyzing dataset: {dataset_name}")

        if use_github:
            if not token:
                print("Error: GitHub API token is required for GitHub API mode")
                print("Run with --no-github flag for offline analysis, or provide a token")
                continue

            results = analyze_dataset_with_github(dataset, username, token, None)  # Don't save individual results
        else:
            results = analyze_dataset_offline(dataset, username, None)  # Don't save individual results

        # Add dataset info to each result
        for result in results:
            result['dataset'] = dataset_name

        all_results.extend(results)
        print(f"Found {len(results)} contributions in {dataset_name}")

    # Save combined results if output file is specified
    if output_file and all_results:
        output_data = {
            "metadata": {
                "username": username,
                "analysis_mode": "github_api" if use_github else "offline",
                "date_analyzed": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(all_results),
                "datasets": list(datasets.keys())
            },
            "results": all_results
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

    return all_results

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Analyze SWE-bench datasets for user contributions')
    parser.add_argument('--username', help='GitHub username to check')
    parser.add_argument('--dataset', help='Path to dataset or dataset name (swe-bench, swe-bench-verified, both)')
    parser.add_argument('--output', help='Output file path')
    parser.add_argument('--token', help='GitHub API token (optional, will use cached or prompt)')
    parser.add_argument('--no-github', action='store_true', help='Disable GitHub API analysis (offline mode only)')
    parser.add_argument('--cache-dir', help='Directory to cache downloaded datasets')
    parser.add_argument('--load-results', help='Load previously saved results instead of running analysis')
    parser.add_argument('--refresh-token', action='store_true', help='Force refresh of GitHub token')

    args = parser.parse_args()

    # Load configuration
    config = get_config()

    # If loading saved results, skip straight to results display
    if args.load_results:
        results = load_saved_results(args.load_results)
        print_results_summary(results)
        return

    # Get cache directory from args or config
    cache_dir = args.cache_dir or config['Paths'].get('cache_dir')
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    # Get username from args or config, or prompt
    username = args.username or config['General'].get('username')
    if not username:
        username = input("Enter your GitHub username: ")
        # Save for future use
        config['General']['username'] = username
        save_config(config)

    # Get output file from args, config, or default
    output_file = args.output or config['Paths'].get('last_output') or 'user_contributions.json'
    config['Paths']['last_output'] = output_file
    save_config(config)

    # Determine which dataset(s) to use
    datasets_to_analyze = {}

    if args.dataset:
        dataset_choice = args.dataset.lower()
    else:
        # If no dataset specified, default to both
        dataset_choice = 'both'

    # Load dataset(s)
    if dataset_choice == 'both':
        print("Analyzing both SWE-bench and SWE-bench-verified datasets")
        # Load both datasets
        swe_bench = load_dataset('swe-bench', cache_dir)
        swe_bench_verified = load_dataset('swe-bench-verified', cache_dir)

        if swe_bench:
            datasets_to_analyze['swe-bench'] = swe_bench
        if swe_bench_verified:
            datasets_to_analyze['swe-bench-verified'] = swe_bench_verified

    else:
        # Load single dataset
        dataset = load_dataset(dataset_choice, cache_dir)
        if dataset:
            datasets_to_analyze[dataset_choice] = dataset

    if not datasets_to_analyze:
        print("No datasets to analyze. Please check your dataset names or paths.")
        return

    # Determine whether to use GitHub API
    use_github = not args.no_github  # Default is to use GitHub

    # Get GitHub token if needed
    token = None
    if use_github:
        if args.refresh_token:
            # Force refresh token
            token = getpass.getpass("Enter your GitHub API token (input will be hidden): ")
            try:
                keyring.set_password(APP_NAME, TOKEN_SERVICE, token)
                print("Token updated successfully")
            except Exception as e:
                print(f"Warning: Could not save token to keyring: {e}")
        elif args.token:
            # Use provided token
            token = args.token
            # Save for future use if possible
            try:
                keyring.set_password(APP_NAME, TOKEN_SERVICE, token)
                print("Token saved for future use")
            except Exception as e:
                print(f"Warning: Could not save token to keyring: {e}")
        else:
            # Try to get from keyring
            token = get_github_token()

    # Analyze datasets
    print(f"Starting analysis for username: {username}")
    print(f"Using {'GitHub API' if use_github else 'offline'} mode")

    # For multiple datasets
    if len(datasets_to_analyze) > 1:
        results = analyze_multiple_datasets(datasets_to_analyze, username, token, output_file, use_github)
    else:
        # For a single dataset
        dataset_name = next(iter(datasets_to_analyze.keys()))
        dataset = datasets_to_analyze[dataset_name]

        print(f"Analyzing dataset: {dataset_name}")
        if use_github:
            if not token:
                print("Error: GitHub API token is required for GitHub API mode")
                print("Run with --no-github flag for offline analysis, or provide a token")
                return

            results = analyze_dataset_with_github(dataset, username, token, output_file)
        else:
            results = analyze_dataset_offline(dataset, username, output_file)

    # Print summary
    print_results_summary(results)

    print(f"\nResults saved to {output_file}")
    print(f"You can view these results later without re-analyzing by using: --load-results {output_file}")

    # Update config with the latest successful run details
    config['General']['last_run'] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_config(config)

if __name__ == "__main__":
    main()
