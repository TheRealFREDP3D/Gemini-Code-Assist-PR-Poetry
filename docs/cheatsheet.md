# Gemini Code Assist PR Poetry Cheatsheet

## Basic usage (replace placeholders)
```bash
python get_new_flowers.py <URL_TO_GITHUB_REPO> --model <MODEL_PROVIDER/MODEL_NAME>
```

## Example with specific repository and model
```bash
python get_new_flowers.py https://github.com/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry --model gemini/gemini-1.5-flash
```

## Specify maximum Pull Requests to check
```bash
python get_new_flowers.py <URL_TO_GITHUB_REPO> --model <MODEL_PROVIDER/MODEL_NAME> --max-prs 50
```

## Specify a different output JSON file
```bash
python get_new_flowers.py <URL_TO_GITHUB_REPO> --model <MODEL_PROVIDER/MODEL_NAME> --output my_poems.json
```
*(Note: The Markdown file will be named based on the JSON output file, e.g., `my_poems.md`)*

## Get help on command-line options
```bash
python get_new_flowers.py --help
```
