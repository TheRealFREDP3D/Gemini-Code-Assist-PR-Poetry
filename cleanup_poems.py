import json
import os
from datetime import datetime

def load_poems(json_file):
    """Load poems from JSON file."""
    if not os.path.exists(json_file):
        print(f"Error: {json_file} not found.")
        return []

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error: {json_file} contains invalid JSON.")
        return []

def save_poems(poems, json_file):
    """Save poems to JSON file."""
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(poems, f, indent=2)

def generate_markdown(poems, md_file):
    """Generate markdown file from poems."""
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("# Gemini Code Assist - PR Poetry\n\n")
        
        # Add statistics table at the top
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write("## Collection Statistics\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Total Poems | {len(poems)} |\n")
        
        # Count unique repositories
        repositories = set(poem.get("repository", "") for poem in poems)
        f.write(f"| Repositories Scanned | {len(repositories)} |\n")
        
        # Count unique PRs
        pr_count = len(set((poem.get("repository", ""), poem.get("pr_number", "")) for poem in poems))
        f.write(f"| PRs Scanned | {pr_count} |\n")
        f.write(f"| Last Updated | {timestamp} |\n\n")

        for poem in poems:
            f.write("---\n\n")
            # Ensure each line is written separately with proper formatting
            for line in poem.get("poem", []):
                # Preserve the original formatting but ensure consistent indentation
                # Add two spaces at the beginning for consistent indentation
                if line.strip():
                    # If the line doesn't start with spaces, add indentation
                    if not line.startswith(" "):
                        f.write(f"  {line}\n")
                    else:
                        # If it already has spaces, preserve them
                        f.write(f"  {line}\n")
                else:
                    # For empty lines, just write a newline
                    f.write("\n")
            f.write("\n")
            f.write(f"  <{poem.get('link')}>\n")
            f.write(f"  \n  _From: {poem.get('repository')}_\n\n")

def main():
    json_file = "gem-flowers.json"
    md_file = "gem-flowers.md"
    
    # Load existing poems
    all_poems = load_poems(json_file)
    print(f"Loaded {len(all_poems)} poems from {json_file}")
    
    # Filter out NO_POEM entries
    filtered_poems = [poem for poem in all_poems if not (
        len(poem.get("poem", [])) == 1 and (
            poem.get("poem", [""])[0] == "\"NO_POEM\"" or 
            "NO_POEM" in poem.get("poem", [""])[0]
        )
    )]
    
    # Also filter out entries where any line contains NO_POEM
    filtered_poems = [poem for poem in filtered_poems if not any(
        "NO_POEM" in line for line in poem.get("poem", [])
    )]
    
    print(f"Filtered out {len(all_poems) - len(filtered_poems)} NO_POEM entries")
    print(f"Remaining poems: {len(filtered_poems)}")
    
    # Save filtered poems back to JSON
    save_poems(filtered_poems, json_file)
    print(f"Saved {len(filtered_poems)} poems to {json_file}")
    
    # Generate markdown file
    generate_markdown(filtered_poems, md_file)
    print(f"Generated markdown file: {md_file}")

if __name__ == "__main__":
    main()
