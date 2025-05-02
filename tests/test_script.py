import os
import sys

print("Python version:", sys.version)
print("Current working directory:", os.getcwd())
print("Script arguments:", sys.argv)

# Test if we can import the required modules
try:
    import requests
    print("requests module imported successfully")
except ImportError as e:
    print("Failed to import requests:", e)

try:
    import git
    print("git module imported successfully")
except ImportError as e:
    print("Failed to import git:", e)

try:
    import dotenv
    print("dotenv module imported successfully")
except ImportError as e:
    print("Failed to import dotenv:", e)

# Test if we can load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    github_token = os.getenv("GITHUB_TOKEN")
    print("GitHub token available:", bool(github_token))
    if github_token:
        print("Token starts with:", github_token[:4] + "..." if len(github_token) > 4 else "")
except Exception as e:
    print("Error loading environment variables:", e)

# Test if we can make a simple GitHub API request
try:
    import requests
    headers = {
        "Authorization": f"token {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get("https://api.github.com/repos/TheRealFREDP3D/Making-BanditGUI/pulls?state=all", headers=headers)
    print("GitHub API response status:", response.status_code)
    print("Number of PRs found:", len(response.json()))
except Exception as e:
    print("Error making GitHub API request:", e)
