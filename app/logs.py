"""One place that decides whether an `app.*` log line reaches the journal.

`uvicorn --log-level info` configures uvicorn's OWN loggers and nothing else. Our loggers are
`logging.getLogger(__name__)` under `app.`, they have no handler, and the root logger has none either - so
Python falls back to `logging.lastResort`, which emits WARNING and above to stderr and DROPS everything
below it. The consequence was invisible until a real refund arrived on 2026-09-29: the refund's WARNING
reached the journal, and every `log.info()` line already in the code - order created, order PAID, invoice
number, report generated - never has, on any deploy.

So the level lives here, one handler on the `app` logger, and third-party libraries are left alone: httpx and
anthropic at INFO would bury our own lines in per-request noise. `propagate` stays on, because pytest's
caplog captures through the root logger and turning it off would make every logging assertion in the suite
pass by capturing nothing.

LOG_LEVEL in the environment overrides it (DEBUG when chasing something, WARNING to go quiet).
"""

import logging
import os
import sys

APP_LOGGER = "app"
DEFAULT_LEVEL = "INFO"
_MARK = "_astrology_handler"


def configure(level: str | None = None) -> logging.Logger:
    """Idempotent: called at import and safe to call again. Returns the `app` logger."""
    log = logging.getLogger(APP_LOGGER)
    wanted = (level or os.getenv("LOG_LEVEL") or DEFAULT_LEVEL).strip().upper()
    log.setLevel(getattr(logging, wanted, logging.INFO))
    if not any(getattr(handler, _MARK, False) for handler in log.handlers):
        handler = logging.StreamHandler(sys.stderr)
        # No timestamp: journald stamps every line itself, and a second clock in the message is one more
        # thing that can disagree with the first.
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        setattr(handler, _MARK, True)
        log.addHandler(handler)
    return log
