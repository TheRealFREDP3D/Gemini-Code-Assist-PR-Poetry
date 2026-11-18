"""Output writers - Markdown + JSON for collected poems.

Both writers consume the same list of `PoemRecord` dicts (defined below) and
write to the configured output directory. The Markdown file is human-readable
grouped by repo -> PR; the JSON file is a flat list suitable for further
processing.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from .poem_extractor import Comment, Poem

log = logging.getLogger(__name__)

# Bump when the record shape changes in a way consumers must know about.
SCHEMA_VERSION = 2


@dataclass
class PoemRecord:
    repo: str                       # "owner/repo"
    pr_number: int
    pr_title: str
    pr_url: str
    poem: str
    author: str                     # bot login
    created_at: str                 # ISO 8601 from comment
    comment_url: str
    comment_kind: str               # "review" | "issue_comment" | "review_comment"
    detection_method: str           # "header" | "tail_blockquote" | "tail_lines" | "llm"
    detection_header: str           # the header that led us to it (if any)
    confidence: float
    model: str = ""                 # LLM used for adjudication ("" if heuristic)

    def to_dict(self) -> dict:
        return asdict(self)


def build_records(
    hits: Iterable["PoemHitLike"],
    *,
    repo_full_name: Optional[str] = None,
) -> List[PoemRecord]:
    records: List[PoemRecord] = []
    for hit in hits:
        poem: Poem = hit.poem
        comment: Comment = hit.comment
        repo_name = repo_full_name or comment.repo_full_name
        pr_url = (
            f"https://github.com/{repo_name}/pull/{comment.pr_number}"
            if repo_name
            else ""
        )
        records.append(
            PoemRecord(
                repo=repo_name,
                pr_number=comment.pr_number,
                pr_title=comment.pr_title,
                pr_url=pr_url,
                poem=poem.text,
                author=comment.author,
                created_at=comment.created_at,
                comment_url=comment.comment_url,
                comment_kind=comment.comment_kind,
                detection_method=poem.source_kind,
                detection_header=poem.header,
                confidence=poem.confidence,
                model=poem.model,
            )
        )
    return records


# A duck-typed alias so we can type hits without importing the scanner
class PoemHitLike:
    poem: Poem
    comment: Comment


def write_json(records: List[PoemRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(records),
        "poems": [r.to_dict() for r in records],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote JSON: %s (%d poems)", path, len(records))
    return path


def write_markdown(records: List[PoemRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    # Group by repo, then by PR
    grouped: dict[str, dict[int, List[PoemRecord]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        grouped[r.repo][r.pr_number].append(r)

    lines: List[str] = []
    lines.append("# Gemini Code Assist - Recovered PR Poetry")
    lines.append("")
    lines.append(
        f"Auto-collected by `gemini-poetry-scanner` on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d UTC')}. "
        f"Source: PR review comments left by the `gemini-code-assist[bot]` GitHub app "
        f"(consumer version shut down 2026-07-17)."
    )
    lines.append("")
    lines.append(f"**Total poems: {len(records)}** across {len(grouped)} repositories.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of contents
    lines.append("## Repositories")
    lines.append("")
    for repo in sorted(grouped.keys(), key=lambda r: -sum(len(v) for v in grouped[r].values())):
        repo_count = sum(len(v) for v in grouped[repo].values())
        anchor = repo.lower().replace("/", "-").replace(".", "")
        lines.append(f"- [{repo}](#{anchor}) ({repo_count} poem{'s' if repo_count != 1 else ''})")
    lines.append("")
    lines.append("---")
    lines.append("")

    for repo in sorted(grouped.keys(), key=lambda r: -sum(len(v) for v in grouped[r].values())):
        prs = grouped[repo]
        anchor = repo.lower().replace("/", "-").replace(".", "")
        lines.append(f"## {repo}")
        lines.append("")
        for pr_number in sorted(prs.keys()):
            pr_records = prs[pr_number]
            first = pr_records[0]
            lines.append(f"### #{pr_number} - {first.pr_title}")
            lines.append("")
            lines.append(f"- PR: [{repo}#{pr_number}]({first.pr_url})")
            if first.comment_url:
                lines.append(f"- Comment: [view on GitHub]({first.comment_url})")
            lines.append(f"- Date: {first.created_at}")
            lines.append("")
            for rec in pr_records:
                detail = f"> _Detected via **{rec.detection_method}** (confidence {rec.confidence:.2f}"
                if rec.detection_header:
                    detail += f", header `{rec.detection_header}`"
                if rec.model:
                    detail += f", model `{rec.model}`"
                lines.append(detail + ")_")
                lines.append("")
                # Render the poem as a blockquote for nice rendering
                for pline in rec.poem.splitlines():
                    lines.append(f"> {pline}" if pline else ">")
                lines.append("")
            lines.append("---")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote Markdown: %s (%d poems)", path, len(records))
    return path


def load_existing_json(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("poems", []) if isinstance(data, dict) else data
    except Exception as exc:
        log.warning("Could not load existing JSON at %s: %s", path, exc)
        return []


def merge_and_dedupe(existing: List[dict], new_records: List[PoemRecord]) -> List[PoemRecord]:
    """Merge new records with existing JSON dict records, deduping on (repo, pr_number, poem) key."""
    seen: set[str] = set()
    merged: List[PoemRecord] = []
    for raw in existing:
        key = f"{raw.get('repo')}|{raw.get('pr_number')}|{(raw.get('poem') or '').strip()[:200]}"
        if key in seen:
            continue
        seen.add(key)
        # Reconstruct a PoemRecord-like dict
        try:
            merged.append(PoemRecord(
                repo=raw.get("repo", ""),
                pr_number=int(raw.get("pr_number", 0) or 0),
                pr_title=raw.get("pr_title", ""),
                pr_url=raw.get("pr_url", ""),
                poem=raw.get("poem", ""),
                author=raw.get("author", ""),
                created_at=raw.get("created_at", ""),
                comment_url=raw.get("comment_url", ""),
                comment_kind=raw.get("comment_kind", ""),
                detection_method=raw.get("detection_method", ""),
                detection_header=raw.get("detection_header", ""),
                confidence=float(raw.get("confidence", 0.0) or 0.0),
                model=raw.get("model", ""),
            ))
        except Exception:
            continue
    for rec in new_records:
        key = f"{rec.repo}|{rec.pr_number}|{rec.poem.strip()[:200]}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(rec)
    return merged
