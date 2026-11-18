"""CrewAI-powered poem discovery, analysis, and archiving workflow.

This module provides an optional CrewAI-based alternative to the CLI scanner.
It assembles a three-agent crew:

* **Searcher** - uses CrewAI's SerperDevTool to pre-search GitHub for PRs
  commented on by `gemini-code-assist[bot]`, returning repo/PR specs.
* **Analyst** - fetches bot comments from those PRs and runs poem extraction
  (heuristic first, optional LiteLLM adjudication as second opinion).
* **Archivist** - writes accepted poems to `output/poems.json` and
  `output/poems.md` with full metadata.

Graceful degradation
--------------------
If `crewai` is not installed (e.g. Python 3.14 where tiktoken/PyO3 won't
build), importing this module still succeeds and `crew_available()` returns
False. The existing CLI scanner is unaffected.
"""

from __future__ import annotations

import logging
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

log = logging.getLogger("crew_agents")

# --------------------------------------------------------------------- #
# Optional CrewAI import
# --------------------------------------------------------------------- #
# Always defined so other modules can import it even when CrewAI is present.
_CREWAI_IMPORT_ERROR: Optional[Exception] = None
_CREWAI_AVAILABLE = False

try:
    from crewai import Agent, Crew, LLM, Process, Task
    from crewai.tools import BaseTool

    # CrewAI >= ~0.148 moved SerperDevTool into the separate crewai-tools
    # package; older CrewAI re-exported it from crewai.tools. Support both.
    try:
        from crewai_tools import SerperDevTool
    except Exception:  # pragma: no cover - older CrewAI
        from crewai.tools import SerperDevTool  # type: ignore[no-redef]

    _CREWAI_AVAILABLE = True
except Exception as exc:  # crewai not installed / incompatible Python
    _CREWAI_AVAILABLE = False
    _CREWAI_IMPORT_ERROR = exc
    Agent = Any  # type: ignore[assignment,misc]
    Crew = Any  # type: ignore[assignment,misc]
    LLM = Any  # type: ignore[assignment,misc]
    Process = Any  # type: ignore[assignment,misc]
    Task = Any  # type: ignore[assignment,misc]
    BaseTool = Any  # type: ignore[assignment,misc]
    SerperDevTool = Any  # type: ignore[assignment,misc]


def crew_available() -> bool:
    """True if CrewAI is importable and usable in this environment."""
    return _CREWAI_AVAILABLE


# --------------------------------------------------------------------- #
# Scanner integration (imported lazily so the module loads without them)
# --------------------------------------------------------------------- #
def _import_scanner():
    """Import scanner modules only when needed (keeps this module importable
    even if the scanner's own deps are missing)."""
    from src.config import Config, load_config
    from src.gh_client import GitHubClient
    from src.output import (
        PoemRecord,
        build_records,
        write_json,
        write_markdown,
        load_existing_json,
        merge_and_dedupe,
    )
    from src.poem_extractor import Comment, Poem, extract_poem, is_bot_comment
    return {
        "Config": Config,
        "load_config": load_config,
        "GitHubClient": GitHubClient,
        "PoemRecord": PoemRecord,
        "build_records": build_records,
        "write_json": write_json,
        "write_markdown": write_markdown,
        "load_existing_json": load_existing_json,
        "merge_and_dedupe": merge_and_dedupe,
        "Comment": Comment,
        "Poem": Poem,
        "extract_poem": extract_poem,
        "is_bot_comment": is_bot_comment,
    }


# --------------------------------------------------------------------- #
# Data contract between agents
# --------------------------------------------------------------------- #
@dataclass
class PRSpec:
    """A repository/PR discovered by the Searcher agent."""

    owner: str
    repo: str
    pr_number: Optional[int] = None
    source_url: str = ""
    confidence: float = 0.0


@dataclass
class PoemFinding:
    """A poem extracted by the Analyst agent."""

    repo: str
    pr_number: int
    pr_title: str
    pr_url: str
    poem_text: str
    author: str
    created_at: str
    comment_url: str
    comment_kind: str
    detection_method: str
    detection_header: str
    confidence: float
    model: str = ""


# --------------------------------------------------------------------- #
# CrewAI tools
# --------------------------------------------------------------------- #
class GitHubCommentFetcherTool(BaseTool if _CREWAI_AVAILABLE else object):  # type: ignore[misc,valid-type]
    """Fetch bot comments from a GitHub PR (reviews + issue comments)."""

    name: str = "github_comment_fetcher"
    description: str = (
        "Fetch all comments left by gemini-code-assist[bot] on a GitHub pull "
        "request. Input: 'owner/repo#pr_number'. Returns a list of comment "
        "bodies with metadata."
    )

    def __init__(self, config: Any, **kwargs: Any):
        super().__init__(**kwargs) if _CREWAI_AVAILABLE else None
        self._config = config
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        if self._client is None:
            scanner = _import_scanner()
            self._client = scanner["GitHubClient"](self._config)
        return self._client

    def _run(self, owner_repo_pr: str) -> str:  # type: ignore[override]
        import json

        # Parse "owner/repo#123"
        parts = owner_repo_pr.split("#")
        repo_spec = parts[0]
        pr_number = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        if "/" not in repo_spec:
            return json.dumps({"error": f"Invalid spec '{owner_repo_pr}'", "comments": []})
        owner, repo = repo_spec.split("/", 1)

        scanner = _import_scanner()
        comments: List[dict] = []

        try:
            if pr_number is not None:
                pr_specs = [(owner, repo, pr_number)]
            else:
                # Walk all PRs, newest first
                pr_specs = []
                for pr in self.client.list_pull_requests(owner, repo, state="all", direction="desc"):
                    pr_specs.append((owner, repo, int(pr["number"])))

            for o, r, pn in pr_specs:
                for review in self.client.list_reviews(o, r, pn):
                    author = (review.get("user") or {}).get("login", "")
                    if not scanner["is_bot_comment"](author, self._config):
                        continue
                    body = review.get("body") or ""
                    if not body.strip():
                        continue
                    comments.append(
                        {
                            "pr_number": pn,
                            "pr_title": review.get("pull_request", {}).get("title", ""),
                            "pr_url": review.get("html_url", ""),
                            "body": body,
                            "author": author,
                            "created_at": review.get("submitted_at") or review.get("created_at", ""),
                            "comment_url": review.get("html_url", ""),
                            "comment_kind": "review",
                        }
                    )
                for comment in self.client.list_issue_comments(o, r, pn):
                    author = (comment.get("user") or {}).get("login", "")
                    if not scanner["is_bot_comment"](author, self._config):
                        continue
                    body = comment.get("body") or ""
                    if not body.strip():
                        continue
                    comments.append(
                        {
                            "pr_number": pn,
                            "pr_title": comment.get("pull_request", {}).get("title", ""),
                            "pr_url": comment.get("html_url", ""),
                            "body": body,
                            "author": author,
                            "created_at": comment.get("created_at", ""),
                            "comment_url": comment.get("html_url", ""),
                            "comment_kind": "issue_comment",
                        }
                    )
        except Exception as exc:  # network / rate limit - report, don't crash
            log.warning("Comment fetch failed for %s: %s", owner_repo_pr, exc)
            return json.dumps({"error": str(exc), "comments": comments})

        return json.dumps({"error": "", "comments": comments})


class PoemExtractorTool(BaseTool if _CREWAI_AVAILABLE else object):  # type: ignore[misc,valid-type]
    """Run poem extraction (heuristic + optional LLM adjudication) on a comment."""

    name: str = "poem_extractor"
    description: str = (
        "Analyze a GitHub comment body and extract any poem written by "
        "gemini-code-assist[bot]. Input JSON: {'body': str, 'repo': str, "
        "'pr_number': int, 'pr_title': str, 'pr_url': str, 'author': str, "
        "'created_at': str, 'comment_url': str, 'comment_kind': str}. "
        "Returns a poem finding or {'poem_found': false}."
    )

    def __init__(self, config: Any, adjudicator: Any = None, **kwargs: Any):
        super().__init__(**kwargs) if _CREWAI_AVAILABLE else None
        self._config = config
        self._adjudicator = adjudicator

    def _run(self, comment_json: str) -> str:  # type: ignore[override]
        import json

        try:
            data = json.loads(comment_json)
        except json.JSONDecodeError:
            return json.dumps({"poem_found": False, "reason": "invalid JSON input"})

        body = data.get("body", "")
        if not body or not body.strip():
            return json.dumps({"poem_found": False, "reason": "empty body"})

        scanner = _import_scanner()
        poem = scanner["extract_poem"](body, self._config)

        # Optional LLM second opinion for weak/no heuristic hits
        if (poem is None or poem.confidence < self._config.adjudicate_threshold) and self._adjudicator is not None:
            verdict = self._adjudicator.adjudicate(body)
            if verdict is not None and verdict.poem_found:
                poem = scanner["Poem"](
                    text="\n".join(verdict.lines),
                    header="",
                    source_kind="llm",
                    confidence=verdict.confidence,
                    raw_excerpt=body[-400:],
                    model=verdict.model,
                )

        if poem is None:
            return json.dumps(
                {"poem_found": False, "reason": "no poem detected", "repo": data.get("repo", "")}
            )

        finding = {
            "poem_found": True,
            "repo": data.get("repo", ""),
            "pr_number": data.get("pr_number", 0),
            "pr_title": data.get("pr_title", ""),
            "pr_url": data.get("pr_url", ""),
            "poem_text": poem.text,
            "author": data.get("author", ""),
            "created_at": data.get("created_at", ""),
            "comment_url": data.get("comment_url", ""),
            "comment_kind": data.get("comment_kind", ""),
            "detection_method": poem.source_kind,
            "detection_header": poem.header,
            "confidence": poem.confidence,
            "model": poem.model,
        }
        return json.dumps(finding)


class ArchiveWriterTool(BaseTool if _CREWAI_AVAILABLE else object):  # type: ignore[misc,valid-type]
    """Archive poem findings to output/poems.json and output/poems.md."""

    name: str = "archive_writer"
    description: str = (
        "Append poem findings to the archive. Input JSON: a list of poem "
        "finding dicts (as produced by poem_extractor) plus 'output_dir'. "
        "Writes merged, deduplicated poems.json and poems.md."
    )

    def __init__(self, config: Any, **kwargs: Any):
        super().__init__(**kwargs) if _CREWAI_AVAILABLE else None
        self._config = config

    def _run(self, findings_json: str) -> str:  # type: ignore[override]
        import json

        try:
            payload = json.loads(findings_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "invalid JSON input", "written": 0})

        findings = payload.get("findings", [])
        output_dir = Path(payload.get("output_dir", str(self._config.output_dir)))

        scanner = _import_scanner()
        hits = []
        for f in findings:
            if not f.get("poem_found"):
                continue
            poem = scanner["Poem"](
                text=f["poem_text"],
                header=f.get("detection_header", ""),
                source_kind=f.get("detection_method", "llm"),
                confidence=float(f.get("confidence", 0.0)),
                model=f.get("model", ""),
            )
            comment = scanner["Comment"](
                body=f.get("poem_text", ""),
                author=f.get("author", ""),
                created_at=f.get("created_at", ""),
                pr_number=int(f.get("pr_number", 0)),
                pr_title=f.get("pr_title", ""),
                repo_full_name=f.get("repo", ""),
                comment_url=f.get("comment_url", ""),
                comment_kind=f.get("comment_kind", ""),
            )
            hits.append(type("PoemHit", (), {"poem": poem, "comment": comment})())

        new_records = scanner["build_records"](hits)

        # Merge with existing if present
        existing_path = output_dir / "poems.json"
        existing = scanner["load_existing_json"](existing_path)
        merged = scanner["merge_and_dedupe"](existing, new_records)
        merged.sort(key=lambda r: (r.repo, r.pr_number, r.created_at))

        output_dir.mkdir(parents=True, exist_ok=True)
        scanner["write_json"](merged, output_dir / "poems.json")
        scanner["write_markdown"](merged, output_dir / "poems.md")

        return json.dumps({"written": len(merged), "output_dir": str(output_dir)})


# --------------------------------------------------------------------- #
# Batch scanner tool (used when --repos/--user targets are given)
# --------------------------------------------------------------------- #
class RepoScannerTool(BaseTool if _CREWAI_AVAILABLE else object):  # type: ignore[misc,valid-type]
    """Deterministically scan a list of repos/PRs for poems.

    Unlike the per-repo GitHubCommentFetcherTool (which relies on the agent
    calling it once per target), this tool scans *all* targets in a single
    call so nothing is missed. Input JSON:
        {"targets": [{"owner": str, "repo": str, "pr_number": int|null}]}
    Returns a list of poem-finding dicts (as consumed by ArchiveWriterTool).
    """

    name: str = "repo_scanner"
    description: str = (
        "Scan GitHub repos/PRs for gemini-code-assist[bot] poems. "
        "Input JSON: {'targets': [{'owner': str, 'repo': str, "
        "'pr_number': int|null}]} . Returns a list of poem findings."
    )

    def __init__(self, config: Any, **kwargs: Any):
        super().__init__(**kwargs) if _CREWAI_AVAILABLE else None
        self._config = config

    def _run(self, input_json: str) -> str:  # type: ignore[override]
        import json

        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "invalid JSON input", "findings": []})

        targets = data.get("targets", [])
        if not targets:
            return json.dumps({"error": "no targets", "findings": []})

        # Lazy import to avoid circular import (scan_poems imports from src.crew_agents).
        from scan_poems import scan_repo, iso_to_epoch  # type: ignore

        config = self._config
        cutoff_epoch = iso_to_epoch(f"{config.cutoff_date}T23:59:59Z")

        scanner = _import_scanner()
        client = scanner["GitHubClient"](config)

        findings: List[dict] = []
        for owner, repo, pr_number in targets:
            try:
                sample_pr_numbers = [pr_number] if pr_number else None
                hits = scan_repo(
                    client,
                    config,
                    owner,
                    repo,
                    cutoff_epoch,
                    sample_pr_numbers=sample_pr_numbers,
                )
                for hit in hits:
                    poem = hit.poem
                    comment = hit.comment
                    findings.append(
                        {
                            "poem_found": True,
                            "repo": comment.repo_full_name,
                            "pr_number": comment.pr_number,
                            "pr_title": comment.pr_title,
                            "pr_url": comment.comment_url,
                            "poem_text": poem.text,
                            "author": comment.author,
                            "created_at": comment.created_at,
                            "comment_url": comment.comment_url,
                            "comment_kind": comment.comment_kind,
                            "detection_method": poem.source_kind,
                            "detection_header": poem.header,
                            "confidence": poem.confidence,
                            "model": poem.model,
                        }
                    )
            except Exception as exc:  # network / rate limit - report, don't crash
                log.warning("Repo scan failed for %s/%s: %s", owner, repo, exc)

        return json.dumps({"findings": findings})


# --------------------------------------------------------------------- #
# Agent factory
# --------------------------------------------------------------------- #
def build_crew(
    config: Any,
    *,
    serper_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    adjudicator: Any = None,
    repo_targets: Optional[List[Tuple[str, str, Optional[int]]]] = None,
    verbose: bool = True,
) -> Any:
    """Build the Searcher → Analyst → Archivist CrewAI crew.

    When ``repo_targets`` are provided (from ``--repos``/``--user``), the
    Searcher agent and web search are skipped and the Analyst works directly
    against the given repos/PRs. Otherwise the Searcher discovers targets via
    Serper web search.

    Returns None if crewai is unavailable.
    """
    if not _CREWAI_AVAILABLE:
        log.warning(
            "CrewAI is not available (%s). Install it to use the crew workflow.",
            _CREWAI_IMPORT_ERROR,
        )
        return None

    # Resolve the model to use: explicit arg > config (env/.env) > CrewAI default.
    llm_model = llm_model or getattr(config, "llm_model", None)
    crew_llm: Any = None
    if llm_model:
        # CrewAI `LLM` accepts model/base_url/api_key so we can point at a
        # custom endpoint (e.g. NVIDIA integrate: https://integrate.api.nvidia.com/v1).
        crew_llm = LLM(
            model=llm_model,
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            api_key=os.getenv("NVIDIA_API_KEY"),
        )
        log.info("CrewAI LLM configured: model=%s base_url=%s", llm_model, crew_llm.base_url)

    # --- Analyst agent ------------------------------------------------- #
    if repo_targets:
        scanner_tool = RepoScannerTool(config=config)
        analyst = Agent(
            role="PR Comment Poem Analyst",
            goal=(
                "Scan the given GitHub repos/PRs for gemini-code-assist[bot] "
                "comments and extract any poems, with confidence scoring."
            ),
            backstory=(
                "You read GitHub PR review comments left by the gemini-code-assist "
                "bot and identify poetic content. You use the repo scanner tool "
                "to fetch all comments from each target repo/PR and run the "
                "heuristic poem extractor on them."
            ),
            tools=[scanner_tool],
            allow_delegation=False,
            verbose=verbose,
            llm=crew_llm,
        )
    else:
        fetcher = GitHubCommentFetcherTool(config=config)
        extractor = PoemExtractorTool(config=config, adjudicator=adjudicator)
        analyst = Agent(
            role="PR Comment Poem Analyst",
            goal=(
                "Fetch gemini-code-assist[bot] comments from discovered PRs and "
                "extract any poems, with confidence scoring."
            ),
            backstory=(
                "You read GitHub PR review comments left by the gemini-code-assist "
                "bot and identify poetic content. You prefer the fast heuristic "
                "extractor and only call the LLM adjudicator for ambiguous cases."
            ),
            tools=[fetcher, extractor],
            allow_delegation=False,
            verbose=verbose,
            llm=crew_llm,
        )

    # --- Archivist agent ----------------------------------------------- #
    archivist_tool = ArchiveWriterTool(config=config)
    archivist = Agent(
        role="Poem Archivist",
        goal=(
            "Archive extracted poems to poems.json and poems.md with full "
            "metadata, deduplicating against previous runs."
        ),
        backstory=(
            "You maintain the permanent archive of recovered AI poetry. You "
            "write structured JSON and human-readable Markdown, deduplicate "
            "against existing entries, and preserve provenance."
        ),
        tools=[archivist_tool],
        allow_delegation=False,
        verbose=verbose,
        llm=crew_llm,
    )

    # --- Tasks ---------------------------------------------------------- #
    if repo_targets:
        # Honor explicit --repos/--user targets; skip web discovery.
        target_json = json.dumps(
            [{"owner": o, "repo": r, "pr_number": pn}
             for o, r, pn in repo_targets]
        )
        target_lines = "\n".join(
            f"  {owner}/{repo}#{pn}" if pn else f"  {owner}/{repo}"
            for owner, repo, pn in repo_targets
        )
        analyze_task = Task(
            description=(
                "Scan the following GitHub repositories/PRs for "
                "gemini-code-assist[bot] comments and extract any poems. "
                "Call the repo_scanner tool once with ALL targets as JSON input:\n"
                f"{target_json}\n\n"
                "Repositories/PRs to scan:\n"
                f"{target_lines}\n"
                "For specs without a PR number, the scanner walks all PRs in that repo."
            ),
            expected_output=(
                "A JSON list of poem findings, each with: repo, pr_number, "
                "pr_title, pr_url, poem_text, author, created_at, comment_url, "
                "comment_kind, detection_method, detection_header, confidence, model."
            ),
            agent=analyst,
        )
        crew = Crew(
            agents=[analyst, archivist],
            tasks=[analyze_task, archive_task := _make_archive_task(archivist, analyze_task, verbose)],
            process=Process.sequential,
            verbose=verbose,
        )
    else:
        # Default discovery path: Searcher → Analyst → Archivist via web search.
        if serper_api_key is None:
            serper_api_key = os.getenv("SERPER_API_KEY")
        if serper_api_key is None:
            log.warning(
                "SERPER_API_KEY not set. Searcher agent will not have web search."
            )

        # --- Search agent -------------------------------------------------- #
        serper_tool = SerperDevTool() if serper_api_key else None
        searcher = Agent(
            role="GitHub PR Discovery Searcher",
            goal=(
                "Find GitHub pull requests where gemini-code-assist[bot] left "
                "comments, using web search. Return repo/PR specs."
            ),
            backstory=(
                "You are an expert at finding AI-generated poetry hidden in GitHub "
                "PR reviews. You use web search to locate repositories where the "
                "gemini-code-assist bot has commented, without burning GitHub's "
                "rate-limited search API."
            ),
            tools=[serper_tool] if serper_tool else [],
            allow_delegation=False,
            verbose=verbose,
            llm=crew_llm,
        )

        search_task = Task(
            description=(
                "Use web search to find GitHub pull requests where "
                "gemini-code-assist[bot] has commented. Search queries like:\n"
                "  site:github.com \"gemini-code-assist[bot]\" pullrequestreview\n"
                "  site:github.com \"gemini-code-assist\" \"poem\" pull request\n"
                "Return a list of repo/PR specs in the form owner/repo#pr_number "
                "(or just owner/repo if no specific PR is known)."
            ),
            expected_output=(
                "A newline-separated list of repo/PR specs, e.g.:\n"
                "owner/repo#123\nother/repo#456\nthird/repo"
            ),
            agent=searcher,
        )

        analyze_task = Task(
            description=(
                "For each repo/PR spec from the search task, fetch the "
                "gemini-code-assist[bot] comments (reviews and issue comments) and "
                "extract poems. For each comment, run the poem extractor. If no "
                "poem is found or confidence is low, use the LLM adjudicator as a "
                "second opinion. Collect all poem findings."
            ),
            expected_output=(
                "A JSON list of poem findings, each with: repo, pr_number, "
                "pr_title, pr_url, poem_text, author, created_at, comment_url, "
                "comment_kind, detection_method, detection_header, confidence, model."
            ),
            agent=analyst,
            context=[search_task],
        )

        crew = Crew(
            agents=[searcher, analyst, archivist],
            tasks=[search_task, analyze_task, _make_archive_task(archivist, analyze_task, verbose)],
            process=Process.sequential,
            verbose=verbose,
        )
    return crew


def _make_archive_task(
    archivist: Any, analyze_task: Any, verbose: bool
) -> Any:
    """Factory for the Archivist task so it can be shared across crew shapes."""
    return Task(
        description=(
            "Take the poem findings from the analysis task and archive them: "
            "write poems.json and poems.md to the output directory, merging "
            "with any existing archive and deduplicating."
        ),
        expected_output=(
            "A confirmation of how many poems were written and the output "
            "directory path."
        ),
        agent=archivist,
        context=[analyze_task],
    )


def run_crew_workflow(
    config: Any,
    *,
    serper_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    adjudicator: Any = None,
    repo_targets: Optional[List[Tuple[str, str, Optional[int]]]] = None,
    output_dir: Optional[str] = None,
    verbose: bool = True,
) -> dict:
    """Run the full Searcher → Analyst → Archivist crew workflow.

    When ``repo_targets`` are provided (from ``--repos``/``--user``), targets
    are scanned deterministically via the existing scanner logic instead of
    relying on CrewAI agent non-determinism. Results are then archived through
    the Archivist tool path.

    Returns a dict with keys: crew_available, written, output_dir, error.
    """
    if not _CREWAI_AVAILABLE:
        return {
            "crew_available": False,
            "error": f"CrewAI not installed: {_CREWAI_IMPORT_ERROR}",
            "written": 0,
        }

    if output_dir is not None:
        config.output_dir = Path(output_dir)

    # ------------------------------------------------------------------ #
    # Explicit targets: scan directly (deterministic), then archive.
    # ------------------------------------------------------------------ #
    if repo_targets:
        return _run_crew_with_targets(
            config, repo_targets, adjudicator=adjudicator, verbose=verbose
        )

    # ------------------------------------------------------------------ #
    # Default discovery path: Searcher → Analyst → Archivist via web search.
    # ------------------------------------------------------------------ #
    crew = build_crew(
        config,
        serper_api_key=serper_api_key,
        llm_model=llm_model,
        adjudicator=adjudicator,
        repo_targets=None,
        verbose=verbose,
    )
    if crew is None:
        return {
            "crew_available": False,
            "error": "CrewAI not available",
            "written": 0,
        }

    try:
        result = crew.kickoff()
    except Exception as exc:  # crew runtime failure
        log.exception("CrewAI workflow failed")
        return {
            "crew_available": True,
            "error": str(exc),
            "written": 0,
        }

    # Try to read back the archive count
    written = 0
    archive_path = Path(config.output_dir) / "poems.json"
    if archive_path.exists():
        try:
            import json

            data = json.loads(archive_path.read_text(encoding="utf-8"))
            written = len(data.get("poems", []))
        except Exception:
            pass

    return {
        "crew_available": True,
        "written": written,
        "output_dir": str(config.output_dir),
        "result": str(result)[:500],
    }


def _run_crew_with_targets(
    config: Any,
    repo_targets: List[Tuple[str, str, Optional[int]]],
    *,
    adjudicator: Any = None,
    verbose: bool = True,
) -> dict:
    """Scan explicit --repos/--user targets directly and archive the results."""
    # Lazy import to avoid circular import (scan_poems imports from src.crew_agents).
    from scan_poems import scan_repo, iso_to_epoch  # type: ignore

    scanner = _import_scanner()
    cutoff_epoch = iso_to_epoch(f"{config.cutoff_date}T23:59:59Z")
    client = scanner["GitHubClient"](config)

    all_hits: List[Any] = []
    for owner, repo, pr_number in repo_targets:
        try:
            sample_pr_numbers = [pr_number] if pr_number else None
            hits = scan_repo(
                client,
                config,
                owner,
                repo,
                cutoff_epoch,
                sample_pr_numbers=sample_pr_numbers,
            )
            all_hits.extend(hits)
            if verbose:
                log.info(
                    "Scanned %s/%s: %d poem hits", owner, repo, len(hits)
                )
        except Exception as exc:  # network / rate limit - report, don't crash
            log.warning("Repo scan failed for %s/%s: %s", owner, repo, exc)

    # Build records and write via the archivist logic (merge + dedupe + write).
    new_records = scanner["build_records"](all_hits)
    output_dir = config.output_dir
    existing_path = output_dir / "poems.json"
    existing = scanner["load_existing_json"](existing_path)
    merged = scanner["merge_and_dedupe"](existing, new_records)
    merged.sort(key=lambda r: (r.repo, r.pr_number, r.created_at))

    output_dir.mkdir(parents=True, exist_ok=True)
    scanner["write_json"](merged, output_dir / "poems.json")
    scanner["write_markdown"](merged, output_dir / "poems.md")

    written = len(merged)
    log.info(
        "CrewAI workflow complete. %d poems written to %s", written, output_dir
    )
    return {
        "crew_available": True,
        "written": written,
        "output_dir": str(output_dir),
        "result": f"{written} poems written from explicit targets",
        "error": None,
    }
