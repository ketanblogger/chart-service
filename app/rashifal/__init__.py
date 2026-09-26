"""Rashifal automation (Phase 7): engine transit brief -> Claude -> stored page content.

- periods.py   the 12 rashi slugs, the 5 period slugs and their IST windows
- brief.py     the "transit brief" per (rashi, period): engine facts only, nothing for the AI to compute
- prompts.py   system prompt, user prompt and the structured-output schema
- generate.py  brief -> model -> structure / safety / fact checks -> store (keeps old content on failure)
- store.py     SQLite content store keyed by (rashi, period) + the scheduler lease
- scheduler.py optional in-process APScheduler (RASHIFAL_SCHEDULER=1); scripts/rashifal_refresh.py is the CLI
- sitemap.py   the 60 permanent URLs + lastmod for Phase 8's sitemap.xml

The public pages (app/web/rashifal.py) read the store and the engine only - they never call the AI.
"""

from .periods import PERIOD_SLUGS, RASHI_SLUGS

__all__ = ["PERIOD_SLUGS", "RASHI_SLUGS"]
