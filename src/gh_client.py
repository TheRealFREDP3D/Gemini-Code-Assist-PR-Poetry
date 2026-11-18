"""GitHub API client - REST + GraphQL with rate-limit aware retry.

The scanner talks to two endpoints:

* REST `api.github.com` for listing PRs, reviews, comments and review threads.
* GraphQL `api.github.com/graphql` for the efficient "find every PR in this
  repo that the bot commented on" lookup, which avoids walking thousands of
  PRs one-by-one.

Rate limits are handled by:
  - reading `X-RateLimit-Remaining` on every response
  - sleeping until `X-RateLimit-Reset` when we hit 0
  - retrying secondary rate limits (HTTP 403 with retry-after) with backoff
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional

import requests

from .config import Config

log = logging.getLogger(__name__)

REST_API = "https://api.github.com"
GRAPHQL_API = "https://api.github.com/graphql"

# Endpoint we use for both GraphQL and REST. GraphQL budget is 5,000 points/hour
# for authenticated users; REST is 5,000 req/hour.


class GitHubError(RuntimeError):
    """Raised when the GitHub API returns a non-recoverable error."""

    def __init__(self, message: str, status: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


@dataclass
class RateLimitInfo:
    remaining: int
    reset: int  # epoch seconds
    limit: int

    @classmethod
    def from_headers(cls, headers: dict) -> "RateLimitInfo":
        try:
            return cls(
                remaining=int(headers.get("X-RateLimit-Remaining", "5000")),
                reset=int(headers.get("X-RateLimit-Reset", "0")),
                limit=int(headers.get("X-RateLimit-Limit", "5000")),
            )
        except (TypeError, ValueError):
            return cls(remaining=5000, reset=0, limit=5000)

    def wait_seconds(self) -> float:
        if self.remaining > 0:
            return 0.0
        if not self.reset:
            return 60.0
        now = time.time()
        wait = max(self.reset - now + 1.0, 1.0)
        # Sanity cap so we don't sleep for an hour if the clock is wrong
        return min(wait, 3600.0)


class GitHubClient:
    """Thin GitHub REST + GraphQL client with rate-limit aware retry."""

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(config.auth_header)
        self._last_rate: Optional[RateLimitInfo] = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _sleep_for_rate_limit(self, headers: dict) -> None:
        info = RateLimitInfo.from_headers(headers)
        self._last_rate = info
        if info.remaining <= 0:
            wait = info.wait_seconds()
            log.warning(
                "GitHub rate limit hit (remaining=0, reset in %.0fs). Sleeping...",
                wait,
            )
            time.sleep(wait)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        retries: Optional[int] = None,
    ) -> requests.Response:
        retries = retries if retries is not None else self.config.max_retries
        last_exc: Optional[Exception] = None

        for attempt in range(retries + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    timeout=self.config.request_timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning("Network error on %s %s: %s. Retry in %ds.", method, url, exc, wait)
                time.sleep(wait)
                continue

            self._sleep_for_rate_limit(resp.headers)

            # Secondary rate limit / abuse detection: 403 or 429 with Retry-After
            if resp.status_code in (403, 429) and "retry-after" in {k.lower() for k in resp.headers}:
                retry_after = float(resp.headers.get("Retry-After", "60"))
                log.warning(
                    "Secondary rate limit on %s %s. Sleeping %.0fs (attempt %d/%d).",
                    method, url, retry_after, attempt + 1, retries,
                )
                time.sleep(min(retry_after, 600.0))
                continue

            if resp.status_code == 403 and "rate limit" in (resp.text or "").lower():
                # Primary rate limit message - we already slept above, but if
                # we still got 403, sleep a bit more and retry.
                log.warning("Rate-limit 403 on %s %s. Sleeping 60s.", method, url)
                time.sleep(60.0)
                continue

            if 500 <= resp.status_code < 600 and attempt < retries:
                wait = 2 ** attempt
                log.warning(
                    "Server error %d on %s %s. Retry in %ds (attempt %d/%d).",
                    resp.status_code, method, url, wait, attempt + 1, retries,
                )
                time.sleep(wait)
                continue

            return resp

        # Out of retries
        raise GitHubError(
            f"Request failed after {retries + 1} attempts: {method} {url}: {last_exc}",
            status=None,
        )

    # ------------------------------------------------------------------ #
    # REST helpers
    # ------------------------------------------------------------------ #
    def get(self, path: str, *, params: Optional[dict] = None) -> dict | list:
        url = path if path.startswith("http") else f"{REST_API}{path}"
        resp = self._request("GET", url, params=params)
        if resp.status_code == 404:
            raise GitHubError(f"Not found: {url}", status=404)
        if not resp.ok:
            raise GitHubError(
                f"GET {url} -> {resp.status_code}: {resp.text[:500]}",
                status=resp.status_code,
            )
        return resp.json()

    def paginate(self, path: str, *, params: Optional[dict] = None) -> Iterator[dict]:
        """Walk a REST `Link: rel="next"` pagination chain."""
        url = path if path.startswith("http") else f"{REST_API}{path}"
        params = dict(params or {})
        params.setdefault("per_page", 100)

        while url:
            resp = self._request("GET", url, params=params)
            if not resp.ok:
                raise GitHubError(
                    f"GET {url} -> {resp.status_code}: {resp.text[:500]}",
                    status=resp.status_code,
                )
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    yield item
            elif isinstance(data, dict) and "items" in data:
                # Search API shape
                for item in data["items"]:
                    yield item
            else:
                # Single object - yield once and stop
                yield data
                break

            # Follow Link header
            next_url = _extract_next_link(resp.headers.get("Link", ""))
            url = next_url
            params = None  # next URL already encodes params

    # ------------------------------------------------------------------ #
    # GraphQL
    # ------------------------------------------------------------------ #
    def graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        payload = {"query": query, "variables": variables or {}}
        resp = self._request("POST", GRAPHQL_API, json=payload)
        if not resp.ok:
            raise GitHubError(
                f"GraphQL HTTP {resp.status_code}: {resp.text[:500]}",
                status=resp.status_code,
            )
        data = resp.json()
        if data.get("errors"):
            messages = [e.get("message", "?") for e in data["errors"]]
            raise GitHubError(
                "GraphQL errors: " + " | ".join(messages),
                payload=data["errors"],
            )
        return data["data"]

    # ------------------------------------------------------------------ #
    # High-level REST endpoints used by the scanner
    # ------------------------------------------------------------------ #
    def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        sort: str = "created",
        direction: str = "desc",
        since: Optional[str] = None,
    ) -> Iterator[dict]:
        params = {"state": state, "sort": sort, "direction": direction}
        if since:
            # GitHub's REST list-PRs endpoint ignores `since`, but we filter
            # client-side in the scanner. We still pass it for clarity.
            params["since"] = since
        yield from self.paginate(f"/repos/{owner}/{repo}/pulls", params=params)

    def list_reviews(self, owner: str, repo: str, pr_number: int) -> Iterator[dict]:
        yield from self.paginate(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews")

    def list_issue_comments(self, owner: str, repo: str, pr_number: int) -> Iterator[dict]:
        # PR comments live at the issues/{number}/comments endpoint
        yield from self.paginate(f"/repos/{owner}/{repo}/issues/{pr_number}/comments")

    def list_review_comments(self, owner: str, repo: str, pr_number: int, review_id: int) -> Iterator[dict]:
        # This endpoint doesn't paginate in the usual way - returns a list
        url = f"{REST_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}/comments"
        resp = self._request("GET", url)
        if not resp.ok:
            return
        data = resp.json()
        if isinstance(data, list):
            for item in data:
                yield item

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict:
        return self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")

    def get_repo(self, owner: str, repo: str) -> dict:
        return self.get(f"/repos/{owner}/{repo}")

    def search_repositories(self, query: str, *, sort: str = "stars", per_page: int = 100) -> Iterator[dict]:
        params = {"q": query, "sort": sort, "order": "desc", "per_page": per_page}
        yield from self.paginate("/search/repositories", params=params)

    def search_issues(self, query: str, *, sort: str = "updated", per_page: int = 100) -> Iterator[dict]:
        """Walk the /search/issues endpoint - works for both issues and PRs."""
        params = {"q": query, "sort": sort, "order": "desc", "per_page": per_page}
        yield from self.paginate("/search/issues", params=params)


def _extract_next_link(link_header: str) -> Optional[str]:
    """Parse a GitHub `Link:` header and return the rel="next" URL if any."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            # Format: <url>; rel="next"; ...
            start = part.find("<")
            end = part.find(">")
            if start != -1 and end != -1:
                return part[start + 1 : end]
    return None


def iso_to_epoch(s: str) -> float:
    """Parse an ISO 8601 timestamp like '2026-07-17T10:00:00Z' to epoch seconds."""
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
