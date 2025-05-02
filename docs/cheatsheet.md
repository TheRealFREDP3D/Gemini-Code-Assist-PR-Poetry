# Basic usage with your repository
python get_new_flowers.py

# Search public repositories and preview results without saving
python get_new_flowers.py --search --max-repos=10 --dry-run

# Clear cache and check a specific repository
python get_new_flowers.py --owner="some-user" --repo="some-repo" --clear-cache

# Process many PRs without caching
python get_new_flowers.py --search --max-prs=500 --no-cache