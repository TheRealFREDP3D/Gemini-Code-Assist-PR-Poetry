"""
Configuration module for the Gemini Code Assist PR Poetry collection script.
This centralizes all configuration variables in one place for easier management.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for the Gemini Code Assist PR Poetry collection script."""

    # GitHub API configuration
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_API_URL = "https://api.github.com"
    SEARCH_REPOS_URL = f"{GITHUB_API_URL}/search/repositories"
    PR_LIST_URL = f"{GITHUB_API_URL}/repos/{{owner}}/{{repo}}/pulls"
    PR_COMMENTS_URL = f"{GITHUB_API_URL}/repos/{{owner}}/{{repo}}/issues/{{pr_number}}/comments"
    PR_REVIEWS_URL = f"{GITHUB_API_URL}/repos/{{owner}}/{{repo}}/pulls/{{pr_number}}/reviews"
    PR_REVIEW_COMMENTS_URL = f"{GITHUB_API_URL}/repos/{{owner}}/{{repo}}/pulls/{{pr_number}}/comments"

    # Default repository information
    DEFAULT_REPO_OWNER = "TheRealFREDP3D"
    DEFAULT_REPO_NAME = "Gemini-Code-Assist-PR-Poetry"

    # Output files and directories
    GEM_FLOWERS_FILE = "gem-flowers.json"  # Main JSON output file
    LOGS_DIR = "logs"  # Directory for log files
    MAX_LOG_SIZE_BYTES = 1024 * 1024  # 1MB - Maximum size for log files before rotation

    # Bot name to look for in comments
    BOT_NAME = "gemini-code-assist[bot]"

    # LLM configuration
    # The default LLM model to use if no model is specified at runtime.
    # This value is used as a fallback when the `--model` command-line argument is not provided.
    # To override the default, use the `--model` flag when running the application.
    DEFAULT_MODEL = "gemini/gemini-1.5-flash"
    LLM_CLIENTS_DIR = "llm_client"
    CUSTOM_LLM_MODEL_FILE = os.path.join(LLM_CLIENTS_DIR, "custom_llm_model.json")

    # Ollama configuration
    OLLAMA_API_URL = "http://localhost:11434"

    # LLM prompt configuration
    POEM_EXTRACTION_PROMPT = """
    Analyze the following GitHub comment and determine if it contains a poem or poetic content.
    If it does, extract ONLY the poem lines. If it doesn't contain a poem, return "NO_POEM".

    GitHub Comment:
    {comment_body}

    Extract ONLY the poem lines (if any):
    """

    # HTTP request headers
    @classmethod
    def get_headers(cls):
        """Get headers for GitHub API requests."""
        return {
            "Authorization": f"token {cls.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

    # Runtime statistics template
    @classmethod
    def get_initial_stats(cls):
        """Get initial runtime statistics dictionary."""
        return {
            "models_used": set(),
            "errors": [],
            "duplicates": [],
            "new_poems": 0,
            "total_poems": 0,
            "repositories_checked": set(),
            "prs_checked": 0
        }
