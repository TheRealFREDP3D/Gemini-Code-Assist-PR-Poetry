# System Context

## I am working on a software system with the following directory structure, architecture, and analyzed files:

## Directory Structure
```
Gemini-Code-Assist-PR-Poetry
├── docs
│   ├── drawio-diagrams
│   │   ├── overview-full.drawio
│   │   └── overview-min.drawio
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
│   ├── deepseek-v3-client.py
│   ├── gpt-4.1-github-client.py
│   ├── gpt-4o-client.py
│   ├── llama-3.1-8b-inst-client.py
│   ├── llama4-maverik-client.py
│   ├── mistral-large-client.py
│   ├── phi4-client.py
│   └── README.md
├── src
│   ├── __init__.py
│   ├── config.py
│   ├── error_handler.py
│   ├── llm_client_template.py
│   ├── logger.py
│   └── README.md
├── tests
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
├── gem-flowers.json
├── gem-flowers.md
├── get_new_flowers.py
├── LICENSE
├── README.md
├── requirements.txt
├── run.bat
└── run.sh

```

## Mermaid Diagram
```mermaid
graph TD

    1011["Developer/Operator<br>Human"]
    subgraph 1007["External Systems"]
        1022["GitHub API<br>External API"]
        1023["OpenAI API<br>External LLM Service"]
        1024["Azure AI Services<br>External LLM Service"]
        1025["Mistral AI API<br>External LLM Service"]
        1026["Ollama Service (Optional)<br>Local LLM Service"]
    end
    subgraph 1008["Gemini-Code-Assist-PR-Poetry System"]
        1019["Poem Data Store<br>JSON Files Container"]
        1020["Log Data Store<br>Log Files Container"]
        1021["Poem Data Management Utility<br>Python Script Container"]
        subgraph 1009["Poem Extraction Application<br>Python Application Container"]
            1012["Poem Extraction Orchestrator<br>Python Component"]
            1013["GitHub Interaction Service<br>Python Component"]
            1014["LLM Gateway<br>Python Component"]
            1017["Poem Processing Service<br>Python Component"]
            1018["Application Support Services<br>Python Component"]
            subgraph 1010["LLM Client Subsystem"]
                1015["LLM Client Framework Base<br>Python Component"]
                1016["Specific LLM Client Implementations<br>Python Component"]
            end
            %% Edges at this level (grouped by source)
            1012["Poem Extraction Orchestrator<br>Python Component"] -->|coordinates with| 1013["GitHub Interaction Service<br>Python Component"]
            1012["Poem Extraction Orchestrator<br>Python Component"] -->|invokes| 1017["Poem Processing Service<br>Python Component"]
            1012["Poem Extraction Orchestrator<br>Python Component"] -->|uses| 1018["Application Support Services<br>Python Component"]
            1017["Poem Processing Service<br>Python Component"] -->|requests LLM analysis via| 1014["LLM Gateway<br>Python Component"]
            1014["LLM Gateway<br>Python Component"] -->|loads and uses custom| 1016["Specific LLM Client Implementations<br>Python Component"]
        end
        %% Edges at this level (grouped by source)
        1021["Poem Data Management Utility<br>Python Script Container"] -->|manages poems in| 1019["Poem Data Store<br>JSON Files Container"]
        1012["Poem Extraction Orchestrator<br>Python Component"] -->|writes poems to| 1019["Poem Data Store<br>JSON Files Container"]
        1018["Application Support Services<br>Python Component"] -->|writes logs to| 1020["Log Data Store<br>Log Files Container"]
    end
    %% Edges at this level (grouped by source)
    1011["Developer/Operator<br>Human"] -->|runs & configures| 1012["Poem Extraction Orchestrator<br>Python Component"]
    1011["Developer/Operator<br>Human"] -->|runs| 1021["Poem Data Management Utility<br>Python Script Container"]
    1014["LLM Gateway<br>Python Component"] -->|uses LiteLLM to call| 1023["OpenAI API<br>External LLM Service"]
    1014["LLM Gateway<br>Python Component"] -->|uses LiteLLM to call| 1024["Azure AI Services<br>External LLM Service"]
    1014["LLM Gateway<br>Python Component"] -->|uses LiteLLM to call| 1025["Mistral AI API<br>External LLM Service"]
    1014["LLM Gateway<br>Python Component"] -->|uses LiteLLM/direct to call| 1026["Ollama Service (Optional)<br>Local LLM Service"]
    1013["GitHub Interaction Service<br>Python Component"] -->|fetches data from| 1022["GitHub API<br>External API"]
    1016["Specific LLM Client Implementations<br>Python Component"] -->|make API calls to| 1023["OpenAI API<br>External LLM Service"]
    1016["Specific LLM Client Implementations<br>Python Component"] -->|make API calls to| 1024["Azure AI Services<br>External LLM Service"]
    1016["Specific LLM Client Implementations<br>Python Component"] -->|make API calls to| 1025["Mistral AI API<br>External LLM Service"]

```

## Analyzed Files

