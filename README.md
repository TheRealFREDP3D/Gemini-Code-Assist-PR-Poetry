# Gemini Code Assist PR Poetry Scanner (v2)

> *"It's like a tiny flower growing on a big pile of snips."*

A rework of
[`TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry`](https://github.com/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry)
that, instead of scanning a single repo or randomly walking GitHub, **finds
repositories where the `gemini-code-assist[bot]` GitHub app actually
contributed** and harvests the poems it buried at the end of its PR review
comments.

---

## What changed vs. the original

| Area | Original (`get_new_flowers.py`) | This scanner (`scan_poems.py`) |
| :--- | :--- | :--- |
| **Repo selection** | Manual `--owner`/`--repo` or random GitHub search | Dynamic discovery via `commenter:gemini-code-assist[bot] is:pr`, ranked by stars, top N taken. Also supports `--repos` and `--user`. |
| **PR walk** | Lists every PR, walks every comment | Uses the discovery results to only fetch PRs the bot actually commented on (10x-100x fewer API calls) |
| **Poem detection** | LiteLLM call to Gemini per comment (requires API key, costs money) | Heuristic-first - finds poem section headers (`## ✨`, `## 🌸`, `## 📜`, etc.), tail blockquotes, and tail short-line clusters. Free, fast, no API key needed. Optional LiteLLM adjudication (`--llm-adjudicate`) for ambiguous comments. |
| **Time window** | No cutoff | Default cutoff `2026-07-17` - the day Google shut down the consumer Gemini Code Assist bot on GitHub. Only pre-cutoff PRs are scanned. |
| **Rate limiting** | Basic | Proper handling of primary + secondary GitHub rate limits, with sleep-until-reset. |

---

## Why July 17, 2026?

Google's [deprecation
notice](https://developers.google.com/gemini-code-assist/docs/deprecations/consumer-code-review)
for the **consumer** version of Gemini Code Assist on GitHub states:

> *Starting July 17, 2026, the consumer version is shut down, and all code
> review activities performed by the app end.*

That is the date the bot stopped posting poems. The scanner defaults to looking
only at PRs created on or before that date. Override with `--cutoff YYYY-MM-DD`
if you want a different window.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry
cd Gemini-Code-Assist-PR-Poetry

# 2. Install deps
pip install -r requirements.txt

# 3. Configure auth (REQUIRED for any real scan)
cp .env.example .env
# Edit .env and paste your GitHub token

# 4. Run with default top-5 dynamic discovery
./run.sh
```

Get a token at <https://github.com/settings/tokens> (classic PAT with
`public_repo` scope, or a fine-grained token with read-only access to public
repos). Without a token, GitHub caps you at 60 requests/hour.

---

## Usage

### Dynamic discovery (default)

Finds the top-5 most-starred repos where `gemini-code-assist[bot]` commented on
PRs, walks their pre-cutoff PR history, and extracts poems.

```bash
python scan_poems.py
python scan_poems.py --top 10        # take top 10 instead of 5
python scan_poems.py --min-prs 5     # only repos with >=5 bot-PRs
```

### User-supplied repos

Scan specific repos explicitly. Comma-separated, full URLs accepted.

```bash
python scan_poems.py --repos TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry,facebook/react
python scan_poems.py --repos https://github.com/vuejs/vue
```

### User-owned repos

Scan every public non-fork repo owned by a user.

```bash
python scan_poems.py --user TheRealFREDP3D
```

### Discovery-only mode

Just print the top-N candidate repos without scanning them.

```bash
python scan_poems.py --list-discovered --top 20
```

### Other useful flags

```bash
--cutoff 2025-12-31          # use a custom cutoff date
--max-prs-per-repo 100       # hard cap on PRs to walk per repo
--output-dir ./my-output     # write outputs somewhere else
--token ghp_xxx              # pass token on CLI instead of .env
--append                     # merge with existing output/poems.json
--preset serper_results.txt  # use pre-searched repos/PRs, skip GitHub search API
--crew                       # run CrewAI agent workflow (needs crewai + SERPER_API_KEY)
--serper-api-key KEY         # SERPER API key for crew Searcher agent
--crew-output-dir ./out      # output dir for crew workflow
--llm-adjudicate             # ask an LLM about ambiguous comments (needs litellm)
--model gemini/gemini-2.5-flash   # adjudication model
--adjudicate-threshold 0.5   # heuristic confidence that skips the LLM
--no-llm-cache               # disable the adjudication response cache
-v / --verbose               # DEBUG-level logging
```

### Optional LLM adjudication

Heuristic detection is the default and needs no API key. For comments where the
heuristics find nothing (or only a low-confidence candidate), you can ask an LLM
for a second opinion:

```bash
pip install litellm
export GEMINI_API_KEY=...          # or OPENAI_API_KEY, etc.
python scan_poems.py --llm-adjudicate
python scan_poems.py --llm-adjudicate --model gemini/gemini-2.5-flash \
    --adjudicate-threshold 0.5 --no-llm-cache
```

The model receives a tail region of the comment (not the whole body) and must
return a JSON object: `{"poem_found": bool, "lines": [...], "confidence":
0.0-1.0, "reason": "..."}`. Returned lines are re-scored by the heuristic gate
before being accepted, so a hallucinated prose block cannot enter the archive.
Responses are cached in `./cache/llm/adjudication_cache.json`, keyed by model +
comment hash. If `litellm` or a provider key is unavailable, the scanner logs a
warning and continues heuristic-only.

See [REVIEW.md](REVIEW.md) for the full analysis of the original LiteLLM-based
approach and why it was restructured.

### Avoiding GitHub search rate limits (SERPER pre-search)

GitHub's `/search/issues` endpoint (used by dynamic discovery) is rate-limited:
10 req/min unauthenticated, and it shares budget with other search calls. To
scan without touching GitHub search at all, pre-search with SERPER (or any web
search) and feed the results into `--preset`:

- Run a SERPER query for PRs where the bot commented, e.g.:

```text
site:github.com "gemini-code-assist[bot]" pullrequestreview
```

- Save the matching repo/PR URLs to a file, one per line:

```text
https://github.com/owner/repo/pull/123
https://github.com/other/repo/pull/456
owner/repo          # whole repo (all bot-PRs scanned)
```

- Scan using the preset file:

```bash
python scan_poems.py --preset serper_results.txt
```

This skips dynamic discovery and the GitHub search API entirely, consuming only
the per-PR REST calls (reviews/comments) which are far more generous.

### CrewAI agent workflow (Searcher → Analyst → Archivist)

For a fully LLM-orchestrated run, use CrewAI agents instead of the direct CLI
scan. This requires `crewai[tools]` and a `SERPER_API_KEY`:

```bash
pip install crewai[tools]
export SERPER_API_KEY=...
python scan_poems.py --crew
python scan_poems.py --crew --serper-api-key KEY --crew-output-dir ./crew-output
```

Three agents run sequentially:

1. **Searcher** - uses CrewAI's `SerperDevTool` to web-search for GitHub PRs
   where `gemini-code-assist[bot]` commented (e.g. `site:github.com
   "gemini-code-assist[bot]" pullrequestreview`), avoiding GitHub's rate-limited
   search API entirely.
2. **Analyst** - fetches the bot's comments from discovered PRs (reviews + issue
   comments) and runs poem extraction: heuristic first, optional LiteLLM
   adjudication as a second opinion for ambiguous comments.
3. **Archivist** - writes accepted poems to `poems.json` and `poems.md`, merging
   with any existing archive and deduplicating.

If `crewai` is not installed, `--crew` exits with a clear error. The default CLI
scan is unaffected and needs no LLM at all.

---

## How discovery works

GitHub's REST search endpoint supports the `commenter:` qualifier:

```text
GET /search/issues?q=commenter:gemini-code-assist[bot] is:pr&sort=updated&per_page=100
```

This returns every PR where the bot left at least one comment. The scanner walks
those results, buckets by repository, fetches each candidate repo's star count,
sorts by stars desc, and returns the top N. Each discovered repo also gets a
`sample_pr_numbers` list - those are the PRs we already know the bot commented
on, so we don't have to walk the whole PR history of the repo.

If the primary search returns nothing (e.g. the bot's comments were on private
repos, or the search index is being weird), we fall back to the broader
`involves:` query.

---

## How poem detection works

For each bot comment, the scanner tries three strategies in order:

1. **Header-anchored extraction.** Look for known poem-section headers the bot
   historically used:

    - `## ✨ Poem` / `## 🌸` / `## 📜` / `## 🎭` / `## 🪻` / `## 💐` / `## 🌷`
      / `## 🌻` / `## 🪷`
    - `## Poem`, `## Here's a poem`, `## Here is a poem`
    - `Here's a poem inspired by...`, `A poem inspired by...`
    - `**Extracted Poem Lines:**` / `**Poem:**` (bold-marker headers the bot
      sometimes used)
   Take the block of short non-empty lines that follows the header (until the
   next header, a horizontal rule, or a non-poetic line). Each line is
   normalized: leading `>` blockquote markers, `1.` / `-` list prefixes, and
   triple-backtick code-fence edges are all stripped (the bot sometimes wrapped
   poems in code fences or numbered the lines).

2. **Tail blockquote extraction.** If no header matched, find the last
   contiguous `>` blockquote in the comment and treat it as a candidate poem.

3. **Tail short-line cluster.** If neither of the above produced anything, take
   the last cluster of >=2 consecutive short lines (<=90 chars, no markdown list
   markers, no code fences, no URLs).

Each candidate is scored with `looks_like_poem()`:

1. +0.3 base
2. +up to 0.3 for line count
3. +up to 0.4 for end-rhyme density (last-2-3-chars suffix match between
   consecutive lines)
4. -reject if any normalized line matches a bad-line pattern (URL, image,
   `Signed-off-by:`, markdown header, bare code fence, etc.)

The highest-scoring candidate with confidence >= 0.15 wins.

---

## Output

Both files are written to `./output/` by default.

### `poems.md`

Human-readable Markdown archive grouped by repo -> PR. Each entry has the PR
title, link, comment URL, date, and the poem rendered as a blockquote.

```markdown
## facebook/react

### #12345 - Fix hydration mismatch in concurrent mode

- PR: [facebook/react#12345](https://github.com/facebook/react/pull/12345)
- Comment: [view on GitHub](https://github.com/facebook/react/pull/12345#pullrequestreview-...)
- Date: 2025-06-12T10:23:45Z

> _Detected via **header** (confidence 0.83, header `## ✨`)_

> A tree of nodes in sync,
> A render both fast and deep,
> Where memory and ink align,
> And children safely sleep.
```

### `poems.json`

Structured records for downstream processing:

```json
{
  "schema_version": 2,
  "generated_at": "2026-11-17T...",
  "count": 42,
  "poems": [
    {
      "repo": "facebook/react",
      "pr_number": 12345,
      "pr_title": "Fix hydration mismatch in concurrent mode",
      "pr_url": "https://github.com/facebook/react/pull/12345",
      "poem": "A tree of nodes in sync,\n...",
      "author": "gemini-code-assist[bot]",
      "created_at": "2025-06-12T10:23:45Z",
      "comment_url": "https://github.com/...",
      "comment_kind": "review",
      "detection_method": "header",
      "detection_header": "## ✨",
      "confidence": 0.83,
      "model": ""
    }
  ]
}
```

---

## Cleanup / deduplication

After several runs with `--append`, you may have duplicate poems. The bundled
`cleanup_poems.py` normalizes whitespace, drops near-duplicates (same text OR
same repo+PR+first-200-chars), and sorts the result.

```bash
python cleanup_poems.py
python cleanup_poems.py --input ./output/poems.json --output ./output/poems-clean.json
```

---

## Project layout

```text
gemini-poetry-scanner/
├── scan_poems.py          # main entry point - CLI, scanning loop
├── cleanup_poems.py       # deduplication + re-sort
├── run.sh / run.bat       # launcher scripts
├── requirements.txt
├── .env.example
├── README.md              # this file
├── REVIEW.md              # review of the original LiteLLM approach + plan
├── src/
│   ├── __init__.py
│   ├── config.py          # config loading from env / .env
│   ├── gh_client.py       # GitHub REST + GraphQL client, rate-limit aware
│   ├── llm_adjudicator.py # optional LiteLLM second opinion (JSON contract)
│   ├── repo_discovery.py  # find repos with gemini-code-assist[bot] activity
│   ├── poem_extractor.py  # heuristic poem detection (3 strategies)
│   └── output.py          # Markdown + JSON writers
├── output/                # generated poems.md + poems.json
├── cache/llm/             # adjudication response cache (if enabled)
└── logs/                  # scanner run logs (if configured)
```

---

## Limitations & notes

- **Heuristic-first detection.** The bot occasionally wrote poems without a
   clear header and without perfect rhyme - those are the cases
   `--llm-adjudicate` is for. The `confidence` field in the JSON tells you how
   sure the extractor was; anything < 0.3 is sketchy. Adjudication is opt-in:
   heuristic-only mode never needs an API key and stays the default.
- **GraphQL not used for PR listing.** The REST `/search/issues` endpoint is
   simpler and gives us all the info we need for discovery. Switching to GraphQL
   for the per-PR review/comments walk is a possible future optimization if rate
   limits become a problem.
- **The bot's username.** The scanner matches `gemini-code-assist`
   (case-insensitive substring) in the comment author login. This catches both
   `gemini-code-assist[bot]` (the app) and any workflow-run variants. If you
   find a different username in the wild, add it to `BOT_LOGIN_PATTERNS` in
   `src/config.py`.
- **Search API coverage.** GitHub's `/search/issues` endpoint only indexes PRs
   from the last few years and may miss very old ones. If you know a repo had
   the bot but discovery misses it, use `--repos owner/repo` to scan it directly
   -that path walks the full PR list.
- **Rate limits.** With a token (5,000 req/hr), a top-5 scan typically finishes
   in 5-30 minutes depending on how many bot comments each repo has. Without a
   token, expect hours-to-days.

---

## License

MIT, same as the original project.
