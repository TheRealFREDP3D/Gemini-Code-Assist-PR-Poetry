#!/usr/bin/env python3
"""Cleanup helper - deduplicate and re-sort a poems.json archive.

Reads `output/poems.json`, removes near-duplicate poems (same text after
whitespace normalization OR same repo+PR+first-200-chars), sorts by
(repo, pr_number, created_at), and writes back.

Usage:
    python cleanup_poems.py [--input PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import DEFAULT_OUTPUT_DIR  # noqa: E402

log = logging.getLogger("cleanup")


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation - for fuzzy match."""
    text = (text or "").lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def dedupe(records: List[dict]) -> List[dict]:
    seen_text: set[str] = set()
    seen_key: set[str] = set()
    out: List[dict] = []
    dropped = 0
    for r in records:
        poem = r.get("poem", "")
        norm = normalize(poem)
        # Key 1: exact normalized poem text (catches cross-repo reposts)
        if norm and norm in seen_text:
            dropped += 1
            continue
        # Key 2: same repo + PR + first 200 normalized chars
        key2 = f"{r.get('repo')}|{r.get('pr_number')}|{norm[:200]}"
        if key2 in seen_key:
            dropped += 1
            continue
        seen_text.add(norm)
        seen_key.add(key2)
        out.append(r)
    log.info("Dedupe: %d -> %d (dropped %d)", len(records), len(out), dropped)
    return out


def sort_records(records: List[dict]) -> List[dict]:
    def key(r):
        return (
            r.get("repo", "").lower(),
            int(r.get("pr_number", 0) or 0),
            r.get("created_at", ""),
        )
    return sorted(records, key=key)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cleanup_poems")
    p.add_argument("--input", type=str, default=str(DEFAULT_OUTPUT_DIR / "poems.json"))
    p.add_argument("--output", type=str, default=None, help="Default: overwrite input.")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    in_path = Path(args.input)
    if not in_path.exists():
        log.error("Input file not found: %s", in_path)
        return 1

    data = json.loads(in_path.read_text(encoding="utf-8"))
    records = data.get("poems", []) if isinstance(data, dict) else data
    log.info("Loaded %d records from %s", len(records), in_path)

    cleaned = sort_records(dedupe(records))

    out_path = Path(args.output) if args.output else in_path
    out_data = {
        "generated_at": data.get("generated_at") if isinstance(data, dict) else None,
        "count": len(cleaned),
        "poems": cleaned,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %d cleaned records to %s", len(cleaned), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
