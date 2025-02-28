#!/usr/bin/env python3
"""SWE-bench Contributor Analyzer.

This script analyzes SWE-bench datasets to find instances where a specific GitHub
user has contributed in ways that would make it into the SWE-bench dataset:
1. As the original issue author
2. As a commenter whose comments became part of the "hints" in the dataset
3. As the pull request author

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
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

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
GITHUB_CACHE_DIR = Path.home() / ".swe-bench-cache" / "github"
CACHE_EXPIRY_DAYS = 7  # Cache expiry in days
REQUEST_TIMEOUT = 10  # Default timeout for GitHub requests in seconds

# Cache functions
def get_cache_key(repo, number):
    """Generate a unique cache key for a GitHub issue/PR."""
    cache_key = f"{repo}_{number}"
    return hashlib.md5(cache_key.encode()).hexdigest()

def get_cache_path(repo, number):
    """Get the file path for a cached GitHub issue/PR."""
    cache_key = get_cache_key(repo, number)
    return GITHUB_CACHE_DIR / f"{cache_key}.json"

def load_from_cache(repo, number):
    """Load GitHub data from cache if available and not expired."""
    cache_path = get_cache_path(repo, number)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r') as f:
            cached_data = json.load(f)

        # Check if cache is expired
        cached_time = datetime.fromisoformat(cached_data.get('cached_at', '2000-01-01T00:00:00'))
        if datetime.now() - cached_time > timedelta(days=CACHE_EXPIRY_DAYS):
            return None

        return cached_data.get('data')
    except (json.JSONDecodeError, KeyError, ValueError):
        # Invalid cache, ignore it
        return None

def save_to_cache(repo, number, data):
    """Save GitHub data to cache."""
    if not data:
        return

    # Create cache directory if it doesn't exist
    GITHUB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_path = get_cache_path(repo, number)
    cached_data = {
        'cached_at': datetime.now().isoformat(),
        'repo': repo,
        'number': number,
        'data': data
    }

    with open(cache_path, 'w') as f:
        json.dump(cached_data, f)

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
            'github_cache_dir': str(GITHUB_CACHE_DIR),
            'last_output': 'user_contributions.json'
        }
        config['Datasets'] = {
            'swe-bench': '',
            'swe-bench-verified': ''
        }
        config['Cache'] = {
            'github_expiry_days': str(CACHE_EXPIRY_DAYS),
            'enabled': 'true'
        }
        config['Performance'] = {
            'request_timeout': str(REQUEST_TIMEOUT)
        }
        save_config(config)
    else:
        config.read(config_path)

    # Ensure all sections exist
    for section in ['General', 'Paths', 'Datasets', 'Cache', 'Performance']:
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

def fetch_github_issue_or_pr(repo, number, token, retries=3, use_cache=True, timeout=None):
    """Fetch a GitHub issue or PR and its comments with caching support."""
    # Check config for cache settings
    config = get_config()
    cache_enabled = config['Cache'].get('enabled', 'true').lower() == 'true'
    cache_expiry = int(config['Cache'].get('github_expiry_days', str(CACHE_EXPIRY_DAYS)))

    # Get request timeout if not provided
    if timeout is None:
        timeout = int(config['Performance'].get('request_timeout', str(REQUEST_TIMEOUT)))

    # Override GITHUB_CACHE_DIR if specified in config
    github_cache_dir = Path(config['Paths'].get('github_cache_dir', str(GITHUB_CACHE_DIR)))

    # Use cache if enabled and requested
    if cache_enabled and use_cache:
        cached_data = load_from_cache(repo, number)
        if cached_data:
            return cached_data.get('item'), cached_data.get('comments', [])

    base_url = f"https://api.github.com/repos/{repo}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    def make_request(url, retry_count=0):
        """Make a GitHub API request with rate limit handling."""
        try:
            response = requests.get(url, headers=headers, timeout=timeout)

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

    # Cache the results if cache is enabled
    if cache_enabled and use_cache:
        cache_data = {
            'item': item,
            'comments': all_comments
        }
        save_to_cache(repo, number, cache_data)

    return item, all_comments



def check_user_contribution(username, item, comments):
    """Check if the user contributed to this issue/PR in a way that appears in the SWE-bench dataset.

    Only checks for contributions that would make it into the SWE-bench dataset:
    1. User is the original issue author
    2. User made comments that became part of the "hints" in the dataset
    3. User authored the pull request
    """
    if not item:
        return []

    contribution_types = []

    # Check if the user created the issue/PR
    if item.get('user', {}).get('login') == username:
        contribution_types.append("author")

    # For PRs, check if the user is the PR author
    if 'pull_request' in item and item.get('user', {}).get('login') == username:
        contribution_types.append("pr_author")

    # Check comments - only those that might end up in the hints
    for comment in comments:
        if comment is None:
            continue

        # Skip comments with None 'user' field
        if comment.get('user') is None:
            continue

        if comment.get('user', {}).get('login') == username:
            contribution_types.append("commenter")
            break

    return contribution_types

def analyze_dataset_offline(dataset, username, output_file):
    """Analyze dataset without GitHub API (check dataset fields only)."""
    results = []

    for instance in tqdm(dataset, desc="Analyzing dataset"):
        contribution_types = []

        # Check hints_text - this is the key component for SWE-bench contributions
        if 'hints_text' in instance and instance['hints_text']:
            if check_text_for_username(instance['hints_text'], username):
                contribution_types.append("mentioned_in_hints")

        if contribution_types:
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
    """Analyze dataset using GitHub API sequentially."""
    results = []
    cache_hits = 0
    cache_misses = 0
    start_time = time.time()

    # Get cache and performance configuration
    config = get_config()
    use_cache = config['Cache'].get('enabled', 'true').lower() == 'true'
    timeout = int(config['Performance'].get('request_timeout', str(REQUEST_TIMEOUT)))

    # Process each instance sequentially
    for instance in tqdm(dataset, desc="Analyzing with GitHub API"):
        # Extract repository and issue/PR number
        repo = instance.get('repo')
        instance_id = instance['instance_id']
        repo_name, number = extract_repo_and_number(instance_id, repo)

        if not repo_name or not number:
            print(f"Could not parse repository/number from: {instance_id}")
            continue

        # Check if data exists in cache before API call
        cached_data = None
        if use_cache:
            cached_data = load_from_cache(repo_name, number)

        # Track cache hits/misses
        if cached_data is not None:
            cache_hits += 1
            item, comments = cached_data.get('item'), cached_data.get('comments', [])
        else:
            cache_misses += 1
            # Fetch from GitHub API
            item, comments = fetch_github_issue_or_pr(repo_name, number, token, use_cache=use_cache, timeout=timeout)

        # Check GitHub API contributions
        contribution_types = check_user_contribution(username, item, comments)

        # Check if user is mentioned in the dataset hints
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
                    'comment_count': len(comments) if comments else 0,
                    'from_cache': cached_data is not None
                }
            })

        # Sleep to avoid rate limits (only when making API requests)
        if cached_data is None and use_cache:
            time.sleep(0.2)

    # Calculate elapsed time
    elapsed_time = time.time() - start_time

    # Report cache statistics
    cache_total = cache_hits + cache_misses
    cache_hit_rate = (cache_hits / cache_total * 100) if cache_total > 0 else 0

    print(f"\nGitHub API analysis completed in {elapsed_time:.2f} seconds")
    print(f"GitHub API cache statistics:")
    print(f"  Cache enabled: {use_cache}")
    print(f"  Total requests: {cache_total}")
    print(f"  Cache hits: {cache_hits} ({cache_hit_rate:.1f}%)")
    print(f"  Cache misses: {cache_misses}")

    # Only save if output_file is specified
    if output_file:
        output_data = {
            "metadata": {
                "username": username,
                "analysis_mode": "github_api",
                "date_analyzed": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(results),
                "performance": {
                    "elapsed_seconds": elapsed_time
                },
                "cache_stats": {
                    "enabled": use_cache,
                    "hits": cache_hits,
                    "misses": cache_misses,
                    "hit_rate": f"{cache_hit_rate:.1f}%"
                }
            },
            "results": results
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

    return results

def analyze_multiple_datasets(datasets, username, token, output_file, use_github):
    """Analyze multiple datasets and combine the results."""
    all_results = []
    total_cache_hits = 0
    total_cache_misses = 0

    # Get cache configuration
    config = get_config()
    use_cache = config['Cache'].get('enabled', 'true').lower() == 'true'

    for dataset_name, dataset in datasets.items():
        print(f"Analyzing dataset: {dataset_name}")

        if use_github:
            if not token:
                print("Error: GitHub API token is required for GitHub API mode")
                print("Run with --no-github flag for offline analysis, or provide a token")
                continue

            results = analyze_dataset_with_github(dataset, username, token, None)  # Don't save individual results

            # Count the number of results with from_cache flag
            cache_hits_in_dataset = sum(1 for r in results if r.get('github_info', {}).get('from_cache', False))
            cache_misses_in_dataset = sum(1 for r in results if not r.get('github_info', {}).get('from_cache', False))

            total_cache_hits += cache_hits_in_dataset
            total_cache_misses += cache_misses_in_dataset
        else:
            results = analyze_dataset_offline(dataset, username, None)  # Don't save individual results

        # Add dataset info to each result
        for result in results:
            result['dataset'] = dataset_name

        all_results.extend(results)
        print(f"Found {len(results)} contributions in {dataset_name}")

    # Report combined cache statistics
    if use_github and use_cache:
        cache_total = total_cache_hits + total_cache_misses
        cache_hit_rate = (total_cache_hits / cache_total * 100) if cache_total > 0 else 0
        print(f"\nCombined GitHub API cache statistics:")
        print(f"  Total requests: {cache_total}")
        print(f"  Cache hits: {total_cache_hits} ({cache_hit_rate:.1f}%)")
        print(f"  Cache misses: {total_cache_misses}")

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

        # Add cache stats if using GitHub API
        if use_github and use_cache:
            output_data["metadata"]["cache_stats"] = {
                "enabled": use_cache,
                "hits": total_cache_hits,
                "misses": total_cache_misses,
                "hit_rate": f"{cache_hit_rate:.1f}%"
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
    parser.add_argument('--github-cache-dir', help='Directory to cache GitHub API responses')
    parser.add_argument('--no-cache', action='store_true', help='Disable GitHub API response caching')
    parser.add_argument('--clear-cache', action='store_true', help='Clear GitHub API response cache before running')
    parser.add_argument('--cache-expiry', type=int, help='Number of days after which to expire cached GitHub data')
    parser.add_argument('--load-results', help='Load previously saved results instead of running analysis')
    parser.add_argument('--refresh-token', action='store_true', help='Force refresh of GitHub token')
    parser.add_argument('--timeout', type=int, help='Timeout in seconds for API requests')

    args = parser.parse_args()

    # Load configuration
    config = get_config()

    # If loading saved results, skip straight to results display
    if args.load_results:
        results = load_saved_results(args.load_results)
        print_results_summary(results)
        return

    # Handle cache configuration
    if args.github_cache_dir:
        config['Paths']['github_cache_dir'] = args.github_cache_dir

    if args.cache_expiry:
        config['Cache']['github_expiry_days'] = str(args.cache_expiry)

    if args.no_cache:
        config['Cache']['enabled'] = 'false'

    # Handle performance configuration
    if args.timeout:
        config['Performance']['request_timeout'] = str(args.timeout)

    # Clear GitHub cache if requested
    if args.clear_cache:
        github_cache_dir = Path(config['Paths'].get('github_cache_dir', str(GITHUB_CACHE_DIR)))
        if github_cache_dir.exists():
            print(f"Clearing GitHub cache at {github_cache_dir}")
            import shutil
            shutil.rmtree(github_cache_dir)
            os.makedirs(github_cache_dir, exist_ok=True)

    # Save updated configuration
    save_config(config)

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

    # Set up cache directory
    github_cache_dir = Path(config['Paths'].get('github_cache_dir', str(GITHUB_CACHE_DIR)))
    if use_github and config['Cache'].get('enabled', 'true').lower() == 'true':
        os.makedirs(github_cache_dir, exist_ok=True)
        print(f"GitHub API cache directory: {github_cache_dir}")
        print(f"Cache expiry: {config['Cache'].get('github_expiry_days', str(CACHE_EXPIRY_DAYS))} days")

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

    # If using GitHub API, show performance settings
    if use_github:
        timeout = int(config['Performance'].get('request_timeout', str(REQUEST_TIMEOUT)))
        print(f"Performance settings:")
        print(f"  Request timeout: {timeout} seconds")

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
