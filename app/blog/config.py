"""Blog settings, and the publishing token - which this module reads and never hands back.

Every setting is an environment variable with a default, read through `app.web.site._env` so the blog
cannot be the one feature with its own idea of what a flag is.

THE TOKEN IS NEVER A VALUE ANYTHING ELSE CAN HOLD. `scripts/publish.sh` sets the standard this repo
holds itself to: the GitHub token is read by git itself from a file, so it is not in the process list,
not in a variable the script can echo, not in the shell history and not in any log line. The same rule
applies here, as far as a long-running server can:

  * the token reaches this process as an environment variable or - preferred - as the CONTENTS OF A FILE
    whose path is the environment variable, so `ps` and `/proc/<pid>/environ` do not carry the secret;
  * nothing in this package logs it, echoes it, puts it in an error body, stores it, or returns it. The
    only thing any caller may ask is `matches(supplied)`, which answers a boolean;
  * the comparison is `hmac.compare_digest`, so a wrong token does not leak its correct prefix through
    timing - the same reason app/admin/auth.py compares the admin user name that way;
  * `problems()` describes HOW the token is configured, never WHAT it is, so the admin page and a config
    check can both say "a token file at ~/.blog_api_token, mode 600" without printing the value.

A box with no token configured serves no publishing API at all: every endpoint answers 404. That is the
admin dashboard's rule - a closed door says 404 rather than 401, because a 401 announces that there is
something here worth guessing at - and it also means a half-finished deploy cannot accept a post.
"""

from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path

from app.web import site

log = logging.getLogger(__name__)


def _env(name: str, default: str) -> str:
    """One reader for every setting on this site. `app/web/indexnow.py` reads its key the same way, so
    the blog is not the one feature with its own idea of what an environment variable is."""
    return site._env(name, default)  # noqa: SLF001 - one resolver, one place


def _flag(name: str, default: str) -> bool:
    return _env(name, default).lower() in ("1", "on", "true", "yes")


# THE ONE SWITCH THAT COULD PUT A POST LIVE WITHOUT A HUMAN. DEFAULT OFF, and it ships off: an API
# create or update lands as a DRAFT whatever the caller asked for while this is off, and /admin/blog is
# the only way a post becomes public. `BLOG_AUTOPUBLISH=on` in /srv/astrology/.env and a restart turns
# it on for posts that pass every check; removing the line and restarting is the whole rollback.
#
# It is deliberately not "trust the writer once it has proved itself" - that is a judgement somebody
# makes about a run of posts, by turning this on, and not a default anybody inherits.
AUTOPUBLISH = _flag("BLOG_AUTOPUBLISH", "off")

# THE MODEL REWRITE PASS. DEFAULT OFF, and it ships off: the deterministic rules do the repairs, and
# anything they cannot fix is written down and published rather than sent to a model. It is off
# because it costs money per post for a result nobody asked to be perfect - `BLOG_AI_FIX=on` in
# /srv/astrology/.env and a restart turns it on, removing the line turns it off again.
AI_FIX = _flag("BLOG_AI_FIX", "off")


def ai_fix() -> bool:
    return _flag("BLOG_AI_FIX", "off")

#: Where the token lives. The FILE is preferred; see the note above about `/proc/<pid>/environ`.
_TOKEN_FILE = _env("BLOG_API_TOKEN_FILE", "")
_TOKEN_ENV_NAME = "BLOG_API_TOKEN"

#: An image upload ceiling, in kilobytes. 2 MiB is generous for a hero image that will be served to a
#: phone and small enough that a stuck upload cannot fill var/. The body is counted as it is read, so
#: this is a real limit and not a Content-Length anybody could lie about.
MAX_IMAGE_KB = max(16, int(_env("BLOG_MAX_IMAGE_KB", "2048") or 2048))
MAX_IMAGE_BYTES = MAX_IMAGE_KB * 1024

#: How many images one post may reasonably need, counted to stop a loop filling the disk by accident.
MAX_IMAGES = max(1, int(_env("BLOG_MAX_IMAGES", "500") or 500))

#: Failed token attempts allowed from one network before the API stops comparing anything, through the
#: limiter app/ai/chat_store.py already owns. The admin sign-in is bounded the same way and for the
#: same reason: a token is guessable in principle and nothing else here would notice somebody trying.
LOGIN_MAX_FAILURES = max(1, int(_env("BLOG_API_MAX_FAILURES", "10") or 10))
LOGIN_WINDOW_MINUTES = max(1, min(55, int(_env("BLOG_API_FAILURE_WINDOW_MINUTES", "15") or 15)))

# ---- what a post must look like ----------------------------------------------------------------------
# These are not taste. Each one is a property some other test on this site already asserts of every
# indexable page, so a post that breaks one would turn a green suite red long after the writer had gone:
# tests/test_pages_i18n.py requires a meta description of 50-230 characters and a title and H1 unique
# site-wide, and tests/test_seo.py requires at least 80 words of body text on an indexed page.
MIN_TITLE_CHARS = 10
MAX_TITLE_CHARS = 70        # a <title> longer than this is truncated in a search result anyway
MIN_SUMMARY_CHARS = 50      # the meta description floor those tests assert
MAX_SUMMARY_CHARS = 230     # and its ceiling
MIN_BODY_WORDS = 300        # a post shorter than this is a note; the site has enough thin pages
MAX_BODY_CHARS = 80_000
MAX_CATEGORIES = 4


def autopublish() -> bool:
    """Read through a function so a caller cannot accidentally capture the flag at import time."""
    return AUTOPUBLISH


# ---- the token ---------------------------------------------------------------------------------------


def _token() -> str:
    """The configured token, or "". PRIVATE, and the only function in this package that holds the value.

    A file is read on every call rather than cached: rotating the token is then "write the file", with no
    restart and no window where the old one still works.
    """
    if _TOKEN_FILE:
        path = Path(_TOKEN_FILE).expanduser()
        try:
            if not path.is_file():
                return ""
            mode = path.stat().st_mode & 0o777
            if mode not in (0o600, 0o400):
                # Refused rather than used: a token file the whole box can read is not a secret, and
                # using it anyway would hide that from whoever set it up. The MODE is logged; the
                # contents never are.
                log.error("BLOG_API_TOKEN_FILE %s is mode %o - it must be 600 or 400, so it is ignored",
                          path, mode)
                return ""
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            log.error("BLOG_API_TOKEN_FILE could not be read: %s", exc)  # the error, not the file's contents
            return ""
    return os.environ.get(_TOKEN_ENV_NAME, "").strip()


def configured() -> bool:
    """True when there is a token to compare against. False means /api/blog answers 404 to everybody."""
    return bool(_token())


def matches(supplied: str) -> bool:
    """Is this the token? The only question anything outside this module may ask about it.

    Constant-time, and False for an unconfigured box: with no token configured nothing can authenticate,
    which is what makes the 404 above true rather than decorative.
    """
    secret = _token()
    if not secret or not supplied:
        return False
    return hmac.compare_digest(supplied.encode("utf-8"), secret.encode("utf-8"))


def how_the_token_is_configured() -> str:
    """One line for the admin page and the operator - the MECHANISM, never the value."""
    if _TOKEN_FILE:
        path = Path(_TOKEN_FILE).expanduser()
        if not path.is_file():
            return f"BLOG_API_TOKEN_FILE is set to {path}, and there is no file there: the API answers 404"
        mode = path.stat().st_mode & 0o777
        if mode not in (0o600, 0o400):
            return f"the token file {path} is mode {mode:o}; it must be 600 or 400, so it is ignored"
        return f"a token file at {path}, mode {mode:o}"
    if os.environ.get(_TOKEN_ENV_NAME, "").strip():
        return (f"the {_TOKEN_ENV_NAME} environment variable. Prefer BLOG_API_TOKEN_FILE: an environment "
                "variable is readable from /proc/<pid>/environ by anything running as this user")
    return f"nothing: set BLOG_API_TOKEN_FILE (preferred) or {_TOKEN_ENV_NAME}. The API answers 404 until then"


def problems() -> list[str]:
    """What an operator would want told about this configuration. Never contains the token."""
    found = []
    if not configured():
        found.append("no publishing token is configured, so /api/blog answers 404 to every caller: "
                     + how_the_token_is_configured())
    elif not _TOKEN_FILE:
        found.append(f"the token comes from the {_TOKEN_ENV_NAME} environment variable; a file named by "
                     "BLOG_API_TOKEN_FILE (mode 600) keeps it out of /proc/<pid>/environ")
    elif len(_token()) < 32:
        # The LENGTH, which is not the token. A short token is a real weakness and saying so costs nothing.
        found.append("the publishing token is shorter than 32 characters; generate one with "
                     '`python -c "import secrets;print(secrets.token_urlsafe(32))"`')
    if AUTOPUBLISH:
        found.append("BLOG_AUTOPUBLISH is ON: a post that passes every check goes live without anybody "
                     "opening /admin/blog")
    return found
