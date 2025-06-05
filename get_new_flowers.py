import os
import re
import json
import requests
import sys
import argparse
import time
from datetime import datetime
import litellm
# import subprocess # subprocess is no longer used
from urllib.parse import urlparse

import re # Added for parse_repo_url
from urllib.parse import urlparse # Ensure urlparse is imported

# Import our custom modules
from src.config import Config
from src.error_handler import ErrorHandler
from src.logger import PoemLogger
# We'll use these in future refactoring
# from src.llm_client_template import get_client_for_model, list_available_clients
from src.llm_client_template import LiteLLMClient # Import LiteLLMClient

# Configure LiteLLM
litellm.api_key = Config.GITHUB_TOKEN

# Initialize logger
logger = PoemLogger(logs_dir=Config.LOGS_DIR, max_log_size_bytes=Config.MAX_LOG_SIZE_BYTES)

# Initialize runtime statistics
run_stats = Config.get_initial_stats()

# Initialize error handler
error_handler = ErrorHandler(run_stats)

# GitHub API URLs and Headers are now directly accessed from Config
PR_LIST_URL = Config.PR_LIST_URL
PR_COMMENTS_URL = Config.PR_COMMENTS_URL
PR_REVIEW_COMMENTS_URL = Config.PR_REVIEW_COMMENTS_URL
HEADERS = Config.get_headers()

def get_pull_requests(owner, repo):
    """Fetch all pull requests from a repository."""
    prs = []
    page = 1

    while True:
        url = PR_LIST_URL.format(owner=owner, repo=repo)
        # print(f"Fetching PRs from {url}?page={page}&state=all&per_page=100") # Verbose
        response = requests.get(f"{url}?page={page}&state=all&per_page=100", headers=HEADERS)

        if response.status_code != 200:
            print(f"Error fetching PRs for {owner}/{repo}: {response.status_code}")
            break

        results = response.json()
        # print(f"Got {len(results)} results for page {page}") # Verbose
        if not results:
            break

        prs.extend(results)
        page += 1

        # Respect GitHub API rate limits
        if page % 10 == 0:
            time.sleep(1)

    return prs

def get_comments_for_pr(owner, repo, pr_number):
    """Fetch all comments for a given PR."""
    url = PR_COMMENTS_URL.format(owner=owner, repo=repo, pr_number=pr_number)
    # print(f"Fetching comments from {url}") # Verbose
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching comments for PR #{pr_number} in {owner}/{repo}: {response.status_code}")
        return []

    comments = response.json()
    # print(f"Found {len(comments)} comments for PR #{pr_number}") # Verbose
    return comments

def get_reviews_for_pr(owner, repo, pr_number):
    """Fetch all reviews for a given PR."""
    url = Config.PR_REVIEWS_URL.format(owner=owner, repo=repo, pr_number=pr_number)
    # print(f"Fetching reviews from {url}") # Verbose
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching reviews for PR #{pr_number} in {owner}/{repo}: {response.status_code}")
        return []

    reviews = response.json()
    # print(f"Found {len(reviews)} reviews for PR #{pr_number}") # Verbose
    return reviews

def get_comments_from_review(owner, repo, pr_number, review_id):
    """Fetch comments for a specific review."""
    url = Config.PR_REVIEW_COMMENTS_URL.format(owner=owner, repo=repo, pr_number=pr_number, review_id=review_id)
    # print(f"Fetching comments for review {review_id} from {url}") # Verbose
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching comments for review {review_id} in PR #{pr_number} in {owner}/{repo}: {response.status_code}")
        return []

    comments = response.json()
    # print(f"Found {len(comments)} comments for review {review_id}") # Verbose
    return comments

def is_valid_github_url(url):
    """Validate that a URL is a legitimate GitHub URL."""
    try:
        parsed = urlparse(url)
        # Check scheme
        if parsed.scheme not in ('http', 'https'):
            return False
            
        # Check hostname is github.com
        if not parsed.hostname:
            return False
        if not (parsed.hostname == 'github.com' or parsed.hostname.endswith('.github.com')): # Ensure hostname is github.com or a valid subdomain
            return False
            
        # Validate path exists and has expected format
        if not parsed.path or not parsed.path.strip('/'):
            return False
            
        # Path should have format: /{owner}/{repo} or /{owner}/{repo}/...
        parts = [p for p in parsed.path.split('/') if p]
        if len(parts) < 2:
            return False
            
        return True
    except Exception:
        return False

def _find_or_create_link(comment_body, lines):
    """Find an existing GitHub link or create a default one."""
    # Look for a GitHub link in the comment
    link_line = None
    for line in lines:
        stripped = line.strip()
        if "github.com" in stripped:
            # Extract URL
            url_match = re.search(r'<?(https?://[^\s>]+)>?', stripped)
            if url_match:
                url = url_match.group(1)
                if is_valid_github_url(url):
                    link_line = f"<{url}>"
                    break

    # If no valid GitHub link found, use a default link
    if not link_line:
        # Extract repository info from the comment if possible
        if repo_match := re.search(r"github\.com/([^/]+/[^/\s]+)", comment_body):
            repo_path = repo_match[1]
            default_url = f"https://github.com/{repo_path}"
            if is_valid_github_url(default_url):
                link_line = f"<{default_url}>"
        
        # Fallback to known safe default
        if not link_line:
            link_line = "<https://github.com/TheRealFREDP3D/Making-BanditGUI>"

    return link_line

def _process_llm_response(poem_text, comment_body, lines):
    """Process the LLM response to extract poem lines and link."""
    if poem_text == "NO_POEM" or "NO_POEM" in poem_text:
        print("    No poem found by LLM")
        return (None, None)

    # Extract poem lines and preserve formatting
    ai_poem_lines = poem_text.strip().splitlines()
    # Preserve original formatting but ensure each line has at least one space prefix
    ai_poem_lines = [line if line.startswith(" ") else f" {line}" for line in ai_poem_lines if line.strip() or line == ""]

    link_line = _find_or_create_link(comment_body, lines)

    if ai_poem_lines:
        print(f"    Found poem using LLM with {len(ai_poem_lines)} lines")
        return (ai_poem_lines, link_line)

    return (None, None)

def extract_poem_from_comment(comment_body, model_name_to_use):
    """Extract poem and link from a comment using the specified LiteLLM client.

    Args:
        comment_body: The comment text to analyze
        model_name_to_use: The specific model name to use (e.g., "gemini/gemini-1.5-flash")
    """
    if not comment_body:
        return (None, None)

    lines = comment_body.strip().splitlines()
    prompt = Config.POEM_EXTRACTION_PROMPT.format(comment_body=comment_body)

    print(f"    Trying to extract poem using LiteLLM with {model_name_to_use}...")

    # Instantiate LiteLLMClient with the specified model
    llm_client = LiteLLMClient(model_name=model_name_to_use)

    try:
        poem_text = llm_client.extract_poem(prompt)

        if not poem_text or poem_text == "NO_POEM" or "NO_POEM" in poem_text:
            # print(f"    LiteLLM ({model_name_to_use}) found no poem or indicated NO_POEM.") # Less verbose
            return (None, None)

        # print(f"    LiteLLM response from {model_name_to_use}: {poem_text[:100]}...") # Less verbose
        return _process_llm_response(poem_text, comment_body, lines)

    except Exception as e:
        print(f"    Error using LiteLLM client with {model_name_to_use}: {e}")
        error_handler.handle_litellm_error(e, model_name_to_use)
        return (None, None)


def create_poem_entry(poem_lines, link, repo_owner, repo_name, pr_number):
    """Create a JSON-friendly poem entry."""
    # Clean up poem lines (remove '>' prefix but preserve indentation and formatting)
    cleaned_lines = []
    for line in poem_lines:
        if line.strip():  # Skip empty lines
            if line.startswith(" "):
                # Remove the first two characters (space and '>') if it's a quoted line
                # but preserve the rest of the formatting
                if len(line) > 2 and line[1] == '>':
                    cleaned_lines.append(line[2:])
                else:
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line.strip())

    # Clean up link
    if link.startswith("<") and link.endswith(">"):
        link = link[1:-1]

    return {
        "poem": cleaned_lines,
        "link": link,
        "repository": f"{repo_owner}/{repo_name}",
        "pr_number": pr_number,
        "collected_at": datetime.now().isoformat()
    }

def load_existing_poems(json_file):
    """Load existing poems from JSON file."""
    if not os.path.exists(json_file):
        return []

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Warning: {json_file} contains invalid JSON. Creating new file.")
        return []

def save_poems_to_json(poems, json_file):
    """Save poems to JSON file."""
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(poems, f, indent=2)

def _process_gemini_comment(comment, owner, repo, pr_number, model_name_to_use, comment_type="comment"):
    """Process a comment from Gemini Code Assist to extract poems.

    Args:
        comment: The comment to process
        owner: Repository owner
        repo: Repository name
        pr_number: Pull request number
        model_name_to_use: The specific model name to use for LLM processing.
        comment_type: Type of comment ("comment" or "review")
    """
    no_poem_phrases = [
        "The GitHub comment does not contain a poem",
        "There are no poetic lines in this comment",
        "NO POEM"
    ]
    if any(phrase.lower() in comment["body"].lower() for phrase in no_poem_phrases):
        print("    Comment contains a NO POEM phrase. Skipping.")
        return None

    print(f"    Found {comment_type} from Gemini Code Assist: {comment['user']['login']}")
    # ollama_only parameter removed from the call below
    poem_lines, link = extract_poem_from_comment(comment["body"], model_name_to_use=model_name_to_use)

    if not (poem_lines and link):
        print(f"    No poem found in {comment_type} from {comment['user']['login']} using model {model_name_to_use}")
        return None

    if comment.get("html_url"):
        link = f"<{comment['html_url']}>"

    entry = create_poem_entry(poem_lines, link, owner, repo, pr_number)
    print(f"    Found poem in PR #{pr_number} from {comment_type}")
    return entry

def collect_poems_from_repo(owner, repo, model_name_to_use, max_prs=100):
    """Collect all poems from a specific repository.

    Args:
        owner: Repository owner
        repo: Repository name
        model_name_to_use: The specific model name to use for LLM processing.
        max_prs: Maximum number of PRs to check
    """
    poems = []
    print(f"Collecting poems from {owner}/{repo} using model {model_name_to_use}...")

    prs = get_pull_requests(owner, repo)[:max_prs]
    print(f"Found {len(prs)} PRs in {owner}/{repo}. Processing...")

    for pr in prs:
        pr_number = pr["number"]
        print(f"  Processing PR #{pr_number}...")

        comments = get_comments_for_pr(owner, repo, pr_number)
        for comment in comments:
            # print(f"    Comment from user: {comment['user']['login']}") # Verbose
            if "gemini-code-assist" in comment["user"]["login"].lower():
                if entry := _process_gemini_comment(comment, owner, repo, pr_number, model_name_to_use=model_name_to_use):
                    poems.append(entry)

        reviews = get_reviews_for_pr(owner, repo, pr_number)
        for review in reviews:
            # print(f"    Review from user: {review['user']['login']}") # Verbose
            if "gemini-code-assist" in review["user"]["login"].lower():
                review_comments = get_comments_from_review(owner, repo, pr_number, review["id"])
                for review_comment in review_comments:
                    # print(f"      Review comment from user: {review_comment['user']['login']}") # Verbose
                    if "gemini-code-assist" in review_comment["user"]["login"].lower():
                        if entry := _process_gemini_comment(review_comment, owner, repo, pr_number, model_name_to_use=model_name_to_use, comment_type="review_comment"):
                            poems.append(entry)

        time.sleep(0.5)

    return poems

def is_duplicate(new_poem, existing_poems):
    """Check if a poem is already in the collection."""
    new_link = new_poem.get("link", "")

    for poem in existing_poems:
        if poem.get("link", "") == new_link:
            run_stats["duplicates"].append({
                "link": new_link,
                "repository": new_poem.get("repository", ""),
                "pr_number": new_poem.get("pr_number", "")
            })
            return True

    return False

def get_next_log_file():
    """Get the next available log file name."""
    return logger._get_log_file()

def write_log_summary(repository_url, model_name):
    """Write a summary of the run to the log file."""
    logger.write_run_summary(run_stats, repository_url, model_name)

def main():
    print("Starting Gemini Code Assist poem collection script")
    parser = argparse.ArgumentParser(description="Collect Gemini Code Assist poems from GitHub repositories")
    parser.add_argument("repository_url", help="Full GitHub repository URL (e.g., https://github.com/owner/repo)")
    parser.add_argument("--max-prs", help="Maximum number of PRs to check per repository", type=int, default=100)
    parser.add_argument("--output", help="Output JSON file", default=Config.GEM_FLOWERS_FILE)
    parser.add_argument("--model", help="Specify the LLM model to use (e.g., 'gemini/gemini-1.5-flash', 'ollama/llama2').", default=Config.DEFAULT_MODEL)
    args = parser.parse_args()

    model_name_to_use = args.model

    owner, repo = parse_repo_url(args.repository_url)
    if owner is None or repo is None:
        print(f"Error: Invalid repository URL format: {args.repository_url}")
        print("Expected format: https://github.com/owner/repo or git@github.com:owner/repo.git")
        sys.exit(1)

    print(f"Processing repository: {args.repository_url}")
    # print(f"GitHub token available: {bool(Config.GITHUB_TOKEN)}") # Less verbose

    json_file = args.output
    new_poems = []

    try:
        # print(f"Checking specified repository: {owner}/{repo}") # Redundant with above
        repo_poems = collect_poems_from_repo(owner, repo, model_name_to_use, args.max_prs)
        new_poems.extend(repo_poems)
        print(f"Collected {len(repo_poems)} initial poems from {owner}/{repo}")

        existing_poems = load_existing_poems(json_file)
        unique_new_poems = [poem for poem in new_poems if not is_duplicate(poem, existing_poems)]

        run_stats["new_poems"] = len(unique_new_poems)
        run_stats["total_poems"] = len(existing_poems) + len(unique_new_poems) # This is a pre-filter count

        if not unique_new_poems and not existing_poems: # If no new poems and no existing ones, nothing to do.
            print("No new poems found and no existing poems loaded. Output files will not be generated.")
        else:
            all_poems = unique_new_poems + existing_poems

            # Filter out NO_POEM entries using the new function
            final_poems_to_save = filter_no_poem_entries(all_poems)

            # Save the truly final list of poems to JSON
            save_poems_to_json(final_poems_to_save, json_file)
            print(f"Saved {len(final_poems_to_save)} poems to {json_file} after filtering.")

            # Update total_poems stat with the count of poems actually saved
            run_stats["total_poems"] = len(final_poems_to_save)

            if not final_poems_to_save:
                print("No valid poems to generate Markdown file.")
            else:
                # Generate markdown file from the final filtered list
                md_file_path = json_file.replace(".json", ".md")
                if not md_file_path.endswith(".md"):
                    md_file_path = json_file + ".md"
                generate_markdown(final_poems_to_save, md_file_path, args.repository_url)
                print(f"Generated markdown file: {md_file_path}")

    except Exception as e:
        error_msg = f"Error during execution: {str(e)}"
        print(error_msg)
        run_stats["errors"].append(error_msg)

    write_log_summary(args.repository_url, model_name_to_use)

# Functions moved from cleanup_poems.py
def filter_no_poem_entries(poems_list):
    """Filters out poems that are considered 'NO_POEM' entries."""
    # Original filter: exact match or "NO_POEM" in the single line
    filtered = [
        poem for poem in poems_list if not (
            len(poem.get("poem", [])) == 1 and (
                poem.get("poem", [""])[0] == "\"NO_POEM\"" or
                "NO_POEM" in poem.get("poem", [""])[0] # Check substring for single line poems
            )
        )
    ]
    # Second filter: "NO_POEM" substring in any line of multi-line poems
    # This also implicitly handles the single line case again, but it's fine.
    further_filtered = [
        poem for poem in filtered if not any(
            "NO_POEM" in line for line in poem.get("poem", [])
        )
    ]
    return further_filtered

def generate_markdown(poems, md_file, repository_url):
    """Generate markdown file from poems."""
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("# Gemini Code Assist - PR Poetry\n\n")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write("## Collection Statistics\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Total Poems in Collection | {len(poems)} |\n")
        f.write(f"| Repository Processed | {repository_url} |\n")
        pr_count = len(set((poem.get("repository", ""), poem.get("pr_number", "")) for poem in poems))
        f.write(f"| Unique PRs with Poems (in this update) | {pr_count} |\n")
        f.write(f"| Last Updated | {timestamp} |\n\n")

        sorted_poems = sorted(poems, key=lambda p: (p.get("repository", "").lower(), p.get("pr_number", 0), p.get("link", "")))

        for poem in sorted_poems:
            f.write("---\n\n")
            for line in poem.get("poem", []):
                if line.strip():
                    if not line.startswith(" "):
                        f.write(f"  {line}  \n")
                    else:
                        f.write(f"  {line}  \n")
                else:
                    f.write("\n")
            f.write("\n")
            f.write(f"  <{poem.get('link')}>\n")
            f.write(f"  \n  _From: {poem.get('repository')} PR #{poem.get('pr_number', 'N/A')}_\n\n")

def parse_repo_url(url: str) -> tuple[str | None, str | None]:
    """
    Parses a GitHub repository URL to extract owner and repository name.
    Supports HTTPS and SSH formats.
    e.g., https://github.com/owner/repo or git@github.com:owner/repo.git
    Returns (owner, repo) or (None, None) if parsing fails.
    """
    # Try parsing as HTTPS URL
    parsed_url = urlparse(url)
    if parsed_url.scheme == 'https' and parsed_url.hostname == 'github.com':
        path_parts = parsed_url.path.strip('/').split('/')
        if len(path_parts) >= 2:
            owner = path_parts[0]
            repo = path_parts[1].replace('.git', '')
            return owner, repo

    # Try parsing as SSH URL
    ssh_match = re.match(r"git@github\.com:([^/]+)/([^.]+)\.git$", url)
    if ssh_match:
        owner = ssh_match.group(1)
        repo = ssh_match.group(2)
        return owner, repo

    # Try parsing as SSH URL without .git suffix
    ssh_match_no_suffix = re.match(r"git@github\.com:([^/]+)/([^.]+)$", url)
    if ssh_match_no_suffix:
        owner = ssh_match_no_suffix.group(1)
        repo = ssh_match_no_suffix.group(2)
        return owner, repo

    # Fallback for URLs like https://github.com/owner/repo/ (with trailing slash)
    if parsed_url.scheme == 'https' and parsed_url.hostname == 'github.com':
        path_parts = parsed_url.path.strip('/').split('/')
        if len(path_parts) >= 2 : # Allow for extra parts like /pulls, /issues etc.
            owner = path_parts[0]
            repo = path_parts[1].replace('.git', '')
            return owner, repo

    return None, None

if __name__ == "__main__":
    # print("Starting script...") # Moved to main
    # print(f"GitHub token available: {bool(Config.GITHUB_TOKEN)}") # Less verbose, can be logged if needed
    main()
    print("Script completed.")
