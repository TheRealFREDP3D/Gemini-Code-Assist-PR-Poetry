"""Heuristic poem extractor for Gemini Code Assist review comments.

The bot's review comment historically follows a fixed structure:

    ## Summary
    ...technical feedback...

    ## Code walk-through
    ...more technical feedback...

    ## ✨ Poem (or 🌸 / 📜 / 🪻 / etc.)
    > A four-to-six line poem
    > inspired by the PR's changes.

The poem section can also appear:
  - Under headers like `## Here's a poem`, `## ✍️`, `## 🎭`
  - As a plain `> ...` blockquote at the very end of the comment
  - With the literal phrase "Here is a poem inspired by your changes:" and
    a few indented lines

We try, in order:
  1. Header-anchored extraction (find a known poem header, take the
     blockquote/short-line block that follows it).
  2. Tail blockquote extraction (last `> ` block in the comment, with
     short rhyming-looking lines).
  3. Last short-line cluster extraction (consecutive lines <=80 chars,
     no markdown list markers, no code fence, minimum 2 lines).

Each candidate is scored with `looks_like_poem()` to filter out things like
signatures or status lines.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .config import Config

log = logging.getLogger(__name__)

# Maximum line length we consider "poetic". Real bot poems rarely exceed 80
# chars per line; allowing longer lines catches prose false-positives.
MAX_POEM_LINE_LEN = 90
MIN_POEM_LINES = 2
MAX_POEM_LINES = 40  # sanity cap

# Lines we never accept as part of a poem (after normalization - i.e. AFTER
# stripping list prefixes, blockquote markers, and code-fence edges).
_BAD_LINE_PATTERNS = [
    re.compile(r"^\s*```"),               # code fence (should be stripped pre-check)
    re.compile(r"^\s*!\[.*\]\(.*\)"),     # image
    re.compile(r"^\s*\[.*\]\(.*\)"),      # bare markdown link with no surrounding text
    re.compile(r"^\s*(https?://|www\.)", re.I),  # bare URL
    re.compile(r"^\s*---+\s*$"),          # horizontal rule
    re.compile(r"^\s*(#+\s|##)"),         # markdown header
    re.compile(r"^\s*<!--"),              # HTML comment
    re.compile(r"^\s*Signed-off-by:", re.I),
    re.compile(r"^\s*Co-authored-by:", re.I),
    re.compile(r"^\s*\*?Generated with", re.I),
    re.compile(r"^\s*\*?Powered by", re.I),
    re.compile(r"^\s*Disclaimer:", re.I),
    re.compile(r"^\s*\[bot\]"),
]

# A line is considered a code fence if it matches this pattern.
_CODE_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Numbered list prefix: "1. ", "2. ", "10. ", etc. - we strip this when
# normalizing poem lines because the bot sometimes used numbered lists to
# format poems (see gem-flowers.json examples).
_NUMBERED_PREFIX_RE = re.compile(r"^\s*(\d+)\.\s+")

# Bullet list prefix: "- " or "* " - stripped too.
_BULLET_PREFIX_RE = re.compile(r"^\s*[-*]\s+")


def _normalize_poem_line(line: str) -> str:
    """Strip the various prefixes the bot used to wrap poem lines.

    Removes:
      - Leading `>` blockquote markers (one or more, with optional spaces)
      - Leading numbered list prefixes (`1. `, `23. `)
      - Leading bullet list prefixes (`- `, `* `)
      - Surrounding whitespace
    Code fence ``` and ~~~ lines are detected separately and should be
    filtered out by the caller (use `_is_code_fence`).
    """
    s = line.rstrip()
    # Strip blockquote markers (can be nested: "> > foo")
    while True:
        stripped = s.lstrip()
        if stripped.startswith(">"):
            s = stripped[1:].lstrip()
        else:
            s = stripped
            break
    # Strip numbered list prefix
    m = _NUMBERED_PREFIX_RE.match(s)
    if m:
        s = s[m.end():]
    # Strip bullet prefix
    m = _BULLET_PREFIX_RE.match(s)
    if m:
        s = s[m.end():]
    return s.strip()


def _is_code_fence(line: str) -> bool:
    return bool(_CODE_FENCE_RE.match(line))


@dataclass
class Poem:
    text: str  # the poem body, joined with newlines
    header: str  # the section header that led us to it ("" if tail-detected)
    source_kind: str  # "header" | "tail_blockquote" | "tail_lines" | "llm"
    confidence: float  # 0..1 - score from looks_like_poem / LLM verdict
    raw_excerpt: str = ""  # the surrounding context for debugging
    model: str = ""  # LLM model name when source_kind == "llm", else ""


@dataclass
class Comment:
    body: str
    author: str
    created_at: str
    pr_number: int
    pr_title: str
    repo_full_name: str
    comment_url: str = ""
    comment_kind: str = "review"  # "review" | "issue_comment" | "review_comment"


@dataclass
class PoemHit:
    poem: Poem
    comment: Comment


def looks_like_poem(text: str) -> float:
    """Return a confidence score 0..1 that `text` is a poem.

    Each line is first normalized (blockquote markers, list prefixes stripped).
    Code-fence lines (``` ```, `~~~`) are skipped entirely (the bot sometimes
    wrapped poems in fences - we treat the fence as decorative).

    Factors:
      - Number of normalized short lines (2..MAX_POEM_LINE_LEN chars)
      - No bad-line patterns after normalization
      - Some end-rhyme (last word of two consecutive lines rhyme)
      - Average line length is short
    """
    raw_lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(raw_lines) < MIN_POEM_LINES:
        return 0.0

    # Normalize: strip prefixes; drop code-fence lines
    norm_lines: List[str] = []
    for ln in raw_lines:
        if _is_code_fence(ln):
            continue
        n = _normalize_poem_line(ln)
        if n:
            norm_lines.append(n)

    if len(norm_lines) < MIN_POEM_LINES:
        return 0.0

    bad_count = 0
    short_lines = 0
    rhyme_pairs = 0
    prev_endword: Optional[str] = None

    for ln in norm_lines:
        if len(ln) > MAX_POEM_LINE_LEN:
            continue
        if any(p.search(ln) for p in _BAD_LINE_PATTERNS):
            bad_count += 1
            continue
        short_lines += 1
        endword = _end_word(ln)
        if prev_endword and endword and _rhymes(prev_endword, endword):
            rhyme_pairs += 1
        prev_endword = endword

    if short_lines < MIN_POEM_LINES:
        return 0.0
    if bad_count > 0:
        return 0.0

    score = 0.3  # base
    # Reward line count
    score += min(short_lines / 10.0, 0.3)
    # Reward rhyme density
    if len(norm_lines) >= 2:
        rhyme_density = rhyme_pairs / max(len(norm_lines) - 1, 1)
        score += min(rhyme_density * 0.4, 0.4)
    return min(score, 1.0)


def _end_word(line: str) -> str:
    """Strip trailing punctuation and return the last word (lowercased)."""
    line = line.strip().rstrip(".,!?;:\"'`()]")
    parts = line.split()
    return parts[-1].lower() if parts else ""


_RHYME_SUFFIX_LEN = 3


def _rhymes(a: str, b: str) -> bool:
    """Cheap suffix-rhyme check - last 2-3 chars match (case-insensitive)."""
    if not a or not b or len(a) < 2 or len(b) < 2:
        return False
    if a == b:
        # Don't reward identical word repeats ("the"/"the")
        return False
    suffix = min(len(a), len(b), _RHYME_SUFFIX_LEN)
    return a[-suffix:] == b[-suffix:]


def extract_poem(comment_body: str, config: Config) -> Optional[Poem]:
    """Try every extraction strategy in order; return the best one."""
    if not comment_body or not comment_body.strip():
        return None

    candidates: List[Poem] = []

    # Strategy 1: header-anchored
    for header in config.poem_headers:
        poem = _extract_after_header(comment_body, header)
        if poem:
            candidates.append(poem)

    # Strategy 2: last blockquote block
    bq = _extract_tail_blockquote(comment_body)
    if bq:
        candidates.append(bq)

    # Strategy 3: last cluster of short non-markdown lines
    tail = _extract_tail_short_lines(comment_body)
    if tail:
        candidates.append(tail)

    if not candidates:
        return None

    # Highest confidence wins; tiebreak by source preference
    source_pref = {"header": 3, "tail_blockquote": 2, "tail_lines": 1}
    best = max(
        candidates,
        key=lambda p: (p.confidence, source_pref.get(p.source_kind, 0)),
    )
    if best.confidence < 0.15:
        return None
    return best


# --------------------------------------------------------------------- #
# Extraction strategies
# --------------------------------------------------------------------- #
def _extract_after_header(body: str, header: str) -> Optional[Poem]:
    """Find `header` as a line prefix, take the block of short non-empty lines
    that follows it (until a blank line followed by another header, or EOF).

    Lines are normalized with `_normalize_poem_line` (strips blockquote markers,
    numbered/bullet list prefixes). Code-fence lines (```/```) are *skipped*
    rather than treated as boundaries - the bot often wrapped its poem in
    a code fence, and we want the content inside, not the fence itself.
    """
    lines = body.splitlines()
    h_lower = header.lower()
    idx = -1
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith(h_lower):
            idx = i
            break
    if idx < 0:
        return None

    # Skip the header line itself and any immediately-following blank/separator
    j = idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1

    collected: List[str] = []
    in_code_fence = False
    while j < len(lines):
        ln = lines[j]
        stripped = ln.strip()
        if not stripped:
            # Allow a single blank line inside a poem, but stop at two blanks
            # or when the next non-blank line is a markdown header.
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k >= len(lines):
                break
            nxt = lines[k].strip()
            if nxt.startswith("#") and not _is_code_fence(nxt):
                break
            if any(p.search(nxt) for p in _BAD_LINE_PATTERNS) and not _is_code_fence(nxt):
                break
            # Allow the blank as a stanza break
            collected.append("")
            j = k
            continue
        # Code fence: toggle in/out, but don't include the fence line itself
        if _is_code_fence(stripped):
            in_code_fence = not in_code_fence
            j += 1
            continue
        # Outside a code fence, stop at markdown headers or other bad patterns
        if not in_code_fence:
            if stripped.startswith("#"):
                break
            # Allow list-marker-prefixed lines (we'll strip them in normalization)
            if any(p.search(stripped) for p in _BAD_LINE_PATTERNS):
                break
        # Stop at very long lines (likely prose) unless we're inside a code fence
        if not in_code_fence and len(stripped) > MAX_POEM_LINE_LEN:
            break
        # Normalize: strip > blockquote / "1. " / "- " prefixes
        collected.append(_normalize_poem_line(stripped))
        j += 1

    # Drop trailing blanks
    while collected and not collected[-1]:
        collected.pop()
    if len(collected) < MIN_POEM_LINES:
        return None

    text = "\n".join(collected)
    conf = looks_like_poem(text)
    return Poem(
        text=text,
        header=header,
        source_kind="header",
        confidence=conf,
        raw_excerpt="\n".join(lines[idx : j])[:400],
    )


def _extract_tail_blockquote(body: str) -> Optional[Poem]:
    """Find the last contiguous `> ` blockquote in the comment."""
    lines = body.splitlines()
    end = len(lines)
    # Walk backwards to find the last non-empty line
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    if end == 0:
        return None

    # Walk backwards to find contiguous `> ` lines
    start = end
    while start > 0 and lines[start - 1].lstrip().startswith(">"):
        start -= 1
    if start == end:
        return None

    block = lines[start:end]
    # Normalize: strip blockquote markers, list prefixes, and skip code-fence lines
    cleaned: List[str] = []
    for ln in block:
        s = ln.strip()
        if not s or _is_code_fence(s):
            continue
        n = _normalize_poem_line(s)
        if n:
            cleaned.append(n)
    if len(cleaned) < MIN_POEM_LINES:
        return None
    # Reject if any cleaned line is a bad pattern (after normalization)
    if any(any(p.search(ln) for p in _BAD_LINE_PATTERNS) for ln in cleaned):
        return None
    if any(len(ln) > MAX_POEM_LINE_LEN for ln in cleaned):
        return None

    text = "\n".join(cleaned)
    conf = looks_like_poem(text)
    return Poem(
        text=text,
        header="",
        source_kind="tail_blockquote",
        confidence=conf,
        raw_excerpt="\n".join(block)[:400],
    )


def _extract_tail_short_lines(body: str) -> Optional[Poem]:
    """Last cluster of >=2 consecutive short non-markdown lines."""
    lines = body.splitlines()
    # Walk from the end, collect a contiguous block of "good" short lines
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    if end == 0:
        return None

    # Code-fence-aware walk: skip fence lines, but include content inside them.
    # Outside a fence, stop at long/header/bad-pattern lines. Inside a fence,
    # keep collecting (the bot sometimes used fences to wrap a poem).
    start = end
    saw_fence = False
    while start > 0:
        ln = lines[start - 1].strip()
        if not ln:
            # Blank line: stop unless we're inside a code fence
            if saw_fence:
                start -= 1
                continue
            break
        if _is_code_fence(ln):
            saw_fence = True
            start -= 1
            continue
        # Outside fence: be strict
        if not saw_fence:
            if len(ln) > MAX_POEM_LINE_LEN:
                break
            if ln.startswith("#"):
                break
            # Allow list-marker-prefixed lines (we'll normalize them away)
            if any(p.search(ln) for p in _BAD_LINE_PATTERNS):
                break
        start -= 1

    if end - start < MIN_POEM_LINES:
        return None

    # Build the block, normalizing each line and dropping code-fence lines
    block: List[str] = []
    for ln in lines[start:end]:
        s = ln.strip()
        if not s or _is_code_fence(s):
            continue
        n = _normalize_poem_line(s)
        if n:
            block.append(n)
    if len(block) < MIN_POEM_LINES:
        return None
    text = "\n".join(block)
    conf = looks_like_poem(text)
    return Poem(
        text=text,
        header="",
        source_kind="tail_lines",
        confidence=conf,
        raw_excerpt="\n".join(lines[start:end])[:400],
    )


def is_bot_comment(author: str, config: Config) -> bool:
    """True if the comment author looks like the Gemini Code Assist bot."""
    if not author:
        return False
    a = author.lower()
    return any(p.lower() in a for p in config.bot_login_patterns)
