"""Optional LiteLLM adjudication for ambiguous bot comments.

The scanner is heuristic-only by default. This module adds an opt-in second
opinion: when the heuristic extractor finds nothing, or finds a candidate
below `Config.adjudicate_threshold`, the comment can be sent to an LLM.

Design notes
============
* LiteLLM is imported lazily. If it is not installed (or no model is
  configured), `LlmAdjudicator.available` is False and the scanner silently
  stays heuristic-only.
* The model is asked for a JSON object, never free prose, so parsing is
  deterministic and scaffolding cannot leak into the archive.
* Provider calls are made with `temperature=0`, retries, a timeout, and
  `drop_params=True`; models are tried in order (primary then fallbacks).
* Responses are cached on disk, keyed by model set + body hash, so reruns do
  not pay twice for the same adjudication.
* Lines returned by the model are re-checked with the heuristic scorer before
  being accepted, which blocks hallucinated prose.

Expected model output::

    {"poem_found": true, "lines": ["line one", "line two"],
     "confidence": 0.9, "reason": "short rhyming blockquote after a --- rule"}

or::

    {"poem_found": false, "lines": [], "confidence": 0.1, "reason": "prose only"}
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .poem_extractor import _normalize_poem_line, looks_like_poem

log = logging.getLogger(__name__)

# Bump when the prompt or verdict schema changes so stale cache entries are
# ignored.
CACHE_SCHEMA = "v1"

POEM_SYSTEM_PROMPT = """\
You extract the short poem that an AI code-review bot appended to a GitHub \
pull-request review comment. The poem is usually the LAST creative block in the \
comment, often after a `---` rule, under a header such as "## ✨", "## 🌸", \
"## Poem", "## Here's a poem", "**Extracted Poem Lines:**", or a trailing \
`> ` blockquote.

A POEM IS:
- 2-8 short lines (typically <= 80 characters), often rhyming, one thought per line.

IT IS NOT:
- technical feedback, summaries, changelogs, or merge-readiness prose
- bulleted/numbered lists of review findings
- code blocks, URLs, footnotes, signatures, or status/boilerplate text
- the section header itself, markdown fences, blockquote markers, or any
  commentary about having extracted something

Rules:
1. Return the poem verbatim, one line per element of the "lines" array,
   preserving order and punctuation.
2. Strip `>` blockquote markers, list markers (`1.`, `-`), code fences, and bold
   labels from each line. Never add commentary.
3. If there is no poem, return {"poem_found": false, "lines": []}.
4. Always reply with a single JSON object and nothing else. Do not wrap it in
   Markdown fences.
"""

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_HR_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")


@dataclass
class LlmVerdict:
    """Result of one adjudication call."""

    poem_found: bool
    lines: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    model: str = ""
    raw: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LlmVerdict":
        return cls(
            poem_found=bool(data.get("poem_found", False)),
            lines=list(data.get("lines", []) or []),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            reason=str(data.get("reason", "") or ""),
            model=str(data.get("model", "") or ""),
            raw=str(data.get("raw", "") or ""),
        )


def _extract_json_object(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model reply (fences tolerated)."""
    if not text:
        return None
    candidates: List[str] = []
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    for cand in candidates:
        s = cand.strip()
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end <= start:
            continue
        try:
            obj = json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _clean_lines(raw: Any) -> List[str]:
    """Normalize model-provided lines using the heuristic normalizer."""
    if isinstance(raw, str):
        raw = raw.splitlines()
    if not isinstance(raw, (list, tuple)):
        return []
    out: List[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s or s.startswith("```"):
            continue
        normalized = _normalize_poem_line(s)
        if normalized:
            out.append(normalized)
    return out


def _clamp_confidence(value: Any) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, conf))


def _candidate_region(body: str, config: Config) -> str:
    """Return the part of the comment most likely to contain the poem.

    Prefers the block starting at the last poem header or horizontal rule;
    otherwise falls back to the tail of the comment. Length is capped so a
    giant `<details>` boilerplate block does not blow up the token budget.
    """
    lines = body.splitlines()
    start = 0
    headers = tuple(h.lower() for h in config.poem_headers)
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if _HR_RE.match(line):
            start = i
            continue
        if any(stripped.startswith(h) for h in headers if h):
            start = i
    region = "\n".join(lines[start:]).strip()
    max_chars = config.llm_max_input_chars
    if len(region) > max_chars:
        region = "\n...\n" + region[-max_chars:]
    return region


class LlmAdjudicator:
    """Opt-in LLM second opinion for ambiguous comments.

    Args:
        config: Scanner configuration (model, fallbacks, thresholds, cache).
        model: Override the primary model.
        fallback_models: Models tried in order if the primary fails.
        cache_dir: Directory for the JSON response cache. None disables it.
        enabled: Set False to force heuristic-only behavior.
    """

    def __init__(
        self,
        config: Config,
        *,
        model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        cache_dir: Optional[Path] = None,
        enabled: bool = True,
    ):
        self.config = config
        self.model = (model or config.llm_model or "").strip()
        if fallback_models is not None:
            self.fallback_models = [m.strip() for m in fallback_models if m and m.strip()]
        else:
            self.fallback_models = list(config.llm_fallback_models)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._litellm: Any = None
        self._cache: Optional[Dict[str, dict]] = None
        if enabled and self.model:
            self._litellm = self._import_litellm()

    @staticmethod
    def _import_litellm() -> Any:
        try:
            return importlib.import_module("litellm")
        except ImportError:
            log.warning(
                "litellm is not installed. Install it with "
                "`pip install litellm` or run without --llm-adjudicate."
            )
            return None

    @property
    def available(self) -> bool:
        return self._litellm is not None and bool(self.model)

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    def _cache_path(self) -> Optional[Path]:
        return self.cache_dir / "adjudication_cache.json" if self.cache_dir else None

    def _load_cache(self) -> Dict[str, dict]:
        if self._cache is not None:
            return self._cache
        self._cache = {}
        path = self._cache_path()
        if path and path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._cache = loaded
            except Exception as exc:  # corrupt cache must never break a scan
                log.warning("Ignoring unreadable LLM cache %s: %s", path, exc)
        return self._cache

    def _cache_key(self, body: str) -> str:
        material = "|".join([CACHE_SCHEMA, self.model, *self.fallback_models, body])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _store_cache(self, key: str, verdict: LlmVerdict) -> None:
        cache = self._load_cache()
        cache[key] = verdict.to_dict()
        path = self._cache_path()
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not write LLM cache %s: %s", path, exc)

    # ------------------------------------------------------------------ #
    # Provider calls
    # ------------------------------------------------------------------ #
    def _complete(self, messages: List[dict], model: str) -> Any:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1024,
            "timeout": self.config.llm_timeout,
            "num_retries": self.config.llm_max_retries,
            "drop_params": True,
        }
        # `base_url` is only meaningful for local Ollama servers; passing it
        # for hosted providers routes their traffic at localhost.
        if "ollama" in model.lower() and self.config.ollama_api_url:
            kwargs["base_url"] = self.config.ollama_api_url

        try:
            return self._litellm.completion(
                response_format={"type": "json_object"}, **kwargs
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "response_format" in msg or "json" in msg:
                log.debug("%s rejected response_format (%s); retrying without it", model, exc)
                return self._litellm.completion(**kwargs)
            raise

    @staticmethod
    def _message_content(response: Any) -> str:
        try:
            content = response.choices[0].message.content
            if content:
                return content
        except Exception:
            pass
        return str(response)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def adjudicate(self, body: str) -> Optional[LlmVerdict]:
        """Ask the configured models whether `body` contains a poem.

        Returns None when adjudication is unavailable or every model failed.
        """
        if not self.available or not body or not body.strip():
            return None

        key = self._cache_key(body)
        cached = self._load_cache().get(key)
        if cached is not None:
            log.debug("LLM adjudication cache hit for %s", key[:12])
            return LlmVerdict.from_dict(cached)

        region = _candidate_region(body, self.config)
        messages = [
            {"role": "system", "content": POEM_SYSTEM_PROMPT},
            {"role": "user", "content": f"GitHub comment:\n{region}"},
        ]

        raw = ""
        used_model = ""
        for model in [self.model, *self.fallback_models]:
            try:
                response = self._complete(messages, model)
            except Exception as exc:
                log.warning("LLM adjudication failed for %s: %s", model, exc)
                continue
            raw = self._message_content(response)
            used_model = model
            break

        if not raw:
            log.warning("All adjudication models failed (%s)", self.model)
            return None

        obj = _extract_json_object(raw)
        if obj is None:
            log.warning("Could not parse a JSON verdict from %s: %r", used_model, raw[:200])
            return None

        found = bool(obj.get("poem_found", False))
        lines = _clean_lines(obj.get("lines", []))
        confidence = _clamp_confidence(obj.get("confidence", 0.8))
        reason = str(obj.get("reason", "") or "").strip()

        if found and not lines:
            found = False
            reason = (reason + " (model returned no lines)").strip()

        if found:
            # Heuristic gate: reject model output that looks like prose.
            score = looks_like_poem("\n".join(lines))
            if score < 0.15:
                log.info(
                    "LLM verdict rejected by heuristic gate (score %.2f): %s",
                    score, lines[:3],
                )
                found = False
            else:
                confidence = max(confidence, score)

        verdict = LlmVerdict(
            poem_found=found,
            lines=lines,
            confidence=confidence,
            reason=reason,
            model=used_model,
            raw=raw,
        )
        self._store_cache(key, verdict)
        return verdict
