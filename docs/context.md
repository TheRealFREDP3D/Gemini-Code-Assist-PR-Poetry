# System Context

## I am working on a software system with the following directory structure, architecture, and analyzed files:

## Directory Structure
```
Gemini-Code-Assist-PR-Poetry
├── docs
│   ├── drawio-diagrams
│   │   ├── overview-full.drawio
│   │   ├── overview-min.drawio
│   │   └── v0.4.0-LLM-overview-full.drawio
│   ├── mermaid-diagrams
│   │   ├── diagram-rate-limiting.md
│   │   ├── diagram-sequences.md
│   │   ├── overview-full.md
│   │   └── overview-min.md
│   ├── podcast
│   │   └── DeepDive-Podcast-Gemini-Code-Assist-PR-Poetry-Collection.mp4
│   ├── post
│   │   └── dev.to.md
│   ├── reviews
│   │   ├── review-deepseek-v3.md
│   │   └── review-qwen3-235B.md
│   ├── tests-output
│   │   ├── terminal-log-all-fails-good-extration-gem-flowers.json
│   │   ├── terminal-log-all-fails-good-extration-gem-flowers.md
│   │   └── terminal-log-all-fails-good-extration.log
│   ├── cheatsheet.md
│   ├── context.md
│   ├── header.jpg
│   ├── output.jpg
│   ├── overview-basic.jpg
│   ├── overview-full.jpg
│   └── stats.jpg
├── llm_client
│   ├── custom_llm_model.json
│   └── README.md
├── src
│   ├── __init__.py
│   ├── config.py
│   ├── error_handler.py
│   ├── llm_client_template.py
│   ├── logger.py
│   └── README.md
├── tests
│   ├── test_llm_client_template.py
│   ├── test_poem_extraction.py
│   └── test_script.py
├── utils
│   ├── PullPal-env-sample
│   ├── PullPal-gitignore
│   ├── PullPal-init.py
│   ├── PullPal-LICENSE
│   ├── PullPal-README.md
│   ├── PullPal-review.md
│   ├── PullPal-setup.py
│   └── PullPal.py
├── CHANGELOG.md
├── cleanup_poems.py
├── gem-flowers.md
├── get_new_flowers.py
├── LICENSE
├── package-lock.json
├── README.md
├── requirements.txt
├── run.bat
├── run.sh
└── SECURITY.md

```

## Mermaid Diagram
```mermaid
graph TD

    1116["Poem Cleanup Script<br>Python"]
    1117["PR Fetcher Script<br>Python CLI"]
    1118["User<br>External Actor"]
    subgraph 1111["External Systems"]
        1119["GitHub API<br>GitHub"]
        1120["LLM APIs<br>LiteLLM, OpenAI, Azure, etc."]
    end
    subgraph 1112["Poem Processing System<br>Python"]
        1113["Poem Collector Script<br>Python"]
        1114["Core Logic Modules<br>Python"]
        1115["LLM Client Config<br>JSON"]
        %% Edges at this level (grouped by source)
        1113["Poem Collector Script<br>Python"] -->|uses| 1114["Core Logic Modules<br>Python"]
        1113["Poem Collector Script<br>Python"] -->|loads| 1115["LLM Client Config<br>JSON"]
    end
    %% Edges at this level (grouped by source)
    1118["User<br>External Actor"] -->|runs| 1113["Poem Collector Script<br>Python"]
    1118["User<br>External Actor"] -->|runs| 1116["Poem Cleanup Script<br>Python"]
    1118["User<br>External Actor"] -->|runs| 1117["PR Fetcher Script<br>Python CLI"]
    1113["Poem Collector Script<br>Python"] -->|fetches PR data from| 1119["GitHub API<br>GitHub"]
    1117["PR Fetcher Script<br>Python CLI"] -->|fetches PR data from| 1119["GitHub API<br>GitHub"]
    1114["Core Logic Modules<br>Python"] -->|calls| 1120["LLM APIs<br>LiteLLM, OpenAI, Azure, etc."]

```

## Analyzed Files

