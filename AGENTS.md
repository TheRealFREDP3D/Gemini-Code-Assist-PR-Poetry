# AGENTS.md

## What this is

A standalone Python CLI that discovers GitHub repos where
`gemini-code-assist[bot]` commented on PRs and extracts the poems it left in
review comments. Two entry points, no package installs, no tests, no CI.

## Commands

```bash
python scan_poems.py  # default: top-5 discovery scan (needs token, 5-30 min)
python scan_poems.py --list-discovered --top 20  # discovery-only, cheap way to verify changes
python scan_poems.py --preset serper_results.txt  # pre-searched repos/PRs, skips GitHub search API
python scan_poems.py --crew --serper-api-key KEY  # CrewAI agent workflow (needs crewai)
python scan_poems.py --llm-adjudicate --model gemini/gemini-2.5-flash  # optional LLM 2nd opinion
python cleanup_poems.py  # dedupe/re-sort output/poems.json
./run.sh / run.bat  # launchers: auto-activate .venv, auto-pip-install if missing
```

## Gotchas

- **Use `uv` + `.venv` for all Python work.** The repo is set up with a uv-managed
`.venv`. Use `uv venv .venv` to create it and `uv pip install --python .venv -r
requirements.txt` to install deps. The `run.sh` / `run.bat` launchers handle
this automatically. Do not use `pip` directly.
- **`scan_poems.py` and `cleanup_poems.py` both do `sys.path.insert(0, project_root)`
and import as `src.*`** — don't move them into `src/`, and don't convert to
relative imports there.
- **Never run a full default scan while developing.** It burns GitHub API quota
  and takes 5-30 minutes. Verify changes with `--list-discovered`, a single
  `--repos owner/repo`, or by unit-testing `src/poem_extractor.py` functions
  directly (pure string logic, no network).
- **A real scan requires `GITHUB_TOKEN` in `.env`** (copied from `.env.example`).
Without it GitHub caps at 60 req/hr. `.env` exists locally and is gitignored —
never commit it or echo the token.
- **Rate limiting lives in `src/gh_client.py`** (primary + secondary limits,
sleep-until-reset). Any new GitHub API call must go through that client, not raw
`requests`.
- **Two hardcoded constants in `src/config.py` encode domain knowledge**:
  `DEFAULT_CUTOFF_DATE = "2026-07-17"` (the day Google shut down the consumer
  bot — only PRs on/before it are scanned) and `BOT_LOGIN_PATTERNS` (add new
  bot usernames here, matched as case-insensitive substrings).
- Poem detection is heuristic-first: three strategies in `src/poem_extractor.py`
(header-anchored -> tail blockquote -> tail short-line cluster), scored by
`looks_like_poem()`, confidence >= 0.15 wins. Adding new poem-section headers
means updating `POEM_HEADERS` in `src/config.py`. The optional LiteLLM second
opinion lives in `src/llm_adjudicator.py` and is only active with
`--llm-adjudicate`; it needs `litellm` installed plus a provider API key, and
silently degrades to heuristic-only otherwise.
- **`litellm` is an optional dependency** (commented out in `requirements.txt`).
Never add it as a hard requirement; the default scan must work with no API keys.
- **The LLM adjudication cache (`cache/llm/adjudication_cache.json`) is generated
data** - keep it gitignored like `.env`, never commit it.
- `--append` merges into the existing `output/poems.json`; run `cleanup_poems.py`
afterwards to dedupe (dupes accumulate across appended runs).
- `.github/instructions/codacy.instructions.md` is a third-party VS Code/Codacy
MCP rule file and is intentionally listed in `.gitignore` — not a repo
instruction source; ignore it.
