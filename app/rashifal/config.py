"""Rashifal settings. Env vars with defaults (loaded from `.env` by app/ai/config.py).

| Env var | Default | Meaning |
|---|---|---|
| `RASHIFAL_MODEL` | `claude-haiku-4-5` | The model chosen for the batch job. `claude-sonnet-5` / `claude-opus-5` are the quality levers. |
| `RASHIFAL_EFFORT` | `low` | `output_config.effort` (ignored by Haiku 4.5, which has no adaptive thinking / effort) |
| `RASHIFAL_MAX_TOKENS` | `16000` | Output cap per call (all languages + thinking) |
| `RASHIFAL_MAX_ATTEMPTS` | `2` | 1 generation + 1 regeneration with the checker's feedback |
| `RASHIFAL_LANGUAGES` | `en,hi,mr` | Languages written in ONE call per page. `en` is always included. All are required for a page to be complete. |
| `RASHIFAL_BATCH` | `1` | Message Batches API (50% cheaper, asynchronous) for runs of 4+ pages; smaller runs and `--sync` call directly. `0` = never batch |
| `RASHIFAL_BATCH_TIMEOUT_MINUTES` | `180` | Give up waiting for a batch after this long (old content stays) |
| `RASHIFAL_SPLIT_LANGUAGES` | `1` | One AI call per language (3 batch items per page): each language is written from the brief, not translated. `0` = one call returns all languages (cheaper input, but Haiku then translates its English badly) |
| `RASHIFAL_MODEL_EN` / `_HI` / `_MR` | `_MR` = `claude-sonnet-5` | Per-language model override (needs split mode). Marathi defaults to Sonnet: see LANGUAGE_MODEL_DEFAULTS. |
| `RASHIFAL_SCHEDULER` | `0` | `1` = run the in-process APScheduler inside uvicorn (see scheduler.py) |
"""

import os
from dataclasses import dataclass, replace

from app.ai.config import Settings, get_settings

SUPPORTED_LANGUAGES = ("en", "hi", "mr")


@dataclass(frozen=True)
class RashifalSettings:
    model: str
    effort: str
    max_tokens: int
    max_attempts: int
    languages: tuple[str, ...]
    batch: bool
    batch_timeout_minutes: int
    split_languages: bool = True
    language_models: tuple[tuple[str, str], ...] = ()  # (("mr", "claude-sonnet-5"), ...)

    def model_for(self, languages: tuple[str, ...]) -> str:
        if len(languages) == 1:
            return dict(self.language_models).get(languages[0], self.model)
        return self.model


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def languages() -> tuple[str, ...]:
    """Configured languages in canonical order; unknown codes are ignored and `en` is always present."""
    wanted = {code.strip().lower() for code in os.getenv("RASHIFAL_LANGUAGES", "en,hi,mr").split(",")}
    return tuple(code for code in SUPPORTED_LANGUAGES if code == "en" or code in wanted)


# Marathi is written by a stronger model than the other two, by default and not by a setting on one server.
#
# Haiku's Marathi drifted into Hindi and, worse, invented Marathi-looking words - सुरटण्यासाठी, लांबमेय,
# हळूवारीचा - which a Marathi reader spots instantly and which no word list can predict, because you can only
# add a word after it has been published. The false-friends gate in generate.py catches the recurring
# substitutions; the model is the only lever on the ones nobody has seen yet.
#
# It lives here rather than in a .env so that it travels with the repository and a test can assert it. An env
# var still overrides it. NOTE: per-language models only apply in split mode (see RashifalSettings.model_for),
# so RASHIFAL_SPLIT_LANGUAGES=0 silently puts Marathi back on the cheap model.
LANGUAGE_MODEL_DEFAULTS = {"mr": "claude-sonnet-5"}


def get_rashifal_settings() -> RashifalSettings:
    return RashifalSettings(
        model=os.getenv("RASHIFAL_MODEL", "claude-haiku-4-5"),
        effort=os.getenv("RASHIFAL_EFFORT", "low"),
        max_tokens=int(os.getenv("RASHIFAL_MAX_TOKENS", "16000")),
        max_attempts=max(1, int(os.getenv("RASHIFAL_MAX_ATTEMPTS", "2"))),
        languages=languages(),
        batch=_flag("RASHIFAL_BATCH", "1"),
        batch_timeout_minutes=int(os.getenv("RASHIFAL_BATCH_TIMEOUT_MINUTES", "180")),
        split_languages=_flag("RASHIFAL_SPLIT_LANGUAGES", "1"),
        language_models=tuple(
            (code, os.getenv(f"RASHIFAL_MODEL_{code.upper()}", "").strip() or LANGUAGE_MODEL_DEFAULTS[code])
            for code in SUPPORTED_LANGUAGES
            if os.getenv(f"RASHIFAL_MODEL_{code.upper()}", "").strip() or code in LANGUAGE_MODEL_DEFAULTS),
    )


def scheduler_enabled() -> bool:
    return _flag("RASHIFAL_SCHEDULER")


def client_settings(settings: RashifalSettings) -> Settings:
    """app.ai Settings for ClaudeClient, with the rashifal model / effort / output cap swapped in."""
    return replace(get_settings(), model=settings.model, effort=settings.effort, max_tokens=settings.max_tokens)
