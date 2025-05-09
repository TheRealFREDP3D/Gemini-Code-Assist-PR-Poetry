# System Context

## I am working on a software system with the following directory structure, architecture, and analyzed files:

## Directory Structure
```
Gemini-Code-Assist-PR-Poetry
├── docs
│   ├── podcast
│   │   ├── banditgui-description.mp3
│   │   └── Gemini Code Assist PR Poetry Collection.mp4
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
│   ├── diagram-rate-limiting.md
│   ├── diagram-sequences.md
│   ├── header.jpg
│   ├── output.jpg
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
└── run.sh

```

## Mermaid Diagram
```mermaid
graph TD

    2561["Developer/User<br>External Actor"]
    subgraph 2556["External Systems & Libraries"]
        2572["GitHub API<br>External Service"]
        2573["LiteLLM<br>Python Library"]
        subgraph 2557["LLM Provider Services"]
            2574["Azure AI Service<br>External API"]
            2575["OpenAI API<br>External API"]
            2576["Mistral AI API<br>External API"]
            2577["DeepSeek API<br>External API"]
            2578["Ollama<br>LLM Service"]
        end
        %% Edges at this level (grouped by source)
        2573["LiteLLM<br>Python Library"] -->|routes requests to| 2574["Azure AI Service<br>External API"]
        2573["LiteLLM<br>Python Library"] -->|routes requests to| 2575["OpenAI API<br>External API"]
        2573["LiteLLM<br>Python Library"] -->|routes requests to| 2576["Mistral AI API<br>External API"]
        2573["LiteLLM<br>Python Library"] -->|routes requests to| 2577["DeepSeek API<br>External API"]
        2573["LiteLLM<br>Python Library"] -->|routes requests to| 2578["Ollama<br>LLM Service"]
    end
    subgraph 2558["Gemini Code Assist Application System"]
        2562["Poem Collection Script<br>Python"]
        2563["Poem Data Processor Utility<br>Python"]
        2571["Test Suite<br>Python (unittest)"]
        subgraph 2559["Application Data (Local Storage)"]
            2569["Poem Data Store<br>JSON Files"]
            2570["Log Data Store<br>Text Files"]
        end
        subgraph 2560["Core Internal Modules"]
            2564["GitHub Interaction Module<br>Python"]
            2565["LLM Orchestration Module<br>Python"]
            2566["Custom LLM Clients<br>Python"]
            2567["Poem Extraction Module<br>Python"]
            2568["Data Persistence Module<br>Python"]
            %% Edges at this level (grouped by source)
            2567["Poem Extraction Module<br>Python"] -->|processes LLM output from| 2565["LLM Orchestration Module<br>Python"]
            2565["LLM Orchestration Module<br>Python"] -->|delegates LLM calls via| 2566["Custom LLM Clients<br>Python"]
        end
        %% Edges at this level (grouped by source)
        2562["Poem Collection Script<br>Python"] -->|uses| 2564["GitHub Interaction Module<br>Python"]
        2562["Poem Collection Script<br>Python"] -->|uses| 2565["LLM Orchestration Module<br>Python"]
        2562["Poem Collection Script<br>Python"] -->|uses| 2567["Poem Extraction Module<br>Python"]
        2562["Poem Collection Script<br>Python"] -->|uses| 2568["Data Persistence Module<br>Python"]
        2563["Poem Data Processor Utility<br>Python"] -->|reads/writes poem data to/from| 2569["Poem Data Store<br>JSON Files"]
        2568["Data Persistence Module<br>Python"] -->|writes/reads poem data to/from| 2569["Poem Data Store<br>JSON Files"]
        2568["Data Persistence Module<br>Python"] -->|writes log data to| 2570["Log Data Store<br>Text Files"]
    end
    %% Edges at this level (grouped by source)
    2561["Developer/User<br>External Actor"] -->|runs| 2562["Poem Collection Script<br>Python"]
    2561["Developer/User<br>External Actor"] -->|runs| 2563["Poem Data Processor Utility<br>Python"]
    2561["Developer/User<br>External Actor"] -->|may run PullPal.py utility via| 2564["GitHub Interaction Module<br>Python"]
    2561["Developer/User<br>External Actor"] -->|runs| 2571["Test Suite<br>Python (unittest)"]
    2565["LLM Orchestration Module<br>Python"] -->|delegates LLM calls via| 2573["LiteLLM<br>Python Library"]
    2565["LLM Orchestration Module<br>Python"] -->|may directly use for local LLMs| 2578["Ollama<br>LLM Service"]
    2564["GitHub Interaction Module<br>Python"] -->|API calls to| 2572["GitHub API<br>External Service"]
    2566["Custom LLM Clients<br>Python"] -->|connects to Azure-hosted models via| 2574["Azure AI Service<br>External API"]
    2566["Custom LLM Clients<br>Python"] -->|connects to OpenAI models via| 2575["OpenAI API<br>External API"]
    2566["Custom LLM Clients<br>Python"] -->|connects to Mistral models via| 2576["Mistral AI API<br>External API"]

```

## Analyzed Files

