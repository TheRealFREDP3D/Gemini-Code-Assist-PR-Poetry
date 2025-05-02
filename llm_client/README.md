# LLM Client Directory

This directory contains various LLM client implementations that can be used by the poem extraction script when the primary models encounter rate limits or other errors.

## Available Clients

The following client implementations are available:

1. **gpt-4.1-github-client.py** - Uses Azure AI Inference to access the GitHub-hosted GPT-4.1 model
2. **gpt-4o-client.py** - Uses OpenAI API to access the GPT-4o model
3. **deepseek-v3-client.py** - Uses Azure AI Inference to access the DeepSeek v3 model
4. **llama-3.1-8b-inst-client.py** - Uses Azure AI Inference to access the Llama 3.1 8B Instruct model
5. **llama4-maverik-client.py** - Uses Azure AI Inference to access the Llama 4 Maverik model
6. **mistral-large-client.py** - Uses Mistral AI API to access the Mistral Large model
7. **phi4-client.py** - Uses Azure AI Inference to access the Phi-4 model

## Custom LLM Models

In addition to the client implementations, you can also define custom LiteLLM models in the `custom_llm_model.json` file. These models will be tried before falling back to the client implementations.

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

1. **Primary Model**: github/gpt-4.1
2. **Fallback Model**: github/gpt-4o
3. **Custom LiteLLM Models**: Models defined in `custom_llm_model.json`
4. **Client Implementations**: Python client implementations in this directory

For Ollama models, the script will check if the Ollama server is running before attempting to use them. If the server is not running, these models will be skipped.

## Adding New Models

To add a new custom LiteLLM model, simply add it to the `litellm_models` array in the `custom_llm_model.json` file.

To add a new client implementation, create a new Python file in this directory that follows the same pattern as the existing clients. The script will automatically detect and use it when needed.
