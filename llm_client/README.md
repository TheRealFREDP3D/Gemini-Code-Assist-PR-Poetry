# LLM Client Directory

This directory contains information about how the poem extraction script interacts with various Large Language Models (LLMs).

## Client Logic

The core logic for interacting with different LLM providers is centralized in `src/llm_client_template.py`. This file includes:
- Base class `BaseLLMClient` for all client implementations.
- Specific client implementations such as `AzureLLMClient`, `OpenAILLMClient`, and `MistralLLMClient`.
- The `CLIENT_MAPPINGS` dictionary, which maps model name patterns to the appropriate client class.
- The `SUPPORTED_MODEL_NAMES` list, which defines all models the system can try to use via these clients.
- The factory function `get_client_for_model(model_name)` that returns a client instance for a given model name based on `CLIENT_MAPPINGS`.
- The `list_available_clients()` function, which lists all clients that can be instantiated based on `SUPPORTED_MODEL_NAMES`.

This centralized approach allows for consistent handling of different LLMs and simplifies adding support for new models that use existing client types or entirely new LLM providers.

## Custom LLM Models

In addition to the clients defined in `src/llm_client_template.py`, you can also define custom LiteLLM models in the `custom_llm_model.json` file. These models will be tried before falling back to the clients managed by `get_client_for_model`.

### Format

The `custom_llm_model.json` file should have the following format:

```json
{
  "litellm_models": [
    "provider/model-name",
    "provider/model-name",
    ...
  ]
}
```

### Available Models

The following models are currently defined:

1. **gemini/gemini-1.5-pro** - Google's Gemini 1.5 Pro model
2. **gemini/gemini-1.5-flash** - Google's Gemini 1.5 Flash model
3. **gemini/gemini-1.0-pro** - Google's Gemini 1.0 Pro model
4. **gemini/gemini-1.5-flash-8b** - Google's Gemini 1.5 Flash 8B model
5. **ollama/qwen2.5:1.5b** - Qwen 2.5 1.5B model via Ollama
6. **ollama/3.2:1b-instruct** - Llama 3.2 1B Instruct model via Ollama

## Fallback Mechanism

The poem extraction script will try models in the following order:

1. **Primary Model**: `github/gpt-4.1` (This is an example, the actual primary model might be configured elsewhere in the script)
2. **Fallback Model**: `github/gpt-4o` (This is an example, the actual fallback model might be configured elsewhere in the script)
3. **Custom LiteLLM Models**: Models defined in `custom_llm_model.json`.
4. **Supported Clients**: Models listed in `SUPPORTED_MODEL_NAMES` in `src/llm_client_template.py`, accessed via the `get_client_for_model` function.

For Ollama models, the script will check if the Ollama server is running before attempting to use them. If the server is not running, these models will be skipped.

## Adding New Models

There are two main ways to add support for new models:

1.  **Using Custom LiteLLM Models:**
    To add a new model that is supported by LiteLLM (and not already covered by the existing client logic), simply add its identifier to the `litellm_models` array in the `custom_llm_model.json` file. This is the simplest way to add support for many models.

2.  **Modifying Centralized Client Logic (`src/llm_client_template.py`):**
    *   **For models compatible with existing client types (Azure, OpenAI, Mistral):**
        If you want to add a new model name that can be served by one of the existing client classes (`AzureLLMClient`, `OpenAILLMClient`, `MistralLLMClient`), you should:
        1.  Add the model name string to the `SUPPORTED_MODEL_NAMES` list.
        2.  Ensure the `CLIENT_MAPPINGS` dictionary correctly maps this model name (either via its prefix or exact name) to the appropriate client class.
    *   **For models requiring a new client type (e.g., a new API provider):**
        1.  Create a new client class in `src/llm_client_template.py` that inherits from `BaseLLMClient` and implements the necessary methods (e.g., `extract_poem`).
        2.  Add the new model name(s) to the `SUPPORTED_MODEL_NAMES` list.
        3.  Update the `CLIENT_MAPPINGS` dictionary to include a pattern (startswith or exact) and the new client class for your new model(s).

This structured approach ensures that model support is managed consistently and the poem extraction script can leverage a wide range of LLMs.
