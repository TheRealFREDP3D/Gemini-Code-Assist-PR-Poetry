# Gemini Code Assist PR Poetry - Core Modules

This directory contains the core modules for the Gemini Code Assist PR Poetry collection script. These modules provide a modular architecture for better maintainability and extensibility.

## Module Overview

### `config.py`

The configuration module centralizes all configuration variables in one place for easier management. It includes:

- GitHub API configuration
- Default repository information
- Output file and directory settings
- LLM configuration
- HTTP request headers
- Runtime statistics template

### `error_handler.py`

The error handling module centralizes error handling logic for better consistency and maintainability. It includes:

- API error handling
- LiteLLM error handling
- Client error handling
- Rate limit handling with exponential backoff
- Error logging to file

### `logger.py`

The logging module provides a centralized logging system with file rotation. It includes:

- Console logging
- File logging with rotation
- Run summary generation

### `llm_client_template.py`

The LLM client template provides a standard structure for all LLM clients to follow. It includes:

- Base abstract class for all LLM clients
- Concrete implementations for different LLM providers:
  - Azure AI Inference
  - OpenAI
  - Mistral
- Helper functions for client selection and management

## Usage

To use these modules in your code, import them as follows:

```python
from src.config import Config
from src.error_handler import ErrorHandler
from src.logger import PoemLogger
from src.llm_client_template import get_client_for_model, list_available_clients
```

Or import the entire package:

```python
import src
```

## Integration with Main Script

These modules are designed to be integrated with the main `get_new_flowers.py` script. The integration involves:

1. Replacing hardcoded configuration values with references to the `Config` class
2. Replacing scattered error handling with calls to the `ErrorHandler` class
3. Replacing custom log file handling with the `PoemLogger` class
4. Replacing individual client files with implementations based on the template
