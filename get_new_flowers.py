import os
import re
import json
import requests
import importlib.util
import sys
from pathlib import Path
import git
import argparse
import time
from datetime import datetime
from dotenv import load_dotenv
import litellm
import glob
import subprocess

load_dotenv()

# Configure LiteLLM
litellm.api_key = os.getenv("GITHUB_TOKEN")
litellm.set_verbose = False

# LLM Fallback Mechanism
# -----------------------
# The script uses a multi-stage fallback mechanism for LLM models:
# 1. First tries PRIMARY_LITELLM_MODELS (github/gpt-4.1, github/gpt-4o)
# 2. If those fail, tries custom models from custom_llm_model.json
# 3. If those fail, tries client implementations in the llm_client directory
# 4. If all models fail, exits with an error

# List of available LLM client implementations in llm_client directory
LLM_CLIENTS = [
    "gpt-4.1-github-client.py",  # GitHub-hosted GPT-4.1 model
    "gpt-4o-client.py",         # GitHub-hosted GPT-4o model
    "deepseek-v3-client.py",    # DeepSeek V3 model
    "llama-3.1-8b-inst-client.py", # Llama 3.1 8B Instruct model
    "llama4-maverik-client.py", # Llama 4 Maverik model
    "mistral-large-client.py",  # Mistral Large model
    "phi4-client.py"            # Phi-4 model
]

# Keep track of which clients have been tried and failed to avoid retrying
failed_clients = []

# Keep track of which litellm models have been tried and failed to avoid retrying
failed_litellm_models = []

# Primary LiteLLM models to try in order before falling back to custom models
PRIMARY_LITELLM_MODELS = ["github/gpt-4.1", "github/gpt-4o"]

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
        # Try to make a request to the Ollama API
        result = subprocess.run(["curl", "-s", "http://localhost:11434/api/tags"],
                               capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and "models" in result.stdout
    except Exception:
        return False

# Configuration
# GitHub token for API access - can be set in .env file
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Default repository information
DEFAULT_REPO_OWNER = "TheRealFREDP3D"
DEFAULT_REPO_NAME = "Gemini-Code-Assist-PR-Poetry"

# Output files and directories
GEM_FLOWERS_FILE = "gem-flowers.json"  # Main JSON output file
LOGS_DIR = "logs"  # Directory for log files
MAX_LOG_SIZE_BYTES = 1024 * 1024  # 1MB - Maximum size for log files before rotation

# Bot name to look for in comments
BOT_NAME = "gemini-code-assist[bot]"

# Runtime statistics
run_stats = {
    "models_used": set(),
    "errors": [],
    "duplicates": [],
    "new_poems": 0,
    "total_poems": 0,
    "repositories_checked": set(),
    "prs_checked": 0
}

# GitHub API URLs
SEARCH_REPOS_URL = "https://api.github.com/search/repositories"
PR_LIST_URL = "https://api.github.com/repos/{owner}/{repo}/pulls"
PR_COMMENTS_URL = "https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
PR_REVIEW_COMMENTS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

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

def get_review_comments_for_pr(owner, repo, pr_number):
    """Fetch all review comments for a given PR."""
    url = PR_REVIEW_COMMENTS_URL.format(owner=owner, repo=repo, pr_number=pr_number)
    print(f"Fetching review comments from {url}")
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching review comments for PR #{pr_number} in {owner}/{repo}: {response.status_code}")
        return []

    reviews = response.json()
    print(f"Found {len(reviews)} reviews for PR #{pr_number}")

    review_comments = [
        {
            "body": review["body"],
            "user": review["user"],
            "html_url": review.get("html_url", ""),
        }
        for review in reviews
        if review.get("body")
        and review.get("user")
        and "bot" in review["user"].get("login", "")
    ]
    print(f"Found {len(review_comments)} review comments from bots for PR #{pr_number}")
    return review_comments

def load_client_module(client_filename):
    """Dynamically load a client module from the llm_client directory.

    Note: This function is not actually used in the current implementation.
    The client scripts are executed directly as separate processes instead of being imported.
    This is kept for potential future use.
    """
    try:
        client_path = os.path.join("llm_client", client_filename)
        module_name = os.path.splitext(client_filename)[0]

        # Use a simpler approach that doesn't rely on exec_module
        import importlib
        return importlib.import_module(f"llm_client.{module_name}")
    except Exception as e:
        print(f"Error loading module {client_filename}: {e}")
        return None

def _handle_client_error(error, client_filename, error_type=""):
    """Handle errors in client execution and log them appropriately."""
    error_prefix = error_type or "Error using client"
    error_msg = f"{error_prefix} {client_filename}: {error}"
    print(f"    {error_msg}")
    run_stats["errors"].append(error_msg)

    # Only add to failed_clients if not already there
    if client_filename not in failed_clients:
        failed_clients.append(client_filename)

    return None

def _modify_client_code(client_code, clean_prompt):
    """Modify client code to use our prompt based on the client type."""
    if "azure.ai.inference" in client_code:
        # Azure AI Inference client pattern
        return client_code.replace(
            'UserMessage("What is the capital of France?")',
            f'UserMessage("{clean_prompt}")'
        ).replace(
            'UserMessage("Can you explain the basics of machine learning?")',
            f'UserMessage("{clean_prompt}")'
        )
    elif "openai" in client_code:
        # OpenAI client pattern
        return client_code.replace(
            '"content": "What is the capital of France?"',
            f'"content": "{clean_prompt}"'
        )
    elif "mistralai" in client_code:
        # Mistral client pattern
        return client_code.replace(
            'UserMessage("What is the capital of France?")',
            f'UserMessage("{clean_prompt}")'
        )
    return client_code  # Return original if no patterns match

def _execute_temp_client(temp_client_path):
    """Execute the temporary client and return its output."""
    return os.popen(f"python {temp_client_path}").read().strip()

def get_poem_with_client(prompt, client_filename):
    """Use a specific client to get a poem from the prompt."""
    print(f"    Trying to extract poem using client: {client_filename}")

    # Prepare file paths
    client_path = os.path.join("llm_client", client_filename)
    temp_client_path = os.path.join("llm_client", f"temp_{client_filename}")

    try:
        # Read the client file
        try:
            with open(client_path, 'r') as f:
                client_code = f.read()
        except FileNotFoundError as e:
            return _handle_client_error(e, client_filename, "Client file not found")

        # Clean up the prompt and modify client code
        # Replace newlines with spaces and escape quotes to prevent syntax errors
        clean_prompt = prompt.replace('\n', ' ').replace('"', '\\"')
        modified_code = _modify_client_code(client_code, clean_prompt)

        # Write the modified client to a temporary file
        with open(temp_client_path, 'w') as f:
            f.write(modified_code)

        # Execute the client and get result
        try:
            result = _execute_temp_client(temp_client_path)

            # Track model usage
            model_name = f"client:{client_filename}"
            run_stats["models_used"].add(model_name)

            print(f"    Client response: {result[:100] if result else 'No response'}...")

            # Return None for NO_POEM, otherwise return the result
            return None if not result or result == "NO_POEM" or "NO_POEM" in result else result

        except subprocess.CalledProcessError as e:
            return _handle_client_error(e, client_filename, "Client execution failed")

    except Exception as e:
        return _handle_client_error(e, client_filename, f"Unexpected error: {type(e).__name__}")

    finally:
        # Always clean up the temporary file
        if os.path.exists(temp_client_path):
            try:
                os.remove(temp_client_path)
            except Exception as e:
                print(f"    Warning: Could not remove temporary file {temp_client_path}: {e}")

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

def _handle_rate_limit(error_str, model_name):
    """Handle rate limit errors with exponential backoff."""
    rate_limit_error = True
    base_wait_time = 5  # Default wait time in seconds

    # Try to extract wait time from error message
    if wait_match := re.search(r"wait (\d+) seconds", error_str):
        base_wait_time = int(wait_match[1])

    # Apply exponential backoff based on how many times this model has failed
    # Count how many times this model appears in failed_litellm_models
    failure_count = failed_litellm_models.count(model_name)
    wait_time = base_wait_time * (2 ** failure_count)

    print(f"    Rate limit detected for {model_name}. Waiting {wait_time} seconds before retry.")
    time.sleep(wait_time)  # Actually wait here to respect rate limits

    return rate_limit_error, wait_time

def _try_primary_litellm_models(prompt):
    """Try to extract poem using primary LiteLLM models."""
    poem_text = None
    rate_limit_error = False
    wait_time = 0
    max_retries = 3  # Maximum number of retries per model

    # Try each primary model that hasn't failed yet
    for model_name in PRIMARY_LITELLM_MODELS:
        # Skip models that have failed too many times
        if failed_litellm_models.count(model_name) >= max_retries:
            print(f"    Skipping {model_name} - failed {max_retries} times")
            continue

        try:
            print(f"    Trying to extract poem using LiteLLM with {model_name}...")
            response = litellm.completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )

            # Track model usage
            run_stats["models_used"].add(model_name)

            poem_text = response.choices[0].message.content.strip()
            print(f"    LiteLLM response from {model_name}: {poem_text[:100]}...")

            # If we got a valid response, break the loop
            if poem_text and poem_text != "NO_POEM" and "NO_POEM" not in poem_text:
                break

        except Exception as e:
            error_str = str(e)
            error_msg = f"Error using {model_name}: {e}"
            print(f"    {error_msg}")
            run_stats["errors"].append(error_msg)

            # Add this model to the failed models list
            failed_litellm_models.append(model_name)

            # Check if it's a rate limit error
            if "rate limit" in error_str.lower() or "429" in error_str:
                rate_limit_error, wait_time = _handle_rate_limit(error_str, model_name)

    return poem_text, rate_limit_error, wait_time

def _try_custom_litellm_models(prompt):
    """Try to extract poem using custom LiteLLM models."""
    poem_text = None
    custom_models = load_custom_llm_models()
    max_retries = 3  # Maximum number of retries per model

    # Try each custom model that hasn't failed yet
    for model in custom_models:
        # Skip models that have failed too many times
        if failed_litellm_models.count(model) >= max_retries:
            print(f"    Skipping {model} - failed {max_retries} times")
            continue

        # Skip Ollama models if Ollama is not running
        if model.startswith("ollama/") and not is_ollama_running():
            print(f"    Skipping {model} - Ollama server is not running")
            continue

        try:
            print(f"    Trying custom LiteLLM model: {model}")
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )

            # Track model usage
            run_stats["models_used"].add(model)

            poem_text = response.choices[0].message.content.strip()
            print(f"    Custom model response: {poem_text[:100]}...")

            if poem_text and poem_text != "NO_POEM" and "NO_POEM" not in poem_text:
                break
        except Exception as e:
            error_str = str(e)
            error_msg = f"Error using custom model {model}: {e}"
            print(f"    {error_msg}")
            run_stats["errors"].append(error_msg)

            # Add this model to the failed models list
            failed_litellm_models.append(model)

            # Check if it's a rate limit error
            if "rate limit" in error_str.lower() or "429" in error_str:
                _, _ = _handle_rate_limit(error_str, model)  # We don't need to return these values here

    return poem_text

def _try_client_implementations(prompt):
    """Try to extract poem using client implementations."""
    poem_text = None

    for client in LLM_CLIENTS:
        if client in failed_clients:
            print(f"    Skipping client {client} - previously failed")
            continue

        try:
            client_poem = get_poem_with_client(prompt, client)
            if client_poem and client_poem != "NO_POEM":
                poem_text = client_poem
                break
        except Exception as e:
            error_msg = f"Error using client {client}: {e}"
            print(f"    {error_msg}")
            run_stats["errors"].append(error_msg)

            # Add this client to the failed clients list
            failed_clients.append(client)

    return poem_text

def _find_or_create_link(comment_body, lines):
    """Find an existing GitHub link or create a default one."""
    # Look for a GitHub link in the comment
    link_line = None
    for line in lines:
        stripped = line.strip()
        if "github.com" in stripped:
            link_line = stripped
            if not (link_line.startswith("<") and link_line.endswith(">")):
                link_line = f"<{link_line}>"
            break

    # If no GitHub link found, use a default link to the repository
    if not link_line:
        # Extract repository info from the comment if possible
        if repo_match := re.search(r"github\.com/([^/]+/[^/\s]+)", comment_body):
            repo_path = repo_match[1]
            link_line = f"<https://github.com/{repo_path}>"
        else:
            # Default link
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

def _check_all_models_failed():
    """Check if all available models have failed and exit if necessary."""
    custom_llm_models = load_custom_llm_models()
    if (len(failed_litellm_models) >= len(PRIMARY_LITELLM_MODELS) + len(custom_llm_models) and
        len(failed_clients) >= len(LLM_CLIENTS)):
        print("ERROR: All available LLM models have failed. Exiting program.")
        sys.exit(1)

def extract_poem_from_comment(comment_body):
    """Extract poem and link from a comment using LiteLLM with fallback to alternative clients."""
    if not comment_body:
        return (None, None)

    # First, try the traditional method
    lines = comment_body.strip().splitlines()
    poem_lines, link_line = _try_traditional_extraction(comment_body)
    if poem_lines and link_line:
        return (poem_lines, link_line)

    # Otherwise, try using LiteLLM to identify if there's a poem in the comment
    prompt = f"""
    Analyze the following GitHub comment and determine if it contains a poem or poetic content.
    If it does, extract ONLY the poem lines. If it doesn't contain a poem, return "NO_POEM".

    GitHub Comment:
    {comment_body}

    Extract ONLY the poem lines (if any):
    """

    # Try primary LiteLLM models
    poem_text, rate_limit_error, wait_time = _try_primary_litellm_models(prompt)

    # Check if we need to try other models
    def is_no_poem(text):
        return not text or text == "NO_POEM" or "NO_POEM" in text

    # If primary models failed or returned NO_POEM, try custom LiteLLM models
    if is_no_poem(poem_text):
        poem_text = _try_custom_litellm_models(prompt)

    # If custom models failed or returned NO_POEM, try alternative clients
    if is_no_poem(poem_text):
        poem_text = _try_client_implementations(prompt)

    # If all models and clients failed, exit with appropriate message
    if is_no_poem(poem_text):
        if rate_limit_error:
            print(f"    All LLM models and clients failed or rate limited. Need to wait {wait_time} seconds.")
        else:
            print("    All LLM models and clients failed.")

        # If all models have failed, exit the program
        _check_all_models_failed()
        return (None, None)

    # Process the response
    try:
        return _process_llm_response(poem_text, comment_body, lines)
    except Exception as e:
        print(f"    Error processing LLM response: {e}")
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

def _process_gemini_comment(comment, owner, repo, pr_number, comment_type="comment"):
    """Process a comment from Gemini Code Assist to extract poems."""
    print(f"    Found {comment_type} from Gemini Code Assist: {comment['user']['login']}")
    poem_lines, link = extract_poem_from_comment(comment["body"])

    if not (poem_lines and link):
        print(f"    No poem found in {comment_type} from {comment['user']['login']}")
        return None

    # If the comment has a specific URL, use it (for reviews)
    if comment.get("html_url"):
        link = f"<{comment['html_url']}>"

    entry = create_poem_entry(poem_lines, link, owner, repo, pr_number)
    print(f"    Found poem in PR #{pr_number} from {comment_type}")
    return entry

def collect_poems_from_repo(owner, repo, max_prs=100):
    """Collect all poems from a specific repository."""
    poems = []
    print(f"Collecting poems from {owner}/{repo}...")

    prs = get_pull_requests(owner, repo)[:max_prs]  # Limit to max_prs
    print(f"Found {len(prs)} PRs in {owner}/{repo}")

    # Update PR statistics
    run_stats["prs_checked"] += len(prs)

    for pr in prs:
        pr_number = pr["number"]
        print(f"  Processing PR #{pr_number}...")

        # Check regular comments
        comments = get_comments_for_pr(owner, repo, pr_number)
        for comment in comments:
            print(f"    Comment from user: {comment['user']['login']}")
            # Check only for Gemini Code Assist comments
            if "gemini-code-assist" in comment["user"]["login"].lower():
                if entry := _process_gemini_comment(comment, owner, repo, pr_number):
                    poems.append(entry)

        # Check review comments
        reviews = get_review_comments_for_pr(owner, repo, pr_number)
        for review in reviews:
            print(f"    Review from user: {review['user']['login']}")
            # Check only for Gemini Code Assist reviews
            if "gemini-code-assist" in review["user"]["login"].lower():
                if entry := _process_gemini_comment(review, owner, repo, pr_number, "review"):
                    poems.append(entry)

        # Respect GitHub API rate limits
        time.sleep(0.5)

    return poems

def is_duplicate(new_poem, existing_poems):
    """Check if a poem is already in the collection."""
    new_link = new_poem.get("link", "")

    for poem in existing_poems:
        if poem.get("link", "") == new_link:
            # Add to duplicates list for logging
            run_stats["duplicates"].append({
                "link": new_link,
                "repository": new_poem.get("repository", ""),
                "pr_number": new_poem.get("pr_number", "")
            })
            return True

    return False

def get_next_log_file():
    """Get the next available log file name."""
    # Create logs directory if it doesn't exist
    os.makedirs(LOGS_DIR, exist_ok=True)

    # Check for existing log files
    existing_logs = glob.glob(os.path.join(LOGS_DIR, "log*.md"))

    if not existing_logs:
        return os.path.join(LOGS_DIR, "log.md")

    # Check if the latest log file is under the size limit
    latest_log = max(existing_logs, key=os.path.getctime)

    if os.path.getsize(latest_log) < MAX_LOG_SIZE_BYTES:
        return latest_log

    # Create a new log file with incremented number
    if latest_log == os.path.join(LOGS_DIR, "log.md"):
        return os.path.join(LOGS_DIR, "log1.md")

    # Extract number from log file name
    base_name = os.path.basename(latest_log)
    num = int(base_name[3:-3]) + 1
    return os.path.join(LOGS_DIR, f"log{num}.md")

def _write_errors_to_log(file_handle):
    """Write errors to the log file."""
    if run_stats["errors"]:
        file_handle.write("## Errors\n")
        for error in run_stats["errors"]:
            file_handle.write(f"- {error}\n")
        file_handle.write("\n")

def write_log_summary():
    """Write a summary of the run to the log file."""
    log_file = get_next_log_file()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"# Run Summary - {timestamp}\n\n")

        # Write configuration
        f.write("## Configuration\n")
        f.write(f"- Repository: {run_stats['repositories_checked']}\n")
        f.write(f"- PRs checked: {run_stats['prs_checked']}\n\n")

        # Write statistics as a table
        f.write("## Statistics\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Total Poems | {run_stats['total_poems']} |\n")
        f.write(f"| Repositories Scanned | {len(run_stats['repositories_checked'])} |\n")
        f.write(f"| PRs Scanned | {run_stats['prs_checked']} |\n")
        f.write(f"| New Poems (This Run) | {run_stats['new_poems']} |\n")
        f.write(f"| Duplicates Found | {len(run_stats['duplicates'])} |\n")
        f.write(f"| Last Updated | {timestamp} |\n\n")

        # Write models used
        f.write("## LLM Models Used\n")
        for model in run_stats["models_used"]:
            f.write(f"- {model}\n")
        f.write("\n")

        # Write duplicates
        if run_stats["duplicates"]:
            f.write("## Duplicates Found\n")
            for dup in run_stats["duplicates"]:
                f.write(f"- {dup['repository']} PR #{dup['pr_number']}: {dup['link']}\n")
            f.write("\n")

        # Write errors
        _write_errors_to_log(f)

        f.write("---\n\n")

def run_wizard(args):
    """Interactive wizard to prompt for parameter values."""
    print("\n=== Gemini Code Assist Poetry Collection Wizard ===\n")
    print("Press Enter to use default values or type a new value.\n")

    # Owner
    default_owner = args.owner
    user_input = input(f"GitHub repository owner [{default_owner}]: ").strip()
    args.owner = user_input or default_owner

    # Repo
    default_repo = args.repo
    user_input = input(f"GitHub repository name [{default_repo}]: ").strip()
    args.repo = user_input or default_repo

    # Search mode
    default_search = "yes" if args.search else "no"
    user_input = input(f"Search for public repositories with Gemini poems? (yes/no) [{default_search}]: ").strip().lower()
    args.search = user_input == "yes" if user_input else args.search

    # Max repos (only if search is enabled)
    if args.search:
        default_max_repos = args.max_repos
        user_input = input(f"Maximum number of repositories to search [{default_max_repos}]: ").strip()
        if user_input:
            try:
                args.max_repos = int(user_input)
            except ValueError:
                print(f"Invalid input. Using default value: {default_max_repos}")

    # Max PRs
    default_max_prs = args.max_prs
    user_input = input(f"Maximum number of PRs to check per repository [{default_max_prs}]: ").strip()
    if user_input:
        try:
            args.max_prs = int(user_input)
        except ValueError:
            print(f"Invalid input. Using default value: {default_max_prs}")

    # Output file
    default_output = args.output
    user_input = input(f"Output JSON file [{default_output}]: ").strip()
    args.output = user_input or default_output

    print("\n=== Configuration Summary ===")
    print(f"Repository: {args.owner}/{args.repo}")
    print(f"Search mode: {'Enabled' if args.search else 'Disabled'}")
    if args.search:
        print(f"Max repositories to search: {args.max_repos}")
    print(f"Max PRs to check: {args.max_prs}")
    print(f"Output file: {args.output}")
    print("\nStarting collection...\n")

    return args

def main():
    print("Starting Gemini Code Assist poem collection script")
    parser = argparse.ArgumentParser(description="Collect Gemini Code Assist poems from GitHub repositories")
    parser.add_argument("--owner", help="GitHub repository owner", default=DEFAULT_REPO_OWNER)
    parser.add_argument("--repo", help="GitHub repository name", default=DEFAULT_REPO_NAME)
    parser.add_argument("--search", help="Search for public repositories with Gemini poems", action="store_true")
    parser.add_argument("--max-repos", help="Maximum number of repositories to search", type=int, default=5)
    parser.add_argument("--max-prs", help="Maximum number of PRs to check per repository", type=int, default=100)
    parser.add_argument("--output", help="Output JSON file", default=GEM_FLOWERS_FILE)
    parser.add_argument("--wizard", "-w", help="Run in wizard mode to interactively set parameters", action="store_true")
    args = parser.parse_args()

    # Run the wizard if requested
    if args.wizard:
        args = run_wizard(args)

    print(f"Configuration: owner={args.owner}, repo={args.repo}, search={args.search}, max_repos={args.max_repos}, max_prs={args.max_prs}")
    print(f"GitHub token available: {bool(GITHUB_TOKEN)}")

    json_file = args.output
    new_poems = []

    try:
        if args.search:
            # Search for public repositories that might have Gemini Code Assist comments
            print("Searching for public repositories with Gemini Code Assist comments...")
            repos = search_public_repos(max_repos=args.max_repos)
            print(f"Found {len(repos)} repositories to check")

            for owner, repo in repos:
                run_stats["repositories_checked"].add(f"{owner}/{repo}")
                repo_poems = collect_poems_from_repo(owner, repo, args.max_prs)
                new_poems.extend(repo_poems)
                print(f"Collected {len(repo_poems)} poems from {owner}/{repo}")
        else:
            # Use the specified repository
            print(f"Checking specified repository: {args.owner}/{args.repo}")
            run_stats["repositories_checked"].add(f"{args.owner}/{args.repo}")
            repo_poems = collect_poems_from_repo(args.owner, args.repo, args.max_prs)
            new_poems.extend(repo_poems)
            print(f"Collected {len(repo_poems)} poems from {args.owner}/{args.repo}")

        # Load existing poems
        existing_poems = load_existing_poems(json_file)

        # Filter out duplicates
        unique_new_poems = [poem for poem in new_poems if not is_duplicate(poem, existing_poems)]

        # Update statistics
        run_stats["new_poems"] = len(unique_new_poems)
        run_stats["total_poems"] = len(existing_poems) + len(unique_new_poems)

        if not unique_new_poems:
            print("No new poems found.")
        else:
            # Add new poems to the front (LIFO)
            all_poems = unique_new_poems + existing_poems

            # Filter out NO_POEM entries before saving to JSON
            def is_no_poem_entry(poem):
                poem_lines = poem.get("poem", [])
                return (len(poem_lines) == 1 and
                        (poem_lines[0] == "\"NO_POEM\"" or "NO_POEM" in poem_lines[0]))

            filtered_poems = [poem for poem in all_poems if not is_no_poem_entry(poem)]

            # Save to JSON file
            save_poems_to_json(filtered_poems, json_file)

            # Update statistics after filtering
            run_stats["total_poems"] = len(filtered_poems)

            # Generate markdown file for human reading (optional)
            md_file = json_file.replace('.json', '.md')
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write("# Gemini Code Assist - PR Poetry\n\n")

                # Add statistics table at the top
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write("## Collection Statistics\n\n")
                f.write("| Metric | Value |\n")
                f.write("|--------|-------|\n")
                f.write(f"| Total Poems | {run_stats['total_poems']} |\n")
                f.write(f"| Repositories Scanned | {len(run_stats['repositories_checked'])} |\n")
                f.write(f"| PRs Scanned | {run_stats['prs_checked']} |\n")
                f.write(f"| New Poems (This Run) | {run_stats['new_poems']} |\n")
                f.write(f"| Duplicates Found | {len(run_stats['duplicates'])} |\n")
                f.write(f"| Last Updated | {timestamp} |\n\n")

                # Use the already filtered poems for the markdown file

                for poem in filtered_poems:
                    f.write("---\n\n")
                    # Ensure each line is written separately with proper formatting
                    for line in poem.get("poem", []):
                        # Preserve the original formatting but ensure consistent indentation
                        # Add two spaces at the beginning for consistent indentation
                        if line.strip():
                            # If the line doesn't start with spaces, add indentation
                            if not line.startswith(" "):
                                # Add two spaces at the end of each line for GitHub-flavored Markdown line breaks
                                f.write(f"  {line}  \n")
                            else:
                                # If it already has spaces, preserve them and add two spaces at the end
                                f.write(f"  {line}  \n")
                        else:
                            # For empty lines, just write a newline
                            f.write("\n")
                    f.write("\n")
                    f.write(f"  <{poem.get('link')}>\n")
                    f.write(f"  \n  _From: {poem.get('repository')}_\n\n")

    except Exception as e:
        error_msg = f"Error during execution: {str(e)}"
        print(error_msg)
        run_stats["errors"].append(error_msg)

    # Write log summary
    write_log_summary()

if __name__ == "__main__":
    print("Starting script...")
    print(f"GitHub token available: {bool(GITHUB_TOKEN)}")
    main()
    print("Script completed.")
