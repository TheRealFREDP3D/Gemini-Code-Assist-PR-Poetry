#!/usr/bin/env python3
"""Gemini Code Assist PR Poetry scanner - main entry point.

This is the reworked version of the original `get_new_flowers.py` from
https://github.com/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry. Instead of
scanning a single repo or randomly walking GitHub, it:

  1. Discovers repositories where `gemini-code-assist[bot]` actually
     commented on PRs (via GitHub's `commenter:` search).
  2. Ranks those by stars and takes the top N (default 5).
  3. Walks each repo's PR history (created on or before the cutoff date -
     default 2026-07-17, when the consumer bot was shut down) and harvests
     every review/comment left by the bot.
  4. Runs a heuristic poem extractor on each comment.
  5. Writes the recovered poems to `output/poems.md` and `output/poems.json`.

The user can also supply explicit repos (`--repos owner/repo,...`) or a
username (`--user someuser`) to scan instead of running discovery.

Usage
-----
    # Dynamic top-5 discovery (default)
    python scan_poems.py

    # Scan specific repos
    python scan_poems.py --repos TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry,facebook/react

    # Scan all public repos owned by a user
    python scan_poems.py --user TheRealFREDP3D

    # Custom discovery size and cutoff
    python scan_poems.py --top 10 --cutoff 2025-12-31

    # Override output dir
    python scan_poems.py --output-dir ./my-output
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Allow `python scan_poems.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import Config, load_config  # noqa: E402
from src.crew_agents import _CREWAI_IMPORT_ERROR, crew_available, run_crew_workflow  # noqa: E402
from src.gh_client import GitHubClient, GitHubError, iso_to_epoch  # noqa: E402
from src.llm_adjudicator import LlmAdjudicator  # noqa: E402
from src.output import (  # noqa: E402
    PoemRecord,
    build_records,
    load_existing_json,
    merge_and_dedupe,
    write_json,
    write_markdown,
)
from src.poem_extractor import (  # noqa: E402
    Comment,
    Poem,
    PoemHit,
    extract_poem,
    is_bot_comment,
)
from src.repo_discovery import (  # noqa: E402
    DiscoveredRepo,
    discover_repos_with_bot_activity,
    expand_user_repos,
    load_preset_targets,
    parse_repo_specs,
)

log = logging.getLogger("scan_poems")

CUTOFF_HELP = (
    "ISO date (YYYY-MM-DD). Only PRs created on or before this date will be "
    "scanned. Default: 2026-07-17 (the day Google shut down the consumer "
    "Gemini Code Assist bot on GitHub)."
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="scan_poems",
        description="Scan GitHub repos for poems left by gemini-code-assist[bot] in PR review comments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument(
        "--repos",
        type=str,
        default=None,
        help="Comma-separated list of owner/repo specs (or GitHub URLs) to scan. "
             "Skips dynamic discovery.",
    )
    src.add_argument(
        "--user",
        type=str,
        default=None,
        help="Scan all public non-fork repos owned by this username. Skips dynamic discovery.",
    )

    src.add_argument(
        "--preset",
        type=str,
        default=None,
        help="Path to a file of pre-searched repo/PR specs (one per line), e.g. "
             "SERPER/web-search results. Each line: owner/repo, owner/repo#123, "
             "or a GitHub PR URL. Skips dynamic discovery and GitHub search API "
             "rate limits entirely.",
    )

    p.add_argument(
        "--top",
        type=int,
        default=5,
        help="When discovering dynamically: take this many top-starred repos where the "
             "bot is a contributor. Default: 5.",
    )
    p.add_argument(
        "--cutoff",
        type=str,
        default=None,
        help=CUTOFF_HELP,
    )
    p.add_argument(
        "--min-prs",
        type=int,
        default=1,
        help="(Discovery only) Minimum bot-PRs a repo must have to be considered. Default: 1.",
    )
    p.add_argument(
        "--max-prs-per-repo",
        type=int,
        default=0,
        help="Hard cap on PRs to walk per repo. 0 = no cap (walk all bot-commented PRs). Default: 0.",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory. Default: ./output",
    )
    p.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub token. If omitted, reads GITHUB_TOKEN / GH_TOKEN from env or .env.",
    )
    p.add_argument(
        "--append",
        action="store_true",
        help="Merge results with any existing output/poems.json instead of overwriting.",
    )
    p.add_argument(
        "--llm-adjudicate",
        action="store_true",
        help="Use an LLM (via LiteLLM) to adjudicate comments where the heuristic "
             "extractor finds nothing or only a low-confidence candidate. "
             "Requires litellm and a provider API key; heuristic detection is "
             "always tried first.",
    )
    p.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model for adjudication (e.g. 'gemini/gemini-2.5-flash', "
             "'ollama/llama3.1'). Default: LLM_MODEL from env/.env.",
    )
    p.add_argument(
        "--adjudicate-threshold",
        type=float,
        default=None,
        help="Accept heuristic candidates at or above this confidence without "
             "asking the LLM. Default: ADJUDICATE_THRESHOLD from env/.env (0.5).",
    )
    p.add_argument(
        "--no-llm-cache",
        action="store_true",
        help="Disable the on-disk LLM adjudication cache.",
    )
    p.add_argument(
        "--list-discovered",
        action="store_true",
        help="Only run the discovery phase and print the top-N candidate repos. Do not scan.",
    )
    p.add_argument(
        "--no-fetch-stars",
        action="store_true",
        help="(Discovery only) Skip fetching star counts for candidate repos. "
             "Faster, but results are ranked by bot_pr_count instead of stars. "
             "Useful when the IP's core rate limit is exhausted.",
    )
    p.add_argument(
        "--crew",
        action="store_true",
        help="Run the CrewAI agent workflow (Searcher -> Analyst -> Archivist) "
             "instead of the direct CLI scan. Requires crewai and SERPER_API_KEY.",
    )
    p.add_argument(
        "--serper-api-key",
        type=str,
        default=None,
        help="SERPER API key for the CrewAI Searcher agent web search. "
             "Defaults to SERPER_API_KEY env var.",
    )
    p.add_argument(
        "--crew-output-dir",
        type=str,
        default=None,
        help="Output directory for the crew workflow. Defaults to --output-dir.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose (DEBUG-level) logging.",
    )
    return p.parse_args(argv)


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# --------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------- #
def _pr_created_before(pr: dict, cutoff_epoch: float) -> bool:
    created = pr.get("created_at") or ""
    if not created:
        return True  # if we can't tell, include it
    return iso_to_epoch(created) <= cutoff_epoch


def _extract_poem_hit(
    body: str,
    config: Config,
    adjudicator: Optional[LlmAdjudicator] = None,
) -> Optional[Poem]:
    """Heuristic extraction first; optionally ask the LLM for a second opinion.

    A heuristic candidate at or above `config.adjudicate_threshold` is accepted
    as-is. Otherwise (no candidate, or a weak one) the adjudicator runs when
    enabled. If adjudication finds nothing, any heuristic result - even a weak
    one - is kept rather than discarding it.
    """
    poem = extract_poem(body, config)
    if poem is not None and (
        adjudicator is None or poem.confidence >= config.adjudicate_threshold
    ):
        return poem
    if adjudicator is None:
        return poem

    verdict = adjudicator.adjudicate(body)
    if verdict is None or not verdict.poem_found:
        return poem

    log.debug("LLM adjudication via %s: %s", verdict.model, verdict.reason[:120])
    return Poem(
        text="\n".join(verdict.lines),
        header="",
        source_kind="llm",
        confidence=verdict.confidence,
        raw_excerpt=body[-400:],
        model=verdict.model,
    )


def scan_repo(
    client: GitHubClient,
    config: Config,
    owner: str,
    repo: str,
    cutoff_epoch: float,
    max_prs: int = 0,
    sample_pr_numbers: Optional[List[int]] = None,
    adjudicator: Optional[LlmAdjudicator] = None,
) -> List[PoemHit]:
    """Scan a single repo for bot poems.

    If `sample_pr_numbers` is given, only those PRs are scanned (used by the
    discovery phase - we already know those PRs had bot comments).
    Otherwise we list all PRs and walk each one.
    """
    hits: List[PoemHit] = []
    log.info("Scanning %s/%s (cutoff epoch=%d, max_prs=%s)",
             owner, repo, int(cutoff_epoch), max_prs or "∞")

    # If discovery gave us specific PR numbers, use them - much faster
    if sample_pr_numbers:
        pr_iter: Iterable[dict]
        pr_numbers_to_scan = sample_pr_numbers
        if max_prs > 0:
            pr_numbers_to_scan = pr_numbers_to_scan[:max_prs]
        log.info("Using %d PR numbers from discovery", len(pr_numbers_to_scan))
        for pr_number in pr_numbers_to_scan:
            try:
                pr = client.get_pull_request(owner, repo, pr_number)
            except GitHubError as exc:
                log.warning("Could not fetch PR #%d in %s/%s: %s", pr_number, owner, repo, exc)
                continue
            if not _pr_created_before(pr, cutoff_epoch):
                continue
            hits.extend(
                _scan_pr_comments(client, config, owner, repo, pr, adjudicator=adjudicator)
            )
        return hits

    # Otherwise walk all PRs, newest first
    scanned = 0
    for pr in client.list_pull_requests(owner, repo, state="all", direction="desc"):
        if not _pr_created_before(pr, cutoff_epoch):
            # PRs come back newest-first; skip post-cutoff PRs and keep
            # walking to older pre-cutoff PRs (the bot only commented
            # on/before 2026-07-17).
            continue
        scanned += 1
        log.info("  Scanning PR #%s: %s", pr.get("number"), (pr.get("title") or "")[:80])
        if max_prs > 0 and scanned > max_prs:
            log.info("Hit max-prs-per-repo=%d, stopping.", max_prs)
            break
        hits.extend(
            _scan_pr_comments(client, config, owner, repo, pr, adjudicator=adjudicator)
        )

    log.info("Scanned %d PRs in %s/%s, %d poem hits", scanned, owner, repo, len(hits))
    return hits


def _scan_pr_comments(
    client: GitHubClient,
    config: Config,
    owner: str,
    repo: str,
    pr: dict,
    adjudicator: Optional[LlmAdjudicator] = None,
) -> List[PoemHit]:
    pr_number = int(pr.get("number", 0) or 0)
    pr_title = pr.get("title", "")
    repo_full = f"{owner}/{repo}"
    pr_url = pr.get("html_url") or f"https://github.com/{repo_full}/pull/{pr_number}"
    hits: List[PoemHit] = []

    # Three comment sources on a PR:
    #   1. Reviews (the bot's overall review body)
    #   2. Issue-level comments (timeline comments on the PR conversation)
    #   3. Review comments (inline comments on specific lines - rarely poems)
    try:
        for review in client.list_reviews(owner, repo, pr_number):
            author = (review.get("user") or {}).get("login", "")
            if not is_bot_comment(author, config):
                continue
            body = review.get("body") or ""
            if not body.strip():
                continue
            comment = Comment(
                body=body,
                author=author,
                created_at=review.get("submitted_at") or review.get("created_at") or "",
                pr_number=pr_number,
                pr_title=pr_title,
                repo_full_name=repo_full,
                comment_url=review.get("html_url") or pr_url,
                comment_kind="review",
            )
            poem = _extract_poem_hit(body, config, adjudicator=adjudicator)
            if poem:
                hits.append(PoemHit(poem=poem, comment=comment))
                model_note = f" model={poem.model}" if poem.model else ""
                log.info("  PR #%d REVIEW poem via %s (conf %.2f%s): %s",
                         pr_number, poem.source_kind, poem.confidence, model_note,
                         poem.text.replace("\n", " ")[:120])
                log.debug("  raw excerpt: %s", poem.raw_excerpt[:200])
    except GitHubError as exc:
        log.warning("  Failed listing reviews for PR #%d: %s", pr_number, exc)

    try:
        for comment in client.list_issue_comments(owner, repo, pr_number):
            author = (comment.get("user") or {}).get("login", "")
            if not is_bot_comment(author, config):
                continue
            body = comment.get("body") or ""
            if not body.strip():
                continue
            c = Comment(
                body=body,
                author=author,
                created_at=comment.get("created_at") or "",
                pr_number=pr_number,
                pr_title=pr_title,
                repo_full_name=repo_full,
                comment_url=comment.get("html_url") or pr_url,
                comment_kind="issue_comment",
            )
            poem = _extract_poem_hit(body, config, adjudicator=adjudicator)
            if poem:
                hits.append(PoemHit(poem=poem, comment=c))
                model_note = f" model={poem.model}" if poem.model else ""
                log.info("  PR #%d ISSUE-COMMENT poem via %s (conf %.2f%s): %s",
                         pr_number, poem.source_kind, poem.confidence, model_note,
                         poem.text.replace("\n", " ")[:120])
                log.debug("  raw excerpt: %s", poem.raw_excerpt[:200])
    except GitHubError as exc:
        log.warning("  Failed listing issue comments for PR #%d: %s", pr_number, exc)

    return hits


# --------------------------------------------------------------------- #
# Repo resolution
# --------------------------------------------------------------------- #
@dataclass
class RepoTarget:
    owner: str
    name: str
    sample_pr_numbers: List[int] = None  # type: ignore


def resolve_targets(
    args: argparse.Namespace,
    client: GitHubClient,
) -> List[RepoTarget]:
    """Figure out which repos to scan based on CLI args."""
    if args.repos:
        specs = parse_repo_specs(args.repos)
        return [
            RepoTarget(owner=o, name=r, sample_pr_numbers=[p] if p else None)
            for o, r, p in specs
        ]

    if args.user:
        user_repos = expand_user_repos(client, args.user)
        return [RepoTarget(owner=o, name=r) for o, r in user_repos]

    if args.preset:
        log.info("Using preset targets from %s (skipping GitHub search)", args.preset)
        presets = load_preset_targets(args.preset)
        return [
            RepoTarget(owner=o, name=r, sample_pr_numbers=pr_nums)
            for o, r, pr_nums in presets
        ]

    # Dynamic discovery
    log.info("Discovering repos with gemini-code-assist[bot] activity (top %d)...", args.top)
    discovered = discover_repos_with_bot_activity(
        client,
        top_n=args.top,
        min_prs=args.min_prs,
        fetch_stars=not args.no_fetch_stars,
    )
    if args.list_discovered:
        log.info("--list-discovered set; printing candidates and exiting.")
        for d in discovered:
            print(f"{d.full_name}  stars={d.star_count}  bot_prs={d.bot_pr_count}")
        return []

    if not discovered:
        log.warning(
            "Discovery returned no repos. The search may have failed (rate limit? "
            "token scopes?) or no public PR has the bot as a commenter. "
            "Try --repos owner/repo,... instead."
        )
        return []

    log.info("Discovered %d repos:", len(discovered))
    for d in discovered:
        log.info("  %s", d)
    return [
        RepoTarget(owner=d.owner, name=d.name, sample_pr_numbers=d.sample_pr_numbers)
        for d in discovered
    ]


# --------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    config = load_config()
    if args.token:
        config.github_token = args.token
    if args.cutoff:
        config.cutoff_date = args.cutoff
    if args.output_dir:
        config.output_dir = Path(args.output_dir)

    if not config.has_token:
        log.warning(
            "No GITHUB_TOKEN found. Unauthenticated rate limit is 60 req/hour - "
            "any non-trivial scan will fail. Set GITHUB_TOKEN in .env or pass --token."
        )

    cutoff_epoch = iso_to_epoch(f"{config.cutoff_date}T23:59:59Z")
    log.info("Cutoff date: %s (epoch=%d)", config.cutoff_date, int(cutoff_epoch))
    log.info("Output dir: %s", config.output_dir)

    client = GitHubClient(config)

    # Note: we deliberately do NOT call /rate_limit as a pre-flight check.
    # That endpoint shares the core rate-limit budget, so when the IP is
    # already low it triggers a sleep before we even start. The lazy
    # rate-limit handling in GitHubClient will kick in per-request as needed.
    # The search endpoint (used by discovery) has its own separate budget.
    if config.has_token:
        log.info("Authenticating with token ending in '%s'", config.github_token[-4:] if len(config.github_token) >= 4 else "****")
    else:
        log.warning("Running unauthenticated - search endpoint budget is 10 req/min, core is 60 req/hour.")

    adjudicator: Optional[LlmAdjudicator] = None
    if args.llm_adjudicate:
        if args.model:
            config.llm_model = args.model
        if args.adjudicate_threshold is not None:
            config.adjudicate_threshold = args.adjudicate_threshold
        if args.no_llm_cache:
            config.llm_cache_dir = None
        adjudicator = LlmAdjudicator(config)
        if not adjudicator.available:
            log.warning(
                "--llm-adjudicate requested but unavailable (install litellm and/or "
                "configure a model). Continuing heuristic-only."
            )
            adjudicator = None
        else:
            log.info(
                "LLM adjudication enabled: model=%s fallbacks=%s threshold=%.2f cache=%s",
                adjudicator.model,
                ", ".join(adjudicator.fallback_models) or "none",
                config.adjudicate_threshold,
                config.llm_cache_dir or "disabled",
            )
    elif args.model or args.adjudicate_threshold is not None:
        log.warning("--model/--adjudicate-threshold have no effect without --llm-adjudicate.")

    # ------------------------------------------------------------------ #
    # CrewAI agent workflow (Searcher -> Analyst -> Archivist)
    # ------------------------------------------------------------------ #
    if args.crew:
        if not crew_available():
            log.error(
                "--crew requested but CrewAI is not installed (%s). "
                "Install with `pip install crewai[tools]` and set SERPER_API_KEY.",
                _CREWAI_IMPORT_ERROR,
            )
            return 4

        # Resolve explicit --repos/--user targets if provided; the crew will
        # scan those directly instead of doing Serper web discovery.
        repo_targets: Optional[List[Tuple[str, str, Optional[int]]]] = None
        if args.repos or args.user:
            targets = resolve_targets(args, client)
            repo_targets = [
                (t.owner, t.name, (t.sample_pr_numbers[0] if t.sample_pr_numbers else None))
                for t in targets
            ]

        # SERPER_API_KEY is only required when we're doing web discovery
        # (no explicit targets). With --repos/--user we skip the Searcher.
        serper_key = args.serper_api_key or os.getenv("SERPER_API_KEY")
        if not serper_key and not repo_targets:
            log.error(
                "--crew requires SERPER_API_KEY (env or --serper-api-key) for "
                "the Searcher agent's web search."
            )
            return 4
        if not serper_key:
            log.warning(
                "SERPER_API_KEY not set; continuing without web search "
                "(explicit targets provided via --repos/--user)."
            )

        crew_out_dir = args.crew_output_dir or args.output_dir or str(config.output_dir)
        crew_result = run_crew_workflow(
            config,
            serper_api_key=serper_key,
            llm_model=args.model,
            adjudicator=adjudicator,
            repo_targets=repo_targets,
            output_dir=crew_out_dir,
            verbose=args.verbose,
        )
        if crew_result.get("error"):
            log.error("CrewAI workflow failed: %s", crew_result["error"])
            return 4
        log.info(
            "CrewAI workflow complete. %d poems written to %s",
            crew_result.get("written", 0), crew_result.get("output_dir"),
        )
        return 0

    targets = resolve_targets(args, client)
    if not targets:
        if args.list_discovered:
            return 0
        log.error("No repos to scan. Aborting.")
        return 3

    all_hits: List[PoemHit] = []
    for i, target in enumerate(targets, 1):
        log.info("[%d/%d] %s/%s", i, len(targets), target.owner, target.name)
        try:
            hits = scan_repo(
                client, config, target.owner, target.name,
                cutoff_epoch=cutoff_epoch,
                max_prs=args.max_prs_per_repo,
                sample_pr_numbers=target.sample_pr_numbers,
                adjudicator=adjudicator,
            )
        except GitHubError as exc:
            log.error("Scan of %s/%s failed: %s", target.owner, target.name, exc)
            continue
        all_hits.extend(hits)

    log.info("Total poem hits across all repos: %d", len(all_hits))

    # Convert to records
    new_records = build_records(all_hits)

    # Optionally merge with existing
    if args.append:
        existing_path = config.output_dir / "poems.json"
        existing = load_existing_json(existing_path)
        records = merge_and_dedupe(existing, new_records)
        log.info("Merged %d new with %d existing -> %d unique", len(new_records), len(existing), len(records))
    else:
        records = new_records

    # Sort by (repo, pr_number, created_at)
    records.sort(key=lambda r: (r.repo, r.pr_number, r.created_at))

    out_md = config.output_dir / "poems.md"
    out_json = config.output_dir / "poems.json"
    write_json(records, out_json)
    write_markdown(records, out_md)

    log.info("Done. %d poems written to:", len(records))
    log.info("  %s", out_md)
    log.info("  %s", out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
