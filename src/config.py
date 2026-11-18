"""Configuration loader for the Gemini Poetry scanner.

Reads from environment variables and/or a local .env file in the project root.
Precedence: explicit CLI arg > environment variable > .env file > built-in default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - dotenv is optional
    def load_dotenv(*_a, **_kw):
        return False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

# The consumer Gemini Code Assist bot on GitHub was shut down on 2026-07-17.
# See: https://developers.google.com/gemini-code-assist/docs/deprecations/consumer-code-review
DEFAULT_CUTOFF_DATE = "2026-07-17"

# Username patterns the bot has used on GitHub. The canonical app login is
# `gemini-code-assist[bot]`, but older installs sometimes appeared as
# `gemini-code-assist` or via a `github-actions[bot]` workflow. We match
# case-insensitively on a substring.
BOT_LOGIN_PATTERNS = (
    "gemini-code-assist",
    "gemini-code-assist[bot]",
)

# Poem-section headers the bot historically used. Matched case-insensitively
# as a line prefix. Includes the bold "**Extracted Poem Lines:**" marker that
# appears in the bot's output (and that the original LLM-based extractor
# also produced as its response wrapper).
POEM_HEADERS = (
    "## ✨",
    "## 🌸",
    "## 📜",
    "## 🎭",
    "## 🪻",
    "## 💐",
    "## 🌷",
    "## 🌻",
    "## 🪷",
    "## poem",
    "## here's a poem",
    "## here is a poem",
    "here's a poem",
    "here is a poem",
    "a poem inspired by",
    "## ✍️",
    "**extracted poem lines:**",
    "**extracted poem lines**",
    "**poem:**",
    "**poem**",
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"

# Optional LLM adjudication (used only with `--llm-adjudicate`). The scanner
# is heuristic-only by default; these settings configure the fallback layer.
DEFAULT_LLM_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
DEFAULT_LLM_FALLBACK_MODELS: tuple = ()
# Heuristic candidates at or above this confidence are accepted without
# asking the LLM. Below it (or no candidate at all) triggers adjudication.
DEFAULT_ADJUDICATE_THRESHOLD = 0.5
DEFAULT_LLM_CACHE_DIR = PROJECT_ROOT / "cache" / "llm"
DEFAULT_LLM_MAX_INPUT_CHARS = 6000
DEFAULT_LLM_TIMEOUT = 30
DEFAULT_LLM_MAX_RETRIES = 2
OLLAMA_API_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


@dataclass
class Config:
    github_token: Optional[str] = None
    cutoff_date: str = DEFAULT_CUTOFF_DATE
    output_dir: Path = DEFAULT_OUTPUT_DIR
    log_dir: Path = DEFAULT_LOG_DIR
    bot_login_patterns: tuple = field(default_factory=lambda: BOT_LOGIN_PATTERNS)
    poem_headers: tuple = field(default_factory=lambda: POEM_HEADERS)
    request_timeout: int = 30
    max_retries: int = 3

    # Optional LLM adjudication (see src/llm_adjudicator.py).
    llm_model: Optional[str] = DEFAULT_LLM_MODEL
    llm_fallback_models: tuple = field(default_factory=lambda: DEFAULT_LLM_FALLBACK_MODELS)
    adjudicate_threshold: float = DEFAULT_ADJUDICATE_THRESHOLD
    llm_cache_dir: Optional[Path] = DEFAULT_LLM_CACHE_DIR
    llm_max_input_chars: int = DEFAULT_LLM_MAX_INPUT_CHARS
    llm_timeout: int = DEFAULT_LLM_TIMEOUT
    llm_max_retries: int = DEFAULT_LLM_MAX_RETRIES
    ollama_api_url: str = OLLAMA_API_URL

    @property
    def has_token(self) -> bool:
        return bool(self.github_token)

    @property
    def auth_header(self) -> dict:
        if self.has_token:
            return {
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "gemini-poetry-scanner/2.0",
            }
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "gemini-poetry-scanner/2.0",
        }


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_models(name: str) -> tuple:
    raw = os.getenv(name) or ""
    return tuple(m.strip() for m in raw.split(",") if m.strip())


def load_config(env_path: Optional[Path] = None) -> Config:
    """Load configuration from .env file and environment."""
    env_path = env_path or DEFAULT_ENV_PATH
    if env_path.exists():
        load_dotenv(env_path)

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        token = token.strip()

    cutoff = os.getenv("CUTOFF_DATE") or DEFAULT_CUTOFF_DATE

    out_dir = Path(os.getenv("OUTPUT_DIR")) if os.getenv("OUTPUT_DIR") else DEFAULT_OUTPUT_DIR
    log_dir = Path(os.getenv("LOG_DIR")) if os.getenv("LOG_DIR") else DEFAULT_LOG_DIR

    llm_cache_dir = (
        Path(os.getenv("LLM_CACHE_DIR"))
        if os.getenv("LLM_CACHE_DIR")
        else DEFAULT_LLM_CACHE_DIR
    )

    return Config(
        github_token=token,
        cutoff_date=cutoff,
        output_dir=out_dir,
        log_dir=log_dir,
        llm_model=os.getenv("LLM_MODEL") or DEFAULT_LLM_MODEL,
        llm_fallback_models=_env_models("LLM_FALLBACK_MODELS"),
        adjudicate_threshold=_env_float("ADJUDICATE_THRESHOLD", DEFAULT_ADJUDICATE_THRESHOLD),
        llm_cache_dir=llm_cache_dir,
        llm_max_input_chars=_env_int("LLM_MAX_INPUT_CHARS", DEFAULT_LLM_MAX_INPUT_CHARS),
        llm_timeout=_env_int("LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT),
        llm_max_retries=_env_int("LLM_MAX_RETRIES", DEFAULT_LLM_MAX_RETRIES),
        ollama_api_url=os.getenv("OLLAMA_HOST", OLLAMA_API_URL),
    )
