# SWE-bench Contributor Analyzer

A tool for analyzing the SWE-bench and SWE-bench-verified datasets to identify GitHub issues and pull requests that you have contributed to.

## Overview

This script helps you find instances in the SWE-bench datasets where you have contributed as an author, commenter, assignee, or are mentioned in issues/PRs. It works with both the full SWE-bench dataset and the human-verified subset.

The analyzer can operate in two modes:
- **Offline mode**: Scans the dataset files directly for mentions of your username
- **GitHub API mode** (default): Makes API calls to GitHub to check for your contributions in more detail

## Features

- **Automatic dataset downloading** from Hugging Face
- **Secure credential storage** using your system's keyring
- **Configuration caching** for streamlined repeat usage
- **GitHub API response caching** to avoid rate limits and speed up repeat analyses
- **Comprehensive analysis** across both SWE-bench datasets
- **Detailed reporting** with contribution breakdowns by repository and type
- **Results caching** for viewing previous analyses without rerunning

## Installation

### Prerequisites

- Python 3.6+
- Required packages:

```bash
pip install requests tqdm keyring configparser
```

For dataset downloading:

```bash
pip install datasets
```

### Setup

1. Clone or download this script
2. Make it executable (optional):

```bash
chmod +x swebench_analyzer.py
```

## Usage

### Basic Usage

For first-time use, simply run:

```bash
python swebench_analyzer.py
```

The script will:
1. Prompt for your GitHub username
2. Securely ask for a GitHub API token
3. Download both SWE-bench datasets from Hugging Face
4. Analyze them using the GitHub API
5. Save the results to `user_contributions.json`

### Command Line Options

```
usage: swebench_analyzer.py [-h] [--username USERNAME] [--dataset DATASET]
                           [--output OUTPUT] [--token TOKEN] [--no-github]
                           [--cache-dir CACHE_DIR] [--github-cache-dir GITHUB_CACHE_DIR]
                           [--no-cache] [--clear-cache] [--cache-expiry CACHE_EXPIRY]
                           [--load-results LOAD_RESULTS] [--refresh-token]

Analyze SWE-bench datasets for user contributions

optional arguments:
  -h, --help            show this help message and exit
  --username USERNAME   GitHub username to check
  --dataset DATASET     Path to dataset or dataset name (swe-bench, swe-bench-verified, both)
  --output OUTPUT       Output file path
  --token TOKEN         GitHub API token (optional, will use cached or prompt)
  --no-github           Disable GitHub API analysis (offline mode only)
  --cache-dir CACHE_DIR
                        Directory to cache downloaded datasets
  --github-cache-dir GITHUB_CACHE_DIR
                        Directory to cache GitHub API responses
  --no-cache            Disable GitHub API response caching
  --clear-cache         Clear GitHub API response cache before running
  --cache-expiry CACHE_EXPIRY
                        Number of days after which to expire cached GitHub data
  --load-results LOAD_RESULTS
                        Load previously saved results instead of running analysis
  --refresh-token       Force refresh of GitHub token
```

### Examples

#### Analyze both datasets (default)

```bash
python swebench_analyzer.py --username your-github-username
```

#### Analyze only one dataset

```bash
python swebench_analyzer.py --dataset swe-bench-verified
```

#### Use offline mode (no GitHub API)

```bash
python swebench_analyzer.py --no-github
```

#### Load previously saved results

```bash
python swebench_analyzer.py --load-results user_contributions.json
```

#### Update your GitHub API token

```bash
python swebench_analyzer.py --refresh-token
```

#### Clear the GitHub API cache

```bash
python swebench_analyzer.py --clear-cache
```

#### Disable GitHub API caching

```bash
python swebench_analyzer.py --no-cache
```

#### Set custom GitHub API cache directory

```bash
python swebench_analyzer.py --github-cache-dir ~/.github-cache
```

#### Set custom cache expiration time

```bash
python swebench_analyzer.py --cache-expiry 14  # Cache valid for 14 days
```

## GitHub API Authentication

The script uses the GitHub API to check for your contributions. You'll need a Personal Access Token with repository read permissions.

To create a token:
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Generate a new token with repository read access permissions
3. Provide this token when prompted by the script

For security, the token is stored in your system's secure keyring and not in plain text.

## Configuration

The script automatically creates a configuration file at `~/.swe-bench-analyzer.ini` to store:

- Your GitHub username
- Dataset cache locations
- GitHub API cache settings
- Previous output file paths
- Most recent analysis timestamp
- Cache expiry configuration

This ensures that subsequent runs require minimal input from you.

The GitHub API cache is stored in `~/.swe-bench-cache/github` by default, but can be changed via the configuration file or command-line arguments.

## Output Format

Results are saved as a JSON file with the following structure:

```json
{
  "metadata": {
    "username": "your-username",
    "datasets": ["swe-bench", "swe-bench-verified"],
    "analysis_mode": "github_api",
    "date_analyzed": "2025-02-26 14:30:22",
    "count": 5,
    "cache_stats": {
      "enabled": true,
      "hits": 12,
      "misses": 3,
      "hit_rate": "80.0%"
    }
  },
  "results": [
    {
      "instance_id": "sympy__sympy-22914",
      "repo": "sympy/sympy",
      "contribution_types": ["author", "mentioned_in_problem"],
      "title": "Fix precision handling in Number class",
      "url": "https://github.com/sympy/sympy/issues/22914",
      "created_at": "2022-01-15T12:34:56Z",
      "dataset_name": "swe-bench",
      "dataset_info": {
        "problem_statement": "...",
        "hints_text": "..."
      },
      "github_info": {
        "issue_found": true,
        "comment_count": 5,
        "from_cache": true
      }
    },
    ...
  ]
}
```

## Troubleshooting

### GitHub API Caching

The script now caches GitHub API responses locally to:
1. Speed up subsequent runs
2. Reduce GitHub API rate limit usage
3. Allow offline analysis of previously fetched data

By default, cached responses expire after 7 days. You can:
- Change the expiry time with `--cache-expiry`
- Clear the cache with `--clear-cache`
- Disable caching with `--no-cache`
- Specify a custom cache location with `--github-cache-dir`

### Rate Limiting

If you encounter GitHub API rate limits, the script will:
1. First use cached responses if available
2. Automatically pause and wait for the rate limit to reset if needed
3. Report cache hit/miss statistics to help you optimize

### Missing Dependencies

If you're missing required packages, the script will show an error message with installation instructions.

### Dataset Download Issues

If the script can't download the datasets:
1. Check your internet connection
2. Try specifying a different cache directory with `--cache-dir`
3. Download the datasets manually and provide the file path with `--dataset`

## About the SWE-bench Datasets

- **SWE-bench**: 2,294 real-world GitHub Issue-Pull Request pairs from 12 popular Python repositories
- **SWE-bench-verified**: 500 human-validated samples from the full dataset

The datasets were designed to benchmark the ability of language models to solve software engineering tasks.

## License

This script is provided as-is under the MIT License.
