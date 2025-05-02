# GitHub Pull Request Conversation Fetcher

This utility fetches and saves the complete conversation history from GitHub pull requests, including PR details, issue comments, review comments, and reviews.

## Features

- Fetch a single PR, multiple specific PRs, or the latest N PRs
- Save conversations in either Markdown or JSON format
- Uses GitHub token from `.env` file or command-line argument
- Handles pagination for large PRs with many comments
- Customizable output directory and file naming

## Requirements

- Python 3.6+
- Required packages:
  - requests
  - python-dotenv

## Installation

1. Make sure you have Python 3.6+ installed
2. Install required packages:
   ```bash
   pip install requests python-dotenv
   ```
3. Set up your GitHub token in the project's `.env` file or provide it via command line

## Usage

```bash
# Make sure you have a .env file with your GitHub token
# GITHUB_TOKEN=your_github_token_here

# Fetch a single PR
python get_pr_conversations.py --pr 123

# Fetch multiple PRs
python get_pr_conversations.py --prs 123,124,125

# Fetch the 10 most recently updated PRs
python get_pr_conversations.py --latest 10

# Specify a custom output directory
python get_pr_conversations.py --pr 123 --output-dir my_pr_data

# Save in JSON format instead of Markdown
python get_pr_conversations.py --pr 123 --format json

# Override the token from .env file
python get_pr_conversations.py --pr 123 --token YOUR_GITHUB_TOKEN
```

## Output Format

By default, the script saves conversations in Markdown format with the following structure:

```markdown
# PR #123: Title of the PR

**Author:** username
**Created:** 2023-01-01T00:00:00Z
**Updated:** 2023-01-02T00:00:00Z
**State:** open

## Description

PR description text...

## Comments

### username - 2023-01-01T12:00:00Z

Comment text...

## Reviews

### username - 2023-01-01T13:00:00Z

**State:** APPROVED

Review text...

## Review Comments

### username - 2023-01-01T14:00:00Z

**Path:** path/to/file.py
**Line:** 42

Review comment text...
```

You can also save in JSON format for programmatic processing.

## Default Settings

- Output directory: `pr-conversation`
- Output file format: `{repo}-{pr-number}.md`
- Repository owner: `TheRealFREDP3D`
- Repository name: `Gemini-Code-Assist-PR-Poetry`

You can override these defaults using command-line arguments.
