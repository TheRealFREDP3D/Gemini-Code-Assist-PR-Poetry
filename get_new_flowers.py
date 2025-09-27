import os
import re
import json
import requests
import sys
import argparse
import time
from datetime import datetime
import litellm
import subprocess
from urllib.parse import urlparse

print("Initial imports successful.")

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
error_handler = ErrorHandler(run_stats) # No need to pass failed_litellm_models or failed_clients here, ErrorHandler manages them

def load_custom_llm_models():
    """Load custom LLM models from the JSON file."""
    try:
        model_file = os.path.join("llm_client", "custom_llm_model.json")
        with open(model_file, 'r') as f:
            data = json.load(f)

        # Clean up the model names (remove trailing commas)
        try:
            return [model.rstrip(',') for model in data.get("litellm_models", [])]
        except Exception as e:
            print(f"Error processing model names: {e}")
            return []
    except Exception as e:
        print(f"Error loading custom LLM models: {e}")
        return []

def is_ollama_running():
    """Check if Ollama server is running."""
    try:
        # Try to make a request to the Ollama API using requests library
        response = requests.get(f"{Config.OLLAMA_API_URL}/api/tags", timeout=5)
        return response.status_code == 200 and "models" in response.text
    except requests.RequestException:
        return False

# GitHub API URLs and Headers are now directly accessed from Config
SEARCH_REPOS_URL = Config.SEARCH_REPOS_URL
PR_LIST_URL = Config.PR_LIST_URL
PR_COMMENTS_URL = Config.PR_COMMENTS_URL
PR_REVIEW_COMMENTS_URL = Config.PR_REVIEW_COMMENTS_URL # Corrected URL for review comments
HEADERS = Config.get_headers()

def search_public_repos(query="gemini-code-assist", max_repos=10):
    """Search for public repositories that might contain Gemini Code Assist comments."""
    search_url = f"{SEARCH_REPOS_URL}?q={query}&sort=updated&order=desc&per_page={max_repos}"
    response = requests.get(search_url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error searching repositories: {response.status_code}")
        return []

    return [(repo["owner"]["login"], repo["name"]) for repo in response.json().get("items", [])]

def get_pull_requests(owner, repo):
    """Fetch all pull requests from a repository."""
    prs = []
    page = 1

    while True:
        url = PR_LIST_URL.format(owner=owner, repo=repo)
        print(f"Fetching PRs from {url}?page={page}&state=all&per_page=100")
        response = requests.get(f"{url}?page={page}&state=all&per_page=100", headers=HEADERS)

        if response.status_code != 200:
            print(f"Error fetching PRs for {owner}/{repo}: {response.status_code}")
            break

        results = response.json()
        print(f"Got {len(results)} results for page {page}")
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
    print(f"Fetching comments from {url}")
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching comments for PR #{pr_number} in {owner}/{repo}: {response.status_code}")
        return []

    comments = response.json()
    print(f"Found {len(comments)} comments for PR #{pr_number}")
    return comments

def get_reviews_for_pr(owner, repo, pr_number):
    """Fetch all reviews for a given PR."""
    url = Config.PR_REVIEWS_URL.format(owner=owner, repo=repo, pr_number=pr_number)
    print(f"Fetching reviews from {url}")
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching reviews for PR #{pr_number} in {owner}/{repo}: {response.status_code}")
        return []

    reviews = response.json()
    print(f"Found {len(reviews)} reviews for PR #{pr_number}")
    return reviews

def get_comments_from_review(owner, repo, pr_number, review_id):
    """Fetch comments for a specific review."""
    url = Config.PR_REVIEW_COMMENTS_URL.format(owner=owner, repo=repo, pr_number=pr_number, review_id=review_id)
    print(f"Fetching comments for review {review_id} from {url}")
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching comments for review {review_id} in PR #{pr_number} in {owner}/{repo}: {response.status_code}")
        return []

    comments = response.json()
    print(f"Found {len(comments)} comments for review {review_id}")
    return comments

# Removed load_client_module, _handle_client_error (direct usages),
# _modify_client_code, _execute_temp_client, get_poem_with_client as they are no longer needed.

def _try_traditional_extraction(comment_body):
    """Try to extract poem using traditional pattern matching method."""
    lines = comment_body.strip().splitlines()
    poem_lines = []
    link_line = None

    in_poem = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(" ") or (in_poem and stripped == ''):
            # Preserve the original line with its formatting
            poem_lines.append(line)
            in_poem = True
        elif re.match(r"<https://github\.com/.+?>", stripped):
            link_line = stripped
            break
        else:
            in_poem = False

    # If we found a poem with the traditional method, return it
    if poem_lines and link_line:
        print("    Found poem using traditional method")
        return (poem_lines, link_line)

    return (None, None)

# This function is now handled by the error_handler module

# Removed _try_primary_litellm_models, _try_ollama_models,
# _try_custom_litellm_models, and _try_client_implementations
# as they are replaced by the new LiteLLMClient logic in extract_poem_from_comment.

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
        # Extract all URLs from the line and validate each
        urls = re.findall(r'<?(https?://[^\s>]+)>?', stripped)
        for url in urls:
            if is_valid_github_url(url):
                link_line = f"<{url}>"
                break
        if link_line:
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

def extract_poem_from_comment(comment_body, model_name_to_use, ollama_only=False):
    """Extract poem and link from a comment using the specified LiteLLM client.

    Args:
        comment_body: The comment text to analyze
        model_name_to_use: The specific model name to use (e.g., "gemini/gemini-1.5-flash")
        ollama_only: If True, only use Ollama models for LLM processing (Note: this flag might be redundant if model_name_to_use already specifies an ollama model)
    """
    if not comment_body:
        return (None, None)

    lines = comment_body.strip().splitlines()
    poem_lines, link_line = _try_traditional_extraction(comment_body)
    if poem_lines and link_line:
        return (poem_lines, link_line)

    prompt = Config.POEM_EXTRACTION_PROMPT.format(comment_body=comment_body)

    if ollama_only and not model_name_to_use.startswith("ollama/"):
        print(f"    Ollama-only mode is enabled, but the specified model '{model_name_to_use}' is not an Ollama model. Skipping.")
        return (None, None)

    if ollama_only and not is_ollama_running():
        print("    Ollama-only mode is enabled but Ollama server is not running.")
        return (None, None)

    print(f"    Trying to extract poem using LiteLLM with {model_name_to_use}...")

    # Instantiate LiteLLMClient with the specified model
    llm_client = LiteLLMClient(model_name=model_name_to_use)

    try:
        poem_text = llm_client.extract_poem(prompt)
        run_stats["models_used"].add(model_name_to_use) # Track model usage

        if not poem_text or poem_text == "NO_POEM" or "NO_POEM" in poem_text:
            print(f"    LiteLLM ({model_name_to_use}) found no poem or indicated NO_POEM.")
            return (None, None)

        print(f"    LiteLLM response from {model_name_to_use}: {poem_text[:100]}...")
        return _process_llm_response(poem_text, comment_body, lines)

    except Exception as e:
        print(f"    Error using LiteLLM client with {model_name_to_use}: {e}")
        error_handler.handle_litellm_error(e, model_name_to_use)
        error_handler.check_all_models_failed(
            primary_models=[Config.DEFAULT_MODEL], # Assuming DEFAULT_MODEL is the only primary
            custom_models=load_custom_llm_models(), # Still need to load custom models to check if all failed
            llm_clients=[] # No separate client implementations anymore
        )
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

def _process_gemini_comment(comment, owner, repo, pr_number, model_name_to_use, comment_type="comment", ollama_only=False):
    """Process a comment from Gemini Code Assist to extract poems.

    Args:
        comment: The comment to process
        owner: Repository owner
        repo: Repository name
        pr_number: Pull request number
        model_name_to_use: The specific model name to use for LLM processing.
        comment_type: Type of comment ("comment" or "review")
        ollama_only: If True, only use Ollama models for LLM processing
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
    poem_lines, link = extract_poem_from_comment(comment["body"], model_name_to_use=model_name_to_use, ollama_only=ollama_only)

    if not (poem_lines and link):
        print(f"    No poem found in {comment_type} from {comment['user']['login']} using model {model_name_to_use}")
        return None

    if comment.get("html_url"):
        link = f"<{comment['html_url']}>"

    entry = create_poem_entry(poem_lines, link, owner, repo, pr_number)
    print(f"    Found poem in PR #{pr_number} from {comment_type}")
    return entry

def collect_poems_from_repo(owner, repo, model_name_to_use, max_prs=100, ollama_only=False):
    """Collect all poems from a specific repository.

    Args:
        owner: Repository owner
        repo: Repository name
        model_name_to_use: The specific model name to use for LLM processing.
        max_prs: Maximum number of PRs to check
        ollama_only: If True, only use Ollama models for LLM processing
    """
    poems = []
    print(f"Collecting poems from {owner}/{repo} using model {model_name_to_use}...")
    if ollama_only:
        print(f"Using Ollama-only mode (effective if '{model_name_to_use}' is an Ollama model and server is running)")

    prs = get_pull_requests(owner, repo)[:max_prs]
    print(f"Found {len(prs)} PRs in {owner}/{repo}")

    run_stats["prs_checked"] += len(prs)

    for pr in prs:
        pr_number = pr["number"]
        print(f"  Processing PR #{pr_number}...")

        comments = get_comments_for_pr(owner, repo, pr_number)
        for comment in comments:
            print(f"    Comment from user: {comment['user']['login']}")
            if "gemini-code-assist" in comment["user"]["login"].lower():
                if entry := _process_gemini_comment(comment, owner, repo, pr_number, model_name_to_use=model_name_to_use, ollama_only=ollama_only):
                    poems.append(entry)

        reviews = get_reviews_for_pr(owner, repo, pr_number) # Use the new get_reviews_for_pr
        for review in reviews:
            print(f"    Review from user: {review['user']['login']}")
            if "gemini-code-assist" in review["user"]["login"].lower():
                # Now fetch comments for this specific review
                review_comments = get_comments_from_review(owner, repo, pr_number, review["id"])
                for review_comment in review_comments:
                    print(f"      Review comment from user: {review_comment['user']['login']}")
                    if "gemini-code-assist" in review_comment["user"]["login"].lower():
                        if entry := _process_gemini_comment(review_comment, owner, repo, pr_number, model_name_to_use=model_name_to_use, comment_type="review_comment", ollama_only=ollama_only):
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

def write_log_summary():
    """Write a summary of the run to the log file."""
    logger.write_run_summary(run_stats)

def run_wizard(args):
    """Interactive wizard to prompt for parameter values."""
    print("\n=== Gemini Code Assist Poetry Collection Wizard ===\n")
    print("Press Enter to use default values or type a new value.\n")

    default_owner = args.owner
    user_input = input(f"GitHub repository owner [{default_owner}]: ").strip()
    args.owner = user_input or default_owner

    default_repo = args.repo
    user_input = input(f"GitHub repository name [{default_repo}]: ").strip()
    args.repo = user_input or default_repo

    default_search = "yes" if args.search else "no"
    user_input = input(f"Search for public repositories with Gemini poems? (yes/no) [{default_search}]: ").strip().lower()
    args.search = user_input == "yes" if user_input else args.search

    if args.search:
        default_max_repos = args.max_repos
        user_input = input(f"Maximum number of repositories to search [{default_max_repos}]: ").strip()
        if user_input:
            try:
                args.max_repos = int(user_input)
            except ValueError:
                print(f"Invalid input. Using default value: {default_max_repos}")

    default_max_prs = args.max_prs
    user_input = input(f"Maximum number of PRs to check per repository [{default_max_prs}]: ").strip()
    if user_input:
        try:
            args.max_prs = int(user_input)
        except ValueError:
            print(f"Invalid input. Using default value: {default_max_prs}")

    default_output = args.output
    user_input = input(f"Output JSON file [{default_output}]: ").strip()
    args.output = user_input or default_output

    default_ollama = "yes" if args.ollama else "no"
    user_input = input(f"Use only local Ollama models? (yes/no) [{default_ollama}]: ").strip().lower()
    args.ollama = user_input == "yes" if user_input else args.ollama

    print("\n=== Configuration Summary ===")
    print(f"Repository: {args.owner}/{args.repo}")
    print(f"Search mode: {'Enabled' if args.search else 'Disabled'}")
    if args.search:
        print(f"Max repositories to search: {args.max_repos}")
    print(f"Max PRs to check: {args.max_prs}")
    print(f"Output file: {args.output}")
    print(f"Ollama mode: {'Enabled' if args.ollama else 'Disabled'}")
    print("\nStarting collection...\n")

    return args

def main():
    print("Script execution started.")
    print("Starting Gemini Code Assist poem collection script")
    parser = argparse.ArgumentParser(description="Collect Gemini Code Assist poems from GitHub repositories")
    parser.add_argument("--owner", help="GitHub repository owner", default=Config.DEFAULT_REPO_OWNER)
    parser.add_argument("--repo", help="GitHub repository name", default=Config.DEFAULT_REPO_NAME)
    parser.add_argument("--search", help="Search for public repositories with Gemini poems", action="store_true")
    parser.add_argument("--max-repos", help="Maximum number of repositories to search", type=int, default=5)
    parser.add_argument("--max-prs", help="Maximum number of PRs to check per repository", type=int, default=100)
    parser.add_argument("--output", help="Output JSON file", default=Config.GEM_FLOWERS_FILE)
    parser.add_argument("--ollama", help="Use only local Ollama models for LLM processing (Note: --model takes precedence)", action="store_true")
    parser.add_argument("--wizard", "-w", help="Run in wizard mode to interactively set parameters", action="store_true")
    parser.add_argument("--model", help="Specify the LLM model to use (e.g., 'gemini/gemini-1.5-flash', 'ollama/llama2'). Overrides default and Ollama-only mode for model selection.", default=None)
    args = parser.parse_args()

    if args.wizard:
        args = run_wizard(args)

    model_name_to_use = args.model or Config.DEFAULT_MODEL

    effective_ollama_only = args.ollama
    if args.model:
        effective_ollama_only = model_name_to_use.startswith("ollama/")
    elif args.ollama and not model_name_to_use.startswith("ollama/"):
        print(f"Warning: --ollama flag is set, but the effective default model '{model_name_to_use}' is not an Ollama model. Poems will be extracted using '{model_name_to_use}'. Consider using --model to specify an Ollama model if that's the intent.")

    print(f"Configuration: owner={args.owner}, repo={args.repo}, search={args.search}, max_repos={args.max_repos}, max_prs={args.max_prs}, ollama_flag={args.ollama}, model_to_use='{model_name_to_use}'")
    print(f"GitHub token available: {bool(Config.GITHUB_TOKEN)}")

    json_file = args.output
    new_poems = []

    try:
        if args.search:
            print("Searching for public repositories with Gemini Code Assist comments...")
            repos = search_public_repos(max_repos=args.max_repos)
            print(f"Found {len(repos)} repositories to check")

            for owner, repo in repos:
                run_stats["repositories_checked"].add(f"{owner}/{repo}")
                repo_poems = collect_poems_from_repo(owner, repo, model_name_to_use, args.max_prs, ollama_only=effective_ollama_only)
                new_poems.extend(repo_poems)
                print(f"Collected {len(repo_poems)} poems from {owner}/{repo}")
        else:
            print(f"Checking specified repository: {args.owner}/{args.repo}")
            run_stats["repositories_checked"].add(f"{args.owner}/{args.repo}")
            repo_poems = collect_poems_from_repo(args.owner, args.repo, model_name_to_use, args.max_prs, ollama_only=effective_ollama_only)
            new_poems.extend(repo_poems)
            print(f"Collected {len(repo_poems)} poems from {args.owner}/{args.repo}")

        existing_poems = load_existing_poems(json_file)
        unique_new_poems = [poem for poem in new_poems if not is_duplicate(poem, existing_poems)]

        run_stats["new_poems"] = len(unique_new_poems)
        run_stats["total_poems"] = len(existing_poems) + len(unique_new_poems)

        if not unique_new_poems:
            print("No new poems found.")
        else:
            all_poems = unique_new_poems + existing_poems

            def is_no_poem_entry(poem):
                poem_lines = poem.get("poem", [])
                return (len(poem_lines) == 1 and
                        (poem_lines[0] == "\"NO_POEM\"" or "NO_POEM" in poem_lines[0]))

            filtered_poems = [poem for poem in all_poems if not is_no_poem_entry(poem)]
            save_poems_to_json(filtered_poems, json_file)
            run_stats["total_poems"] = len(filtered_poems)

            # Call cleanup_poems.main() to generate the markdown file
            import cleanup_poems
            cleanup_poems.main()

    except Exception as e:
        error_msg = f"Error during execution: {str(e)}"
        print(error_msg)
        run_stats["errors"].append(error_msg)

    write_log_summary()

if __name__ == "__main__":
    print("Starting script...")
    print(f"GitHub token available: {bool(Config.GITHUB_TOKEN)}")
    main()
    print("Script completed.")
