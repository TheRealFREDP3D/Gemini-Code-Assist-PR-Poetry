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
litellm.set_verbose = True

# List of available LLM clients
LLM_CLIENTS = [
    "gpt-4.1-github-client.py",
    "gpt-4o-client.py",
    "deepseek-v3-client.py",
    "llama-3.1-8b-inst-client.py",
    "llama4-maverik-client.py",
    "mistral-large-client.py",
    "phi4-client.py"
]

# Keep track of which clients have been tried
tried_clients = []

# Keep track of which litellm models have been tried
tried_litellm_models = []

def load_custom_llm_models():
    """Load custom LLM models from the JSON file."""
    try:
        model_file = os.path.join("llm_client", "custom_llm_model.json")
        with open(model_file, 'r') as f:
            data = json.load(f)

        # Clean up the model names (remove trailing commas)
        models = [model.rstrip(',') for model in data.get("litellm_models", [])]
        return models
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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
DEFAULT_REPO_OWNER = "TheRealFREDP3D"
DEFAULT_REPO_NAME = "Gemini-Code-Assist-PR-Poetry"
GEM_FLOWERS_FILE = "gem-flowers.json"
BOT_NAME = "gemini-code-assist[bot]"
LOGS_DIR = "logs"
MAX_LOG_SIZE_BYTES = 1024 * 1024  # 1MB

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

    # Extract the body from each review
    review_comments = []
    for review in reviews:
        if review.get("body") and review.get("user") and "bot" in review["user"].get("login", ""):
            review_comments.append({
                "body": review["body"],
                "user": review["user"],
                "html_url": review.get("html_url", "")
            })

    print(f"Found {len(review_comments)} review comments from bots for PR #{pr_number}")
    return review_comments

def load_client_module(client_filename):
    """Dynamically load a client module from the llm_client directory."""
    client_path = os.path.join("llm_client", client_filename)
    module_name = os.path.splitext(client_filename)[0]

    spec = importlib.util.spec_from_file_location(module_name, client_path)
    if spec is None:
        raise ImportError(f"Could not find module {client_filename}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module

def get_poem_with_client(prompt, client_filename):
    """Use a specific client to get a poem from the prompt."""
    print(f"    Trying to extract poem using client: {client_filename}")

    try:
        # Modify the client file to use our prompt
        client_path = os.path.join("llm_client", client_filename)
        with open(client_path, 'r') as f:
            client_code = f.read()

        # Create a temporary modified version of the client
        temp_client_path = os.path.join("llm_client", f"temp_{client_filename}")

        # Replace the example prompt with our poem extraction prompt
        if "azure.ai.inference" in client_code:
            # Azure AI Inference client pattern
            client_code = client_code.replace(
                'UserMessage("What is the capital of France?")',
                'UserMessage("' + prompt.replace('"', '\\"') + '")'
            ).replace(
                'UserMessage("Can you explain the basics of machine learning?")',
                'UserMessage("' + prompt.replace('"', '\\"') + '")'
            )
        elif "openai" in client_code:
            # OpenAI client pattern
            client_code = client_code.replace(
                '"content": "What is the capital of France?"',
                '"content": "' + prompt.replace('"', '\\"') + '"'
            )
        elif "mistralai" in client_code:
            # Mistral client pattern
            client_code = client_code.replace(
                'UserMessage("What is the capital of France?")',
                'UserMessage("' + prompt.replace('"', '\\"') + '")'
            )

        # Write the modified client to a temporary file
        with open(temp_client_path, 'w') as f:
            f.write(client_code)

        # Execute the temporary client and capture its output
        result = os.popen(f"python {temp_client_path}").read().strip()

        # Clean up the temporary file
        os.remove(temp_client_path)

        # Track model usage
        model_name = f"client:{client_filename}"
        run_stats["models_used"].add(model_name)

        print(f"    Client response: {result[:100]}...")

        # Check if the result is a valid poem or NO_POEM
        if result == "NO_POEM":
            return None
        else:
            return result

    except Exception as e:
        print(f"    Error using client {client_filename}: {e}")
        return None

def extract_poem_from_comment(comment_body):
    """Extract poem and link from a comment using LiteLLM with fallback to alternative clients."""
    if not comment_body:
        return (None, None)

    # First, try the traditional method
    lines = comment_body.strip().splitlines()
    poem_lines = []
    link_line = None

    in_poem = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("> ") or (in_poem and stripped == ''):
            poem_lines.append(stripped)
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

    # Otherwise, try using LiteLLM to identify if there's a poem in the comment
    prompt = f"""
    Analyze the following GitHub comment and determine if it contains a poem or poetic content.
    If it does, extract ONLY the poem lines. If it doesn't contain a poem, return "NO_POEM".

    GitHub Comment:
    {comment_body}

    Extract ONLY the poem lines (if any):
    """

    # Try with primary model first (github/gpt-4.1)
    try:
        print("    Trying to extract poem using LiteLLM with github/gpt-4.1...")
        model_name = "github/gpt-4.1"
        response = litellm.completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )

        # Track model usage
        run_stats["models_used"].add(model_name)

        poem_text = response.choices[0].message.content.strip()
        print(f"    LiteLLM response: {poem_text[:100]}...")

    except Exception as e:
        error_msg = f"Error using github/gpt-4.1: {e}"
        print(f"    {error_msg}")
        run_stats["errors"].append(error_msg)
        # Check if it's a rate limit error
        rate_limit_error = False
        wait_time = 0
        if "rate limit" in str(e).lower() or "429" in str(e):
            rate_limit_error = True
            # Try to extract wait time
            wait_match = re.search(r"wait (\d+) seconds", str(e))
            if wait_match:
                wait_time = int(wait_match.group(1))

        # Try with fallback model (github/gpt-4o)
        try:
            print("    Trying fallback model github/gpt-4o...")
            model_name = "github/gpt-4o"
            response = litellm.completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )

            # Track model usage
            run_stats["models_used"].add(model_name)

            poem_text = response.choices[0].message.content.strip()
            print(f"    LiteLLM fallback response: {poem_text[:100]}...")

        except Exception as e2:
            error_msg = f"Error using fallback model github/gpt-4o: {e2}"
            print(f"    {error_msg}")
            run_stats["errors"].append(error_msg)

            # If both models failed, try custom LiteLLM models
            poem_text = None
            custom_models = load_custom_llm_models()

            # Try custom LiteLLM models first
            for model in custom_models:
                if model not in tried_litellm_models:
                    tried_litellm_models.append(model)

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

                        if poem_text and poem_text != "NO_POEM":
                            break
                    except Exception as e:
                        error_msg = f"Error using custom model {model}: {e}"
                        print(f"    {error_msg}")
                        run_stats["errors"].append(error_msg)

            # If custom models failed, try alternative clients
            if not poem_text or poem_text == "NO_POEM":
                for client in LLM_CLIENTS:
                    if client not in tried_clients:
                        tried_clients.append(client)
                        poem_text = get_poem_with_client(prompt, client)
                        if poem_text and poem_text != "NO_POEM":
                            break

            if not poem_text or poem_text == "NO_POEM":
                if rate_limit_error:
                    print(f"    All LLM models and clients failed or rate limited. Need to wait {wait_time} seconds.")
                else:
                    print("    All LLM models and clients failed.")
                return (None, None)

    # Process the response
    try:
        if poem_text == "NO_POEM":
            print("    No poem found by LLM")
            return (None, None)

        # Extract poem lines
        ai_poem_lines = poem_text.strip().splitlines()
        ai_poem_lines = [f"> {line}" for line in ai_poem_lines if line.strip()]

        # Look for a GitHub link in the comment
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
            repo_match = re.search(r"github\.com/([^/]+/[^/\s]+)", comment_body)
            if repo_match:
                repo_path = repo_match.group(1)
                link_line = f"<https://github.com/{repo_path}>"
            else:
                # Default link
                link_line = "<https://github.com/TheRealFREDP3D/Making-BanditGUI>"

        if ai_poem_lines:
            print(f"    Found poem using LLM with {len(ai_poem_lines)} lines")
            return (ai_poem_lines, link_line)

    except Exception as e:
        print(f"    Error processing LLM response: {e}")

    return (None, None)

def create_poem_entry(poem_lines, link, repo_owner, repo_name, pr_number):
    """Create a JSON-friendly poem entry."""
    # Clean up poem lines (remove '>' prefix and trim)
    cleaned_lines = [line[2:].strip() if line.startswith("> ") else line.strip() for line in poem_lines if line.strip()]

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
                print(f"    Found comment from Gemini Code Assist: {comment['user']['login']}")
                poem_lines, link = extract_poem_from_comment(comment["body"])
                if poem_lines and link:
                    entry = create_poem_entry(poem_lines, link, owner, repo, pr_number)
                    poems.append(entry)
                    print(f"    Found poem in PR #{pr_number} from regular comment")
                else:
                    print(f"    No poem found in comment from {comment['user']['login']}")

        # Check review comments
        reviews = get_review_comments_for_pr(owner, repo, pr_number)
        for review in reviews:
            print(f"    Review from user: {review['user']['login']}")
            # Check only for Gemini Code Assist reviews
            if "gemini-code-assist" in review["user"]["login"].lower():
                print(f"    Found review from Gemini Code Assist: {review['user']['login']}")
                poem_lines, link = extract_poem_from_comment(review["body"])
                if poem_lines and link:
                    # If the review has a specific URL, use it
                    if review.get("html_url"):
                        link = f"<{review['html_url']}>"
                    entry = create_poem_entry(poem_lines, link, owner, repo, pr_number)
                    poems.append(entry)
                    print(f"    Found poem in PR #{pr_number} from review")
                else:
                    print(f"    No poem found in review from {review['user']['login']}")

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

        # Write statistics
        f.write("## Statistics\n")
        f.write(f"- New poems found: {run_stats['new_poems']}\n")
        f.write(f"- Total poems in collection: {run_stats['total_poems']}\n")
        f.write(f"- Duplicates found: {len(run_stats['duplicates'])}\n\n")

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
        if run_stats["errors"]:
            f.write("## Errors\n")
            for error in run_stats["errors"]:
                f.write(f"- {error}\n")
            f.write("\n")

        f.write("---\n\n")

def main():
    print("Starting Gemini Code Assist poem collection script")
    parser = argparse.ArgumentParser(description="Collect Gemini Code Assist poems from GitHub repositories")
    parser.add_argument("--owner", help="GitHub repository owner", default=DEFAULT_REPO_OWNER)
    parser.add_argument("--repo", help="GitHub repository name", default=DEFAULT_REPO_NAME)
    parser.add_argument("--search", help="Search for public repositories with Gemini poems", action="store_true")
    parser.add_argument("--max-repos", help="Maximum number of repositories to search", type=int, default=5)
    parser.add_argument("--max-prs", help="Maximum number of PRs to check per repository", type=int, default=100)
    parser.add_argument("--output", help="Output JSON file", default=GEM_FLOWERS_FILE)
    args = parser.parse_args()

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

            # Save to JSON file
            save_poems_to_json(all_poems, json_file)

            # Generate markdown file for human reading (optional)
            md_file = json_file.replace('.json', '.md')
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write("# Gemini Code Assist - PR Poetry\n\n")

                for poem in all_poems:
                    f.write("---\n\n")
                    for line in poem.get("poem", []):
                        f.write(f"  > {line}\n")
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