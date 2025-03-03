#!/usr/bin/env python3
"""
SWE-bench Contributor Visualizer

This script visualizes the results from the SWE-bench analyzer script,
showing contribution patterns, repository distributions, and other insights.
"""

import json
import argparse
import os
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import seaborn as sns
import pandas as pd
import numpy as np

def load_results(file_path):
    """Load results from the output JSON file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading results file: {e}")
        return None

def format_contribution_type(contribution_type):
    """Format contribution type to be more readable."""
    if not contribution_type:
        return "Unknown"

    # Handle prefixes like "issue_author" -> "Issue Author"
    if "_" in contribution_type:
        parts = contribution_type.split("_")
        return " ".join(part.capitalize() for part in parts)

    # Handle special types
    type_map = {
        "author": "PR Author",  # Renamed to be clearer
        "pr_author": "PR Author",
        "commenter": "Commenter",
        "dataset_commenter": "Dataset Comment Contributor",
        "mentioned_in_hints": "Mentioned in Hints",
        "mentioned_in_problem": "Mentioned in Problem",
        "issue_author": "Issue Author",
        "issue_commenter": "Issue Commenter",
        "issue_dataset_commenter": "Issue Comment in Dataset",
    }

    if contribution_type in type_map:
        return type_map[contribution_type]

    # Default: just capitalize
    return contribution_type.replace("_", " ").capitalize()

def prepare_data(data):
    """Process the raw data into formats suitable for visualization."""
    if not data or 'results' not in data:
        print("No results found in the data file.")
        return None

    results = data['results']
    metadata = data.get('metadata', {})

    # Extract username and datasets
    username = metadata.get('username', 'Unknown')
    datasets = metadata.get('datasets', ['unknown'])

    # Process results
    processed_data = {
        'username': username,
        'datasets': datasets,
        'total_contributions': len(results),
        'repos': [],
        'contribution_types': [],
        'dates': [],
        'repo_counts': Counter(),
        'type_counts': Counter(),
        'dataset_counts': Counter(),
        'repo_type_counts': defaultdict(Counter),
        'monthly_counts': defaultdict(int),
        'yearly_counts': defaultdict(int),
    }

    for result in results:
        repo = result.get('repo', 'Unknown')
        types = result.get('contribution_types', [])
        date_str = result.get('created_at', '')
        dataset = result.get('dataset', 'Unknown')

        processed_data['repos'].append(repo)
        processed_data['contribution_types'].extend(types)

        # Count by repository
        processed_data['repo_counts'][repo] += 1

        # Count by contribution type
        for contribution_type in types:
            processed_data['type_counts'][contribution_type] += 1
            processed_data['repo_type_counts'][repo][contribution_type] += 1

        # Count by dataset
        processed_data['dataset_counts'][dataset] += 1

        # Parse date if available
        if date_str:
            try:
                # Handle different date formats
                if 'T' in date_str:
                    date_obj = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
                else:
                    date_obj = datetime.strptime(date_str.split(' ')[0], '%Y-%m-%d')

                processed_data['dates'].append(date_obj)

                # Group by month and year for time series
                month_key = date_obj.strftime('%Y-%m')
                year_key = date_obj.strftime('%Y')
                processed_data['monthly_counts'][month_key] += 1
                processed_data['yearly_counts'][year_key] += 1
            except:
                # Skip dates that can't be parsed
                pass

        # Process related issues if present
        related_issues = result.get('github_info', {}).get('related_issues', [])
        if related_issues:
            # Could track these separately if needed
            pass

    return processed_data

def create_visualizations(processed_data, output_dir=None):
    """Create various visualizations from the processed data."""
    if not processed_data:
        return

    sns.set_style("whitegrid")

    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Set default figure size
    plt.rcParams['figure.figsize'] = (12, 8)

    # 1. Repository Distribution
    plt.figure()
    repos_df = pd.DataFrame({
        'Repository': list(processed_data['repo_counts'].keys()),
        'Contributions': list(processed_data['repo_counts'].values())
    })
    repos_df = repos_df.sort_values('Contributions', ascending=False)

    plt.figure(figsize=(12, 8))
    ax = sns.barplot(x='Contributions', y='Repository', data=repos_df.head(15))
    plt.title(f"Top Repositories with {processed_data['username']}'s Contributions")
    plt.tight_layout()

    if output_dir:
        plt.savefig(os.path.join(output_dir, 'top_repositories.png'))
        plt.close()
    else:
        plt.show()

    # 2. Contribution Types
    plt.figure()
    # Create a DataFrame with formatted type names
    types_df = pd.DataFrame({
        'Type': [format_contribution_type(t) for t in processed_data['type_counts'].keys()],
        'RawType': list(processed_data['type_counts'].keys()),
        'Count': list(processed_data['type_counts'].values())
    })
    types_df = types_df.sort_values('Count', ascending=False)

    colors = sns.color_palette("husl", len(types_df))
    plt.figure(figsize=(12, 10))

    # To prevent text overlap, use a pie chart with external labels
    wedges, texts, autotexts = plt.pie(
        types_df['Count'],
        labels=None,  # No direct labels
        autopct='%1.1f%%',
        colors=colors,
        startangle=90,
        pctdistance=0.85
    )

    # Draw a circle at the center to make it a donut chart (helps with readability)
    centre_circle = plt.Circle((0, 0), 0.70, fc='white')
    plt.gca().add_artist(centre_circle)

    # Add a legend instead of direct labels to avoid overlap
    plt.legend(
        wedges,
        types_df['Type'],
        title="Contribution Types",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1)
    )

    plt.axis('equal')
    plt.title(f"Contribution Types Distribution for {processed_data['username']}")

    if output_dir:
        # Add extra padding to ensure the legend fits when saved
        plt.tight_layout(pad=4.0, rect=[0, 0, 0.85, 1])
        plt.savefig(os.path.join(output_dir, 'contribution_types.png'), bbox_inches='tight')
        plt.close()
    else:
        plt.tight_layout(pad=4.0, rect=[0, 0, 0.85, 1])
        plt.show()

    # 3. Timeline of Contributions
    if processed_data['dates']:
        plt.figure(figsize=(14, 7))
        dates_df = pd.DataFrame({'Date': processed_data['dates']})
        dates_counts = dates_df.groupby(dates_df['Date'].dt.to_period('M')).size()

        # Convert period index to datetime for better plotting
        dates_df = pd.DataFrame({
            'Month': pd.PeriodIndex(dates_counts.index).to_timestamp(),
            'Contributions': dates_counts.values
        })

        plt.figure(figsize=(14, 7))
        ax = sns.lineplot(x='Month', y='Contributions', data=dates_df, marker='o')

        # Format the x-axis to show dates nicely
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=45)

        plt.title(f"Timeline of {processed_data['username']}'s Contributions")
        plt.tight_layout()

        if output_dir:
            plt.savefig(os.path.join(output_dir, 'contributions_timeline.png'))
            plt.close()
        else:
            plt.show()

    # 4. Dataset Distribution
    if len(processed_data['dataset_counts']) > 1:
        plt.figure(figsize=(10, 6))
        datasets_df = pd.DataFrame({
            'Dataset': list(processed_data['dataset_counts'].keys()),
            'Count': list(processed_data['dataset_counts'].values())
        })

        colors = sns.color_palette("Set2", len(datasets_df))
        plt.pie(datasets_df['Count'], labels=datasets_df['Dataset'], autopct='%1.1f%%',
                colors=colors, startangle=90)
        plt.axis('equal')
        plt.title(f"Distribution of Contributions Across Datasets")

        if output_dir:
            plt.savefig(os.path.join(output_dir, 'dataset_distribution.png'))
            plt.close()
        else:
            plt.show()

    # 5. Heatmap of Repos vs Contribution Types
    top_repos = [repo for repo, _ in processed_data['repo_counts'].most_common(10)]
    all_types = list(processed_data['type_counts'].keys())
    formatted_types = [format_contribution_type(t) for t in all_types]

    heatmap_data = []
    for repo in top_repos:
        repo_data = []
        for contrib_type in all_types:
            repo_data.append(processed_data['repo_type_counts'][repo][contrib_type])
        heatmap_data.append(repo_data)

    plt.figure(figsize=(12, 8))
    df_heatmap = pd.DataFrame(heatmap_data, index=top_repos, columns=formatted_types)

    # Replace zero values with NaN for better visualization
    df_heatmap = df_heatmap.replace(0, np.nan)

    ax = sns.heatmap(df_heatmap, annot=True, fmt='g', cmap='YlGnBu', linewidths=.5)
    plt.title(f"Contribution Types by Repository")
    plt.tight_layout()

    if output_dir:
        plt.savefig(os.path.join(output_dir, 'repo_type_heatmap.png'))
        plt.close()
    else:
        plt.show()

    # 6. Annual Contributions
    if processed_data['yearly_counts']:
        plt.figure(figsize=(12, 6))
        years_df = pd.DataFrame({
            'Year': list(processed_data['yearly_counts'].keys()),
            'Contributions': list(processed_data['yearly_counts'].values())
        })
        years_df = years_df.sort_values('Year')

        ax = sns.barplot(x='Year', y='Contributions', data=years_df)
        for i, row in years_df.iterrows():
            ax.text(i, row['Contributions'], row['Contributions'], ha='center')

        plt.title(f"Annual Contributions")
        plt.tight_layout()

        if output_dir:
            plt.savefig(os.path.join(output_dir, 'annual_contributions.png'))
            plt.close()
        else:
            plt.show()

    # Generate HTML report
    if output_dir:
        create_html_report(processed_data, output_dir)

def render_related_issues(result):
    """Render HTML for related issues section."""
    related_issues = result.get('github_info', {}).get('related_issues', [])
    if not related_issues:
        return ""

    html = """
    <h4>Related Issues</h4>
    <ul class="related-issues">
    """

    for issue in related_issues:
        issue_number = issue.get('number', '')
        issue_title = issue.get('title', 'Unknown Issue')
        issue_url = issue.get('url', '#')

        html += f"""
        <li><a href="{issue_url}" target="_blank">#{issue_number}: {issue_title}</a></li>
        """

    html += "</ul>"
    return html

def create_html_report(processed_data, output_dir):
    """Create an HTML report with all visualizations and data summaries."""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SWE-bench Analysis for {processed_data['username']}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                color: #333;
            }}
            h1, h2, h3 {{
                color: #2c3e50;
            }}
            #entries-count {{
                margin: 10px 0;
                font-weight: bold;
                color: #2c3e50;
            }}
            .container {{
                display: flex;
                flex-wrap: wrap;
                justify-content: space-between;
            }}
            .stat-box {{
                background-color: #f8f9fa;
                border-radius: 5px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                flex: 1 0 calc(25% - 20px);
                min-width: 200px;
                margin-right: 20px;
                text-align: center;
            }}
            .stat-box h2 {{
                font-size: 3em;
                margin: 0;
                color: #2980b9;
            }}
            .stat-box p {{
                font-size: 1.2em;
                color: #7f8c8d;
            }}
            .visualization {{
                margin-bottom: 40px;
            }}
            .visualization img {{
                max-width: 100%;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                border-radius: 5px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }}
            th {{
                background-color: #f2f2f2;
                font-weight: bold;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .filter-controls {{
                margin: 20px 0;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .filter-controls button {{
                margin-right: 10px;
                padding: 8px 16px;
                background-color: #2980b9;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }}
            .filter-controls button:hover {{
                background-color: #3498db;
            }}
            .filter-controls button.active {{
                background-color: #16a085;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 8px;
                margin-right: 5px;
                border-radius: 4px;
                font-size: 0.8em;
                font-weight: bold;
            }}
            .badge-verified {{
                background-color: #27ae60;
                color: white;
            }}
            .badge-standard {{
                background-color: #3498db;
                color: white;
            }}
            .related-issues {{
                margin-top: 10px;
                list-style-type: none;
                padding-left: 0;
            }}
            .related-issues li {{
                margin-bottom: 8px;
                padding: 5px 10px;
                background-color: #f8f9fa;
                border-radius: 4px;
                border-left: 3px solid #3498db;
            }}
            .toggle-details {{
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                cursor: pointer;
                font-size: 0.8em;
            }}
            .toggle-details:hover {{
                background-color: #2980b9;
            }}
            .details-row {{
                display: none;
                background-color: #f9f9f9;
            }}
            .details-content {{
                padding: 15px;
            }}
            pre {{
                background-color: #f1f1f1;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
                max-height: 300px;
                overflow-y: auto;
            }}
            .search-container {{
                margin-bottom: 20px;
            }}
            #searchInput {{
                padding: 10px;
                width: 100%;
                border: 1px solid #ddd;
                border-radius: 4px;
                box-sizing: border-box;
                font-size: 16px;
            }}
        </style>
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                const allRows = document.querySelectorAll('.repo-row');
                let activeDataset = 'all';
                let activeRepo = 'all';
                let activeType = 'all';

                // Set initial count values
                document.getElementById('total-count').textContent = allRows.length;
                document.getElementById('visible-count').textContent = allRows.length;

                // Helper function to apply all filters
                function applyFilters() {{
                    let visibleCount = 0;

                    allRows.forEach(row => {{
                        // Get row attributes
                        const rowDataset = row.getAttribute('data-dataset');
                        const rowRepo = row.getAttribute('data-repo');
                        const rowTypes = row.getAttribute('data-types');

                        // Check if row passes all filters
                        const passesDataset = (activeDataset === 'all' || rowDataset === activeDataset);
                        const passesRepo = (activeRepo === 'all' || rowRepo === activeRepo);
                        // Use word boundary to ensure precise matches for types like "author" vs "issue_author"
                        const passesType = (activeType === 'all' || 
                                          (rowTypes && (rowTypes.split(' ').includes(activeType) || 
                                           // Special case for backward compatibility
                                           (activeType === 'pr_author' && rowTypes.split(' ').includes('author')))));

                        // Display row only if it passes all filters
                        const isVisible = (passesDataset && passesRepo && passesType);
                        row.style.display = isVisible ? '' : 'none';

                        // Count visible rows
                        if (isVisible) visibleCount++;

                        // Hide details rows when filtering
                        const detailsRow = row.nextElementSibling;
                        if (detailsRow && detailsRow.classList.contains('details-row')) {{
                            detailsRow.style.display = 'none';
                            const toggleButton = row.querySelector('.toggle-details');
                            if (toggleButton) {{
                                toggleButton.textContent = 'Show Details';
                            }}
                        }}
                    }});

                    // Update the count display
                    document.getElementById('visible-count').textContent = visibleCount;
                }}

                // Dataset filter functionality
                const datasetFilterButtons = document.querySelectorAll('.dataset-filter');
                datasetFilterButtons.forEach(button => {{
                    button.addEventListener('click', function() {{
                        const dataset = this.getAttribute('data-dataset');
                        activeDataset = dataset;

                        // Update active button
                        datasetFilterButtons.forEach(btn => btn.classList.remove('active'));
                        this.classList.add('active');

                        applyFilters();
                    }});
                }});

                // Repository filter functionality
                const repoFilterButtons = document.querySelectorAll('.repo-filter');
                repoFilterButtons.forEach(button => {{
                    button.addEventListener('click', function() {{
                        const repo = this.getAttribute('data-repo');
                        activeRepo = repo;

                        // Update active button
                        repoFilterButtons.forEach(btn => btn.classList.remove('active'));
                        this.classList.add('active');

                        applyFilters();
                    }});
                }});

                // Contribution type filter functionality
                const typeFilterButtons = document.querySelectorAll('.type-filter');
                typeFilterButtons.forEach(button => {{
                    button.addEventListener('click', function() {{
                        const type = this.getAttribute('data-type');
                        activeType = type;

                        // Update active button
                        typeFilterButtons.forEach(btn => btn.classList.remove('active'));
                        this.classList.add('active');

                        applyFilters();
                    }});
                }});

                // Toggle details functionality
                const toggleButtons = document.querySelectorAll('.toggle-details');

                toggleButtons.forEach(button => {{
                    button.addEventListener('click', function() {{
                        const detailsRow = this.closest('tr').nextElementSibling;
                        if (detailsRow.style.display === 'table-row') {{
                            detailsRow.style.display = 'none';
                            this.textContent = 'Show Details';
                        }} else {{
                            detailsRow.style.display = 'table-row';
                            this.textContent = 'Hide Details';
                        }}
                    }});
                }});

                // Search functionality
                const searchInput = document.getElementById('searchInput');

                searchInput.addEventListener('keyup', function() {{
                    const searchValue = this.value.toLowerCase();

                    if (searchValue === '') {{
                        // If search is empty, just apply the current filters
                        applyFilters();
                        return;
                    }}

                    let visibleCount = 0;

                    allRows.forEach(row => {{
                        const text = row.textContent.toLowerCase();
                        // Check if text matches search AND passes all current filters
                        const matchesSearch = text.includes(searchValue);
                        const passesDataset = (activeDataset === 'all' || row.getAttribute('data-dataset') === activeDataset);
                        const passesRepo = (activeRepo === 'all' || row.getAttribute('data-repo') === activeRepo);
                        const rowTypes = row.getAttribute('data-types');
                        const passesType = (activeType === 'all' || 
                                          (rowTypes && (rowTypes.split(' ').includes(activeType) || 
                                           // Special case for backward compatibility
                                           (activeType === 'pr_author' && rowTypes.split(' ').includes('author')))));

                        const isVisible = (matchesSearch && passesDataset && passesRepo && passesType);
                        row.style.display = isVisible ? '' : 'none';

                        // Count visible rows
                        if (isVisible) visibleCount++;

                        // Hide details rows when filtering
                        const detailsRow = row.nextElementSibling;
                        if (detailsRow && detailsRow.classList.contains('details-row')) {{
                            detailsRow.style.display = 'none';
                            const toggleButton = row.querySelector('.toggle-details');
                            if (toggleButton) {{
                                toggleButton.textContent = 'Show Details';
                            }}
                        }}
                    }});

                    // Update the count display
                    document.getElementById('visible-count').textContent = visibleCount;
                }});
            }});
        </script>
    </head>
    <body>
        <h1>SWE-bench Analysis for {processed_data['username']}</h1>
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="container">
            <div class="stat-box">
                <h2>{processed_data['total_contributions']}</h2>
                <p>Total Contributions</p>
            </div>
            <div class="stat-box">
                <h2>{len(processed_data['repo_counts'])}</h2>
                <p>Repositories</p>
            </div>
            <div class="stat-box">
                <h2>{len(processed_data['type_counts'])}</h2>
                <p>Contribution Types</p>
            </div>
        </div>

        <h2>Visualizations</h2>

        <div class="visualization">
            <h3>Top Repositories</h3>
            <img src="top_repositories.png" alt="Top Repositories">
        </div>

        <div class="visualization">
            <h3>Contribution Types Distribution</h3>
            <img src="contribution_types.png" alt="Contribution Types">
        </div>
    """

    if processed_data['dates']:
        html_content += """
        <div class="visualization">
            <h3>Timeline of Contributions</h3>
            <img src="contributions_timeline.png" alt="Timeline">
        </div>
        """

    if processed_data['yearly_counts']:
        html_content += """
        <div class="visualization">
            <h3>Annual Contributions</h3>
            <img src="annual_contributions.png" alt="Annual Contributions">
        </div>
        """

    if len(processed_data['dataset_counts']) > 1:
        html_content += """
        <div class="visualization">
            <h3>Dataset Distribution</h3>
            <img src="dataset_distribution.png" alt="Dataset Distribution">
        </div>
        """

    html_content += """
        <div class="visualization">
            <h3>Contribution Types by Repository (Heatmap)</h3>
            <img src="repo_type_heatmap.png" alt="Heatmap">
        </div>

        <h2>Detailed Repository Breakdown</h2>
        <table>
            <tr>
                <th>Repository</th>
                <th>Contributions</th>
                <th>Percentage</th>
            </tr>
    """

    for repo, count in processed_data['repo_counts'].most_common():
        percentage = (count / processed_data['total_contributions']) * 100
        html_content += f"""
            <tr>
                <td>{repo}</td>
                <td>{count}</td>
                <td>{percentage:.1f}%</td>
            </tr>
        """

    html_content += """
        </table>

        <h2>Contribution Types Breakdown</h2>
        <table>
            <tr>
                <th>Type</th>
                <th>Count</th>
                <th>Percentage</th>
            </tr>
    """

    for type_name, count in processed_data['type_counts'].most_common():
        formatted_type = format_contribution_type(type_name)
        percentage = (count / sum(processed_data['type_counts'].values())) * 100
        html_content += f"""
            <tr>
                <td>{formatted_type}</td>
                <td>{count}</td>
                <td>{percentage:.1f}%</td>
            </tr>
        """

    html_content += """
        </table>

        <h2>Individual Issues and Pull Requests</h2>

        <div class="filter-controls">
            <h3>Filter by Dataset:</h3>
            <button class="dataset-filter active" data-dataset="all">All Datasets</button>
    """

    # Add buttons for each dataset
    for dataset in processed_data['dataset_counts'].keys():
        html_content += f"""
            <button class="dataset-filter" data-dataset="{dataset}">{dataset}</button>
        """

    html_content += """
        </div>

        <div class="filter-controls">
            <h3>Filter by Repository:</h3>
            <button class="repo-filter active" data-repo="all">All Repositories</button>
    """

    # Add buttons for top repositories (limit to top 10 to avoid clutter)
    for repo, count in sorted(processed_data['repo_counts'].items(), key=lambda x: x[1], reverse=True)[:10]:
        html_content += f"""
            <button class="repo-filter" data-repo="{repo}">{repo}</button>
        """

    html_content += """
        </div>

        <div class="filter-controls">
            <h3>Filter by Contribution Type:</h3>
            <button class="type-filter active" data-type="all">All Types</button>
    """

    # Add buttons for each contribution type
    # Use a set to track which formatted labels we've already added
    added_formatted_types = set()
    
    for contrib_type in processed_data['type_counts'].keys():
        formatted_type = format_contribution_type(contrib_type)
        
        # Skip if we already added a button with this formatted label
        if formatted_type in added_formatted_types:
            continue
            
        # For PR Author, ensure we use pr_author as the data-type since 
        # we've special-cased that in the filter logic
        data_type = "pr_author" if formatted_type == "PR Author" else contrib_type
        
        html_content += f"""
            <button class="type-filter" data-type="{data_type}">{formatted_type}</button>
        """
        added_formatted_types.add(formatted_type)

    html_content += """
        </div>

        <div class="search-container">
            <input type="text" id="searchInput" placeholder="Search issues by title, repo, or contribution type...">
        </div>

        <div id="entries-count">Showing all <span id="visible-count">0</span> of <span id="total-count">0</span> entries</div>

        <table id="contributions-table">
            <tr>
                <th>Repository</th>
                <th>Title</th>
                <th>Contribution Types</th>
                <th>Date</th>
                <th>Dataset</th>
                <th>Actions</th>
            </tr>
    """

    # Load the original data to get full issue details
    try:
        with open(os.path.join(os.getcwd(), 'user_contributions.json'), 'r') as f:
            original_data = json.load(f)
            all_results = original_data.get('results', [])
    except Exception as e:
        print(f"Warning: Could not load original data file: {e}")
        all_results = []

    # Sort results by date (newest first)
    sorted_results = sorted(all_results, key=lambda x: x.get('created_at', ''), reverse=True)

    for idx, result in enumerate(sorted_results):
        repo = result.get('repo', 'Unknown')
        title = result.get('title', 'Unknown')
        contribution_types = result.get('contribution_types', [])
        formatted_types = [format_contribution_type(t) for t in contribution_types]
        types_str = ', '.join(formatted_types)
        date_str = result.get('created_at', 'Unknown date')
        url = result.get('url', '#')
        dataset = result.get('dataset', 'Unknown')

        # Format date for display
        if 'T' in date_str:
            try:
                date_obj = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
                date_display = date_obj.strftime('%b %d, %Y')
            except:
                date_display = date_str
        else:
            date_display = date_str

        # Dataset badge
        dataset_badge = ""
        if "verified" in dataset.lower():
            dataset_badge = '<span class="badge badge-verified">Verified</span>'
        else:
            dataset_badge = '<span class="badge badge-standard">Standard</span>'

        # Get problem statement and hints
        problem = result.get('dataset_info', {}).get('problem_statement', 'No problem statement')
        hints = result.get('dataset_info', {}).get('hints_text', 'No hints')

        # Create a data attribute with all contribution types for filtering
        contrib_types_attr = " ".join(contribution_types)

        html_content += f"""
            <tr class="repo-row" data-dataset="{dataset}" data-repo="{repo}" data-types="{contrib_types_attr}">
                <td>{repo}</td>
                <td><a href="{url}" target="_blank">{title}</a></td>
                <td>{types_str}</td>
                <td>{date_display}</td>
                <td>{dataset_badge}</td>
                <td><button class="toggle-details">Show Details</button></td>
            </tr>
            <tr class="details-row">
                <td colspan="6">
                    <div class="details-content">
                        <h4>Problem Statement</h4>
                        <pre>{problem}</pre>

                        <h4>Hints/Comments</h4>
                        <pre>{hints}</pre>

                        <p><a href="{url}" target="_blank">View on GitHub</a></p>

                        <!-- Display related issues if any -->
                        {render_related_issues(result)}
                    </div>
                </td>
            </tr>
        """

    html_content += """
        </table>
    </body>
    </html>
    """

    with open(os.path.join(output_dir, 'report.html'), 'w') as f:
        f.write(html_content)

    print(f"HTML report generated at {os.path.join(output_dir, 'report.html')}")

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Visualize SWE-bench analyzer results')
    parser.add_argument('--input', default='user_contributions.json',
                      help='Input JSON file from swebench_analyzer.py (default: user_contributions.json)')
    parser.add_argument('--output-dir', '-o', default='visualizations',
                      help='Directory to save visualizations (default: visualizations)')
    parser.add_argument('--show', action='store_true',
                      help='Show visualizations instead of saving to files')
    parser.add_argument('--no-browser', action='store_true',
                      help='Do not automatically open the report in a web browser')
    args = parser.parse_args()

    # Load data
    data = load_results(args.input)
    if not data:
        return

    # Process data
    processed_data = prepare_data(data)
    if not processed_data:
        return

    # Create visualizations
    output_dir = None if args.show else args.output_dir
    create_visualizations(processed_data, output_dir)

    if not args.show:
        report_path = os.path.join(os.path.abspath(args.output_dir), 'report.html')
        print(f"Visualizations saved to {args.output_dir}/")

        if not args.no_browser:
            print(f"Opening {report_path} in your browser...")
            webbrowser.open('file://' + report_path)
        else:
            print(f"You can view the report at {report_path}")

if __name__ == "__main__":
    main()
