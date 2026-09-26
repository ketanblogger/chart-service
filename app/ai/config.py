"""AI-layer settings. Everything is an env var with a default, loaded from `.env` at the repo root.

| Env var | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | - | Claude API key (required for live calls only) |
| `REPORT_MODEL` | `claude-sonnet-5` | The model chosen for paid reports (2026-09-21). |
| `REPORT_EFFORT` | `medium` | `output_config.effort`: low / medium / high / xhigh / max |
| `REPORT_MAX_TOKENS` | `32000` | Output cap per call (streamed, so no HTTP timeout issue) |
| `REPORT_MAX_ATTEMPTS` | `2` | Flat reports: 1 generation + N-1 regenerations when the checks fail |
| `BOOK_PART_ATTEMPTS` | `3` | The Kundali book: attempts per PART. A retry is one part (~Rs 2.5); a part that gives up costs the whole book (~Rs 25), so this is higher than `REPORT_MAX_ATTEMPTS` |
| `REPORT_CONCURRENCY` | `3` | How many parts of the book are written at once, after the first has warmed the prompt cache |
| `REPORT_FALLBACKS` | `default` | Server-side refusal fallback (`default` or `off`) |
| `REPORT_TIMEOUT_SECONDS` | `300` | Per-request timeout |
| `REPORT_API_RETRIES` | `3` | SDK retries on 408/409/429/5xx/connection errors |
| `REPORTS_UNLOCKED` | `0` | `1` = POST /api/report is open (dev/test only). See app/ai/entitlement.py |
| `REPORTS_DIR` | `var/reports` | On-disk report cache |
| `USD_INR` | `88` | Only used to print cost estimates in rupees |
| `REPORT_COMPACT_DATA` | `1` | `1` = the model reads the compact chart encoding (app/ai/compact.py, ~1/3 of the input tokens); `0` = the raw engine JSON |
| `CHAT_MODEL` | `claude-sonnet-5` | Consultation chat model. `claude-sonnet-5` is ~60% cheaper per message |
| `CHAT_EFFORT` | `medium` | Measured live on Sonnet 5: medium costs the same per message as low (~Rs 1) and writes cleaner Hindi/Marathi |
| `CHAT_MAX_TOKENS` | `4000` | Output cap per chat turn (thinking + reply) |
| `CHAT_FREE_MESSAGES` | `2` | Free AI replies per user before the paywall; 2 is the shipped default |
| `CHAT_PACK_MESSAGES` / `CHAT_PACK_PRICE_INR` | `10` / `99` | The paid pack shown on the paywall |
| `CHAT_RATE_PER_MINUTE` | `6` | Max chat messages per user per minute (3x that per IP bucket) |
| `CHAT_FREE_PER_IP_PER_DAY` | `10` | Max free AI replies per IP bucket per day, whatever the cookie/birth details |
| `SESSION_SECRET` | generated | Signs the user-id cookie. Set it in production; dev generates var/session_secret |
| `TRUST_PROXY` | `0` | `1` = take the client IP from X-Forwarded-For (only behind your own reverse proxy) |
| `APP_DB` | `var/app.db` | SQLite file (app/db.py) |
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # does not override variables already set in the environment

# USD per million tokens (input, output). Source: claude-api skill model table, cached 2026-06-24.
PRICES_PER_MTOK = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


@dataclass(frozen=True)
class Settings:
    model: str
    effort: str
    max_tokens: int
    max_attempts: int
    book_part_attempts: int
    fallbacks: str
    timeout_seconds: float
    api_retries: int
    reports_dir: Path
    usd_inr: float
    compact_data: bool = True


@dataclass(frozen=True)
class ChatSettings:
    model: str
    effort: str
    max_tokens: int
    free_messages: int
    pack_messages: int
    pack_price_inr: int
    rate_per_minute: int
    free_per_ip_per_day: int


def get_chat_settings() -> ChatSettings:
    return ChatSettings(
        model=os.getenv("CHAT_MODEL", "claude-sonnet-5"),
        effort=os.getenv("CHAT_EFFORT", "medium"),
        max_tokens=int(os.getenv("CHAT_MAX_TOKENS", "4000")),
        free_messages=int(os.getenv("CHAT_FREE_MESSAGES", "2")),
        pack_messages=int(os.getenv("CHAT_PACK_MESSAGES", "10")),
        pack_price_inr=int(os.getenv("CHAT_PACK_PRICE_INR", "99")),
        rate_per_minute=int(os.getenv("CHAT_RATE_PER_MINUTE", "6")),
        free_per_ip_per_day=int(os.getenv("CHAT_FREE_PER_IP_PER_DAY", "10")),
    )


def get_settings() -> Settings:
    """Read at call time (not import time) so tests and scripts can change the environment."""
    reports_dir = Path(os.getenv("REPORTS_DIR", "var/reports"))
    if not reports_dir.is_absolute():
        reports_dir = ROOT / reports_dir
    return Settings(
        model=os.getenv("REPORT_MODEL", "claude-sonnet-5"),
        effort=os.getenv("REPORT_EFFORT", "medium"),
        max_tokens=int(os.getenv("REPORT_MAX_TOKENS", "32000")),
        max_attempts=max(1, int(os.getenv("REPORT_MAX_ATTEMPTS", "2"))),
        book_part_attempts=max(1, int(os.getenv("BOOK_PART_ATTEMPTS", "3"))),
        fallbacks=os.getenv("REPORT_FALLBACKS", "default"),
        timeout_seconds=float(os.getenv("REPORT_TIMEOUT_SECONDS", "300")),
        api_retries=int(os.getenv("REPORT_API_RETRIES", "3")),
        reports_dir=reports_dir,
        usd_inr=float(os.getenv("USD_INR", "88")),
        compact_data=os.getenv("REPORT_COMPACT_DATA", "1").strip() != "0",
    )


def has_credentials() -> bool:
    """True if the Anthropic SDK can find credentials (API key, auth token, or an `ant auth login` profile)."""
    if os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip():
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


def estimate_cost_usd(model: str, usage: dict) -> float | None:
    """Cost of one call from its token usage. None if the model's price is not in the table."""
    price = PRICES_PER_MTOK.get(model)
    if price is None:
        return None
    price_in, price_out = price
    cost = (
        usage.get("input_tokens", 0) * price_in
        + usage.get("cache_creation_input_tokens", 0) * price_in * CACHE_WRITE_MULTIPLIER
        + usage.get("cache_read_input_tokens", 0) * price_in * CACHE_READ_MULTIPLIER
        + usage.get("output_tokens", 0) * price_out
    )
    return round(cost / 1_000_000, 6)
