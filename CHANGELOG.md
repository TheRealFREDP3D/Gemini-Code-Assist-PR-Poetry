# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-05-02

### Added

- Initial collection of Gemini Code Assist poems in `gem-flowers.md`
- Basic README explaining the project

## [1.1.0] - 2025-05-03

### Added

- `get_new_flowers.py` script for automated poem collection
- Support for collecting poems from the main repository
- LIFO ordering (newest poems at the top)
- Duplicate detection to avoid adding the same poem twice

## [1.2.0] - 2025-05-03

### Added

- Multi-repository support in `get_new_flowers.py`
- Command-line arguments for customization
- Repository attribution for each poem
- Rate limiting to respect GitHub API limits

## [1.3.0] - 2025-05-03

### Added

- Caching system to remember processed PRs
- Support for collecting poems from PR reviews (not just comments)
- Rich metadata including PR title and date
- Progress tracking with `tqdm`
- Dry run mode to preview changes
- Better error handling and user feedback

### Changed

- Improved link formatting
- Better console output for monitoring long-running searches
- Updated README with usage instructions

## [1.4.0] - 2025-05-04

### Added

- LLM integration for poem detection using LiteLLM
- Support for multiple LLM providers (OpenAI, Azure, Gemini, Ollama)
- Automatic fallback to alternative models when rate limits are encountered
- Comprehensive logging system with log rotation
- JSON format for easier programmatic access to poems
- PR conversation fetcher utility in `utils/get-pr-conversations/`
  - Fetches complete PR conversations including comments, reviews, and details
  - Supports Markdown and JSON output formats
  - Uses GitHub token from `.env` file
  - Can fetch single PR, multiple PRs, or latest PRs

### Changed

- Improved poem detection accuracy
- Better error handling for API rate limits
- Updated documentation with new features
- Reorganized project structure for better maintainability

## [1.4.1] - 2025-05-05

### Changed

- Updated poem formatting in `gem-flowers.md` to remove Markdown blockquote formatting (removed '>' prefix from each line)
- Modified code to exclude "NO_POEM" entries from the markdown file while preserving them in the JSON file
- Updated both `get_new_flowers.py` and development utilities to maintain consistent formatting

## [1.4.2] - 2025-05-06

### Fixed

- Improved LLM fallback logic to properly track and exclude failed models
- Fixed JSON format issues in `custom_llm_model.json` to prevent parsing errors
- Enhanced client script handling with better prompt cleaning for newlines and escape quotes
- Added proper error tracking and logging for all model execution failures
- Fixed syntax errors in LLM client scripts when processing multi-line prompts
- Added system exit when all available LLM models have failed

### Changed

- Reorganized model fallback order: primary LiteLLM models → custom LiteLLM models → alternative client scripts
- Improved error messages to provide more context about failures
- Enhanced logging to track which models were tried and which failed

## [1.4.3] - 2025-05-07

### Added

- Interactive wizard mode with `--wizard` or `-w` flag to guide users through parameter setup
- Improved documentation for the wizard mode in README and cheatsheet

### Changed

- Updated help text to include information about the wizard mode
- Improved user experience for first-time users with guided parameter input

## [1.4.4] - 2025-05-08

### Changed

- Refactored `get_poem_with_client` function to improve code quality and maintainability
- Extracted helper functions for better separation of concerns:
  - `_handle_client_error` for centralized error handling
  - `_modify_client_code` for client-specific code modifications
  - `_execute_temp_client` for executing temporary client scripts
- Improved error handling with proper cleanup in finally blocks
- Enhanced code readability with f-strings and simplified conditionals
- Reduced function complexity score from F to B (from 51 to 6)

## [1.4.5] - 2025-05-09

### Added

- Added statistics table to the top of gem-flowers.md showing collection metrics
- Added similar statistics table to log files for consistency

### Changed

- Modified code to completely skip NO_POEM entries instead of just filtering them from markdown
- Improved NO_POEM detection to catch variations in the response format
- Updated both main script and development utilities to maintain consistent behavior

## [1.5.0] - 2025-05-10

### Added

- New modular architecture with core modules in `src/` directory:
  - `config.py` - Centralized configuration management
  - `error_handler.py` - Improved error handling with better recovery
  - `logger.py` - Enhanced logging with file rotation
  - `llm_client_template.py` - Standardized template for LLM clients
- Added run scripts for easier execution:
  - `run.sh` - Shell script for Linux/macOS
  - `run.bat` - Batch script for Windows
- Comprehensive documentation for the new architecture
- Fixed syntax errors in utility scripts and test files

### Changed

- Improved error handling with centralized error management
- Better configuration management with a dedicated class
- Enhanced logging with Python's built-in logging module
- Standardized LLM client implementations

## [1.5.1] - 2025-05-11

### Added

- Added `--ollama` command-line argument to use only local Ollama models for LLM processing
- Added Ollama-specific configuration in Config class
- Added `_try_ollama_models()` function to specifically try Ollama models
- Updated wizard mode to include Ollama option
- Added examples to README.md and cheatsheet.md for the new option

### Changed

- Simplified LLM fallback workflow with clearer separation of concerns
- Improved `is_ollama_running()` function to use the `requests` library instead of `curl`
- Enhanced response handling with better error handling and null checks
- Made response processing more robust across different LLM providers

### Fixed

- Fixed issues with attribute access in LLM response handling
- Improved error handling for Ollama-only mode
- Fixed potential issues with null responses

## [1.6.0-FINAL] - 2025-05-12

### Added

- Finalized project structure and organization
- Comprehensive documentation for all components
- Complete test coverage for core functionality

### Changed

- Pinned dependency versions for better reproducibility
- Improved error handling and recovery mechanisms
- Enhanced logging with more detailed information
- Standardized code formatting across all files

### Fixed

- Resolved all remaining issues with LLM client implementations
- Fixed edge cases in poem extraction and formatting
- Addressed potential security concerns with API handling

## [Future Plans]

- Web interface for browsing the collection
- Categorization and tagging of poems
- Statistics about poem frequency and patterns
- Support for other AI code assistants that generate poetry
