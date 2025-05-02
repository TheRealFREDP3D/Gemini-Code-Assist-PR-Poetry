# PullPal - GitHub Pull Request Conversation Tool

## Project Evolution

PullPal began as a utility script (`get-pr-conversations`) within the Gemini-Code-Assist-PR-Poetry project. After evaluating its functionality and potential, it became clear that this tool deserved to be a standalone project for the following reasons:

### Reasons for Separation

1. **Standalone Value**: PullPal provides complete functionality that's valuable on its own, independent of the poetry collection project.

2. **Broader Audience**: As a separate repository, it can attract users who need PR conversation fetching but aren't interested in poetry collection.

3. **Focused Development**: A dedicated repository allows for independent versioning, issue tracking, and feature roadmap.

4. **Reusability**: It can be imported as a dependency in multiple projects, including the original poetry collection project.

5. **Discoverability**: A separate repository with appropriate tags makes it easier for people to find when searching for GitHub API tools.

## Feature Overview

PullPal is a powerful utility for fetching and saving complete GitHub pull request conversations, including:

- PR details and metadata
- Issue comments
- Review comments
- Reviews with their states

The tool supports:
- Multiple output formats (Markdown and JSON)
- Fetching single PRs, multiple specific PRs, or the latest N PRs
- Customizable output directories and file naming
- Pagination handling for large PRs
- Comprehensive error handling

## Future Development

As a standalone project, PullPal can now evolve with:

- Additional output formats (CSV, HTML, etc.)
- Enhanced filtering options
- Visualization capabilities
- Batch processing features
- Integration with other GitHub tools and workflows

This separation allows both projects to focus on their core purposes while maintaining a connection through documentation and potential integration.
