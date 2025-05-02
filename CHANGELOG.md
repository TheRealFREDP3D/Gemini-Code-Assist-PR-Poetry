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

### Changed

- Improved poem detection accuracy
- Better error handling for API rate limits
- Updated documentation with new features
- Reorganized project structure for better maintainability

## [Future Plans]

- Web interface for browsing the collection
- Categorization and tagging of poems
- Statistics about poem frequency and patterns
- Support for other AI code assistants that generate poetry
