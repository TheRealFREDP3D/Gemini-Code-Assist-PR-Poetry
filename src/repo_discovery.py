"""Repository discovery - find repos where `gemini-code-assist[bot]` is a contributor.

Strategy
========
GitHub doesn't expose a direct "list repositories where user X is a contributor"
endpoint, but we can use the **issue/PR search API** to find every PR where the
bot commented, then bucket the PRs by repository. The repos with the most bot
comments are the ones where the bot was most active.

We then optionally fetch each repo's star count and sort by stars so the user
gets the "top N most-starred repos that the bot actually contributed to".

Functions
---------
- `discover_repos_with_bot_activity(client, top_n=5, min_prs=3)`
    Walk `commenter:gemini-code-assist[bot] type:pr` search results, group by
    repo, optionally fetch stars, return top N.
- `expand_user_repos(client, username)`
    For `--user someuser` - list that user's public non-fork repos.
- `parse_repo_specs(specs)`
    Parse `--repos owner/repo,owner/repo,...` into (owner, repo) tuples.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from .gh_client import GitHubClient

log = logging.getLogger(__name__)

# Search queries
BOT_COMMENTER_QUERY = "commenter:{bot} is:pr"
BOT_INVOLVED_QUERY = "involves:{bot} is:pr"

# The bot login as it appears in search queries. GitHub search treats
# `gemini-code-assist[bot]` specially because of the `[bot]` suffix.
# Empirically `commenter:gemini-code-assist[bot]` works in the search box
# and via the API; if it returns nothing we fall back to `involves:`.
BOT_LOGIN_FOR_SEARCH = "gemini-code-assist[bot]"


@dataclass
class DiscoveredRepo:
    owner: str
    name: str
    full_name: str  # "owner/name"
    star_count: int
    bot_pr_count: int  # how many PRs the bot commented on
    sample_pr_numbers: List[int] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.full_name} (★{self.star_count}, bot on {self.bot_pr_count} PRs)"


_PR_FRAGMENT_RE = re.compile(r"(?:#|/pull/)(\d+)\s*$")


def parse_repo_specs(
    specs: str | Sequence[str],
) -> List[Tuple[str, str, Optional[int]]]:
    """Parse `--repos owner/repo,owner/repo,...` (or a list) into tuples.

    Accepts:
      - "owner/repo"
      - "owner/repo#123"           (PR number from a SERPER result URL)
      - "owner/repo/pull/123"
      - "https://github.com/owner/repo"
      - "https://github.com/owner/repo/pull/123"
      - "owner/repo,owner2/repo2#5"
      - ["owner/repo", "owner2/repo2"]

    Returns a list of ``(owner, repo, pr_number_or_None)`` tuples.
    """
    if isinstance(specs, str):
        items = [s.strip() for s in specs.split(",") if s.strip()]
    else:
        items = [s.strip() for s in specs if s and s.strip()]

    out: List[Tuple[str, str, Optional[int]]] = []
    for item in items:
        s = item
        pr_number: Optional[int] = None
        # Capture a trailing PR number before splitting the path.
        m = _PR_FRAGMENT_RE.search(s)
        if m:
            pr_number = int(m.group(1))
            s = s[: m.start()].rstrip("/")

        if s.startswith("http"):
            # https://github.com/owner/repo[.git][/anything]
            s = s.split("://", 1)[1]
            s = s.split("/", 1)[1]  # drop host
            s = s.rstrip("/")
            if s.endswith(".git"):
                s = s[:-4]
        parts = s.split("/")
        if len(parts) < 2:
            log.warning("Skipping malformed repo spec '%s' (expected owner/repo)", item)
            continue
        owner, repo = parts[0], parts[1]
        if not owner or not repo:
            log.warning("Skipping malformed repo spec '%s'", item)
            continue
        out.append((owner.strip(), repo.strip(), pr_number))
    return out


def expand_user_repos(client: GitHubClient, username: str, *, include_forks: bool = False) -> List[Tuple[str, str]]:
    """List a user's public repos. Returns [(owner, name), ...]."""
    log.info("Listing public repos for user @%s", username)
    out: List[Tuple[str, str]] = []
    params = {"type": "public", "per_page": 100}
    if include_forks:
        params.pop("type", None)
    for repo in client.paginate(f"/users/{username}/repos", params=params):
        full = repo.get("full_name", "")
        if not full or "/" not in full:
            continue
        if repo.get("fork") and not include_forks:
            continue
        owner, name = full.split("/", 1)
        out.append((owner, name))
    log.info("Found %d public repos for @%s", len(out), username)
    return out


def load_preset_targets(
    path: str | Path,
) -> List[Tuple[str, str, List[int]]]:
    """Load pre-searched repo/PR targets from a file.

    This is the integration point for SERPER (or any web search) results.
    Instead of calling GitHub's rate-limited ``/search/issues`` endpoint, you
    can run a SERPER query like::

        site:github.com "gemini-code-assist[bot]" "pullrequestreview"

    save the matching repo/PR URLs (one per line) to a file, and pass it via
    ``--preset``::

        python scan_poems.py --preset serper_results.txt

    Each line may be:
      - owner/repo
      - owner/repo#123          (a specific PR the bot commented on)
      - https://github.com/owner/repo/pull/123

    Returns a list of ``(owner, repo, pr_numbers)`` tuples, where
    ``pr_numbers`` is the list of PR numbers found on lines for that repo
    (empty when only the repo was given).
    """
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        log.error("Preset targets file not found: %s", p)
        return []

    specs: List[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        specs.append(line)

    parsed = parse_repo_specs(specs)

    # Group PR numbers by repo so a repo with multiple PR lines gets all of them.
    grouped: dict[Tuple[str, str], List[int]] = {}
    plain_repos: set[Tuple[str, str]] = set()
    for owner, repo, pr_number in parsed:
        key = (owner, repo)
        if pr_number is not None:
            grouped.setdefault(key, []).append(pr_number)
        else:
            plain_repos.add(key)

    targets: List[Tuple[str, str, List[int]]] = []
    for key in plain_repos:
        targets.append((key[0], key[1], []))
    for key, pr_numbers in grouped.items():
        targets.append((key[0], key[1], sorted(pr_numbers)))

    log.info("Loaded %d preset targets from %s", len(targets), p)
    return targets


def discover_repos_with_bot_activity(
    client: GitHubClient,
    *,
    top_n: int = 5,
    min_prs: int = 1,
    max_prs_to_scan: int = 1000,
    fetch_stars: bool = True,
    max_star_fetch_failures: int = 5,
) -> List[DiscoveredRepo]:
    """Find repos where `gemini-code-assist[bot]` commented on PRs.

    Walks `commenter:gemini-code-assist[bot] is:pr` search results, buckets
    by repo, fetches star count for each candidate, sorts by stars desc and
    returns the top N.

    If `fetch_stars` is False (or star-fetches keep failing because the core
    rate limit is exhausted), candidates are returned with `star_count=0`
    and the final sort falls back to `bot_pr_count` desc.
    """
    candidates: dict[str, dict] = {}  # full_name -> {pr_numbers: set, owner, name}

    def _ingest(query: str) -> int:
        n = 0
        try:
            for item in client.search_issues(query, sort="updated", per_page=100):
                n += 1
                if n > max_prs_to_scan:
                    log.warning("Hit max_prs_to_scan=%d during discovery, stopping early", max_prs_to_scan)
                    break
                repo_url = item.get("repository_url") or ""
                # repo_url looks like https://api.github.com/repos/{owner}/{repo}
                if "/repos/" not in repo_url:
                    continue
                full_name = repo_url.split("/repos/", 1)[1].strip("/")
                if "/" not in full_name:
                    continue
                owner, name = full_name.split("/", 1)
                pr_number = item.get("number")
                bucket = candidates.setdefault(
                    full_name,
                    {"owner": owner, "name": name, "pr_numbers": set()},
                )
                if pr_number:
                    bucket["pr_numbers"].add(int(pr_number))
        except Exception as exc:
            log.warning("Search '%s' yielded an error: %s", query, exc)
        return n

    primary_q = BOT_COMMENTER_QUERY.format(bot=BOT_LOGIN_FOR_SEARCH)
    log.info("Searching GitHub for PRs commented on by %s", BOT_LOGIN_FOR_SEARCH)
    found = _ingest(primary_q)

    if found == 0:
        # Fall back to `involves:` which is broader (mentions, assignments, etc.)
        fallback_q = BOT_INVOLVED_QUERY.format(bot=BOT_LOGIN_FOR_SEARCH)
        log.info("Primary search returned nothing. Trying broader query: %s", fallback_q)
        found = _ingest(fallback_q)

    log.info("Discovered %d unique repos with bot activity across %d PRs", len(candidates), found)
    if not candidates:
        return []

    # Filter to repos with at least `min_prs` bot-PRs
    filtered = [
        (full_name, info)
        for full_name, info in candidates.items()
        if len(info["pr_numbers"]) >= min_prs
    ]
    log.info("After min_prs=%d filter: %d repos", min_prs, len(filtered))

    # Fetch star counts and build DiscoveredRepo records.
    # If we hit several failures in a row (typically because the core rate
    # limit is exhausted when unauthenticated), stop trying to fetch stars
    # and just return what we have - the final sort will fall back to bot_pr_count.
    discovered: List[DiscoveredRepo] = []
    consecutive_failures = 0
    skipped_star_fetches = 0
    for full_name, info in filtered:
        stars = 0
        if fetch_stars and consecutive_failures < max_star_fetch_failures:
            try:
                repo_data = client.get_repo(info["owner"], info["name"])
                stars = int(repo_data.get("stargazers_count", 0) or 0)
                consecutive_failures = 0
            except Exception as exc:
                consecutive_failures += 1
                log.warning("Could not fetch repo info for %s: %s (failure %d/%d)",
                            full_name, exc, consecutive_failures, max_star_fetch_failures)
                if consecutive_failures >= max_star_fetch_failures:
                    log.warning(
                        "Hit %d consecutive star-fetch failures - skipping remaining star fetches. "
                        "Results will be ranked by bot_pr_count only.",
                        consecutive_failures,
                    )
        else:
            skipped_star_fetches += 1

        pr_numbers = sorted(info["pr_numbers"])
        discovered.append(
            DiscoveredRepo(
                owner=info["owner"],
                name=info["name"],
                full_name=full_name,
                star_count=stars,
                bot_pr_count=len(pr_numbers),
                sample_pr_numbers=pr_numbers[:50],
            )
        )

    if skipped_star_fetches:
        log.info("Skipped star-fetch for %d/%d repos (rate-limited or disabled)",
                 skipped_star_fetches, len(discovered))

    # Sort by star count desc, then by bot_pr_count desc as tiebreaker
    discovered.sort(key=lambda r: (r.star_count, r.bot_pr_count), reverse=True)
    return discovered[:top_n]
