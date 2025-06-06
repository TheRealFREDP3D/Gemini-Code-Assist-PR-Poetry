# Gemini Code Assist PR Poetry

[Listen to the Podcast Deep Dive
having a conversation about this project](https://youtu.be/XEh26jsH-2g?si=yVaqn5TcBZhUaVzZ)

## Why?

When a Pull Request is created, the **Gemini Code Assist** app analyzes it and generates a detailed report.
But tucked at the end of that report… a surprising flourish:

A snippet of poetry — inspired by the PR itself.

It took me off guard. For a moment I wondered:
**"This is a weird feature… why?"**

I know it's weird...
But maybe weird is good.
Maybe it's beautiful.

---

📖 A growing collection of these poetry nuggets lives in [`gem-flowers.md`](./gem-flowers.md) and [`gem-flowers.json`](./gem-flowers.json).

💻 I made a tool to automatically collect these gems from a specified GitHub repository. Go try it out and start a collection of your own!

---

![Collection Stats](/docs/stats.jpg)

## 🌱 Contributing

Add your poetic PR discoveries to the collection and give a better home for these poetic snippets than their obscure Pull Request comments bottom lines. Give them some light and air.

I bet some gems will surface soon enough. ✨

### Automated Collection

You can use the provided script to automatically collect poems from a GitHub repository:

```bash
# Install dependencies
pip install requests litellm python-dotenv tqdm

# Run the Python script directly:
# Replace <URL_TO_GITHUB_REPO> with the actual repository URL.
# Replace <MODEL_PROVIDER/MODEL_NAME> with the LiteLLM model string (optional, defaults to gemini/gemini-1.5-flash).
python get_new_flowers.py <URL_TO_GITHUB_REPO> --model <MODEL_PROVIDER/MODEL_NAME>

# Example with a specific model and repository:
python get_new_flowers.py https://github.com/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry --model gemini/gemini-1.5-flash

# Other options:
# --max-prs : Maximum number of PRs to check (default: 100)
# --output : Output JSON file (default: gem-flowers.json)
# --model : Specify the LLM model to use (e.g., 'ollama/llama2', 'claude-3-haiku-20240307')

# See all options:
python get_new_flowers.py --help
```

### Configuration

The script requires a GitHub token and potentially API keys for your chosen LLM provider. These should be set as environment variables. You can place them in a `.env` file in the project root, and they will be loaded automatically.

**.env.example:**
```env
# Required: GitHub token for accessing repository data
GITHUB_TOKEN=your_github_token_here

# Optional: LLM Provider API Keys (handled by LiteLLM)
# LiteLLM will automatically look for standard environment variables for different providers.
# For example:
# GOOGLE_API_KEY=your_google_api_key_here (for Gemini models)
# OPENAI_API_KEY=your_openai_api_key_here
# ANTHROPIC_API_KEY=your_anthropic_api_key_here
# COHERE_API_KEY=your_cohere_api_key_here
# Add other keys as needed for your chosen provider.

# Optional LiteLLM Logging (uncomment to enable)
# LITELLM_LOGGING=True
# LITELLM_LOG=DEBUG
```
Refer to the [LiteLLM documentation](https://docs.litellm.ai/docs/providers) for details on environment variables for specific LLM providers.

### Key Features

- Collects poems from a user-specified GitHub repository via its URL.
- Adds new poems to the collection, avoiding duplicates based on comment links.
- Includes metadata about the source repository and PR.
- Uses a user-specified LLM model (via LiteLLM) to identify poems in comments.
- Logs detailed information about the collection process.
- Generates both Markdown and JSON output of the collected poems.

### Output Formats

- **Markdown**: Human-readable format in `gem-flowers.md` (automatically generated from the JSON).
- **JSON**: Machine-readable format in `gem-flowers.json`.

See [CHANGELOG.md](./CHANGELOG.md) for version history and updates.

## Project Structure

- `get_new_flowers.py` - Main script for collecting and processing poems.
- `gem-flowers.md` - Human-readable collection of poems.
- `gem-flowers.json` - Machine-readable collection of poems.
- `src/` - Core modules for the project
  - `config.py` - Configuration management
  - `error_handler.py` - Centralized error handling
  - `logger.py` - Logging system using `collection_activity.log` with rotation.
  - `llm_client_template.py` - Defines `LiteLLMClient` for LLM interaction.
- `logs/` - Contains `collection_activity.log` with detailed information about collection runs.
- `tests/` - Test scripts and utilities.
- `docs/` - Project documentation, diagrams, and related assets.

---

 *It's like a gorgeous tiny flower growing on a big pile of snips*
 — `\x02\xM4\xNY\xC0\xFF\x55`

---

## Visual Overview

![Visual Overview - Basic](docs/overview-basic.jpg)

---
