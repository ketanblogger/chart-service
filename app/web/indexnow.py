"""IndexNow: tell Bing and Yandex a URL changed, instead of waiting to be crawled.

WHAT IT IS AND IS NOT. IndexNow is one HTTP call that says "this URL changed". Bing and Yandex accept it;
GOOGLE DOES NOT - its Indexing API is restricted to job postings and livestreams, and using it for
ordinary pages is both against its terms and useless. So this reaches the two engines that take it, and
whether that turns into visits is answerable: the source tracking added earlier will show Bing arrivals
by name, which is the honest test of whether any of this was worth building.

THE KEY IS PUBLIC BY DESIGN. It is served at the site root so the engines can fetch it and confirm that
whoever is submitting URLs controls the site. It is not a secret and there is nothing to leak: it proves
control of the domain, not identity, and anyone can read it by visiting the file.

FAILURE IS NEVER THE CALLER'S PROBLEM. A publish or a window turnover must not fail because Bing is slow,
so every submission is best-effort, short-timeout and logged. Nothing on the site waits for it.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from fastapi import APIRouter, Response

from app.web import site

log = logging.getLogger(__name__)
router = APIRouter()

#: Generated once for this site. Public: it is served at the root for the engines to read.
KEY = site._env("INDEXNOW_KEY", "92de060ac3c1b33514814c43440db07f").strip()

#: One endpoint: api.indexnow.org shares a submission with every participating engine, so submitting to
#: Bing and Yandex separately would be the same URLs twice.
ENDPOINT = "https://api.indexnow.org/indexnow"
TIMEOUT_SECONDS = 10
#: The protocol's own ceiling for one request.
MAX_URLS_PER_REQUEST = 10_000


def key_path() -> str:
    return f"/{KEY}.txt"


def key_file() -> Response:
    """The ownership proof: the key, served as plain text at the site root."""
    return Response(KEY, media_type="text/plain", headers={"Cache-Control": "public, max-age=86400"})


# AN EXACT PATH, NOT A PATTERN. This was registered as "/{key}.txt" with a check inside, and that route
# matched EVERY .txt at the site root - so /robots.txt reached this handler, failed the key check and
# returned 404. A pattern at the root shadows whatever else lives there, and robots.txt is the last file
# on the site that should quietly disappear. The key is known at import time, so the route can be its
# literal path and match nothing else.
if KEY:
    router.add_api_route(key_path(), key_file, methods=["GET"], include_in_schema=False)


def submit(paths: list[str], *, reason: str = "") -> dict:
    """Tell the engines these paths changed. Best effort: returns what happened, never raises.

    `paths` are site-relative ("/horoscope/libra/weekly"); they are sent as absolute URLs on this site's
    own host, which is what the protocol requires and what the key proves control of.
    """
    if not KEY:
        return {"sent": 0, "status": None, "detail": "no INDEXNOW_KEY configured"}
    # ONLY THE REAL SITE TELLS THE ENGINES ANYTHING. A developer regenerating two pages on a laptop was
    # submitting 39 URLs to Bing and Yandex per run, and the 429 that came back is how it was noticed:
    # every local refresh, every test that writes a page, spending the site's real submission quota on
    # content nobody changed. The submission is about the LIVE pages, so a machine that is not serving
    # them has nothing to say about them.
    from app import hardening

    if not hardening.is_production():
        return {"sent": 0, "status": None,
                "detail": f"APP_ENV is not production; {len(paths)} url(s) not submitted"}
    base = site.base_url().rstrip("/")
    host = base.split("//", 1)[-1]
    urls = [f"{base}{path}" if path.startswith("/") else path for path in paths][:MAX_URLS_PER_REQUEST]
    if not urls:
        return {"sent": 0, "status": None, "detail": "nothing to submit"}

    body = json.dumps({"host": host, "key": KEY, "keyLocation": f"{base}{key_path()}",
                       "urlList": urls}).encode()
    request = urllib.request.Request(ENDPOINT, data=body,
                                     headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
        log.info("indexnow: %d url(s) submitted, status %s%s", len(urls), status,
                 f" ({reason})" if reason else "")
        return {"sent": len(urls), "status": status, "detail": ""}
    except urllib.error.HTTPError as exc:
        # 422 means the key did not verify, which is worth seeing rather than swallowing.
        log.warning("indexnow refused %d url(s): %s %s", len(urls), exc.code, exc.reason)
        return {"sent": 0, "status": exc.code, "detail": f"{exc.code} {exc.reason}"}
    except Exception as exc:  # noqa: BLE001 - measurement must never break a publish
        log.warning("indexnow could not be reached: %s", exc)
        return {"sent": 0, "status": None, "detail": str(exc)[:200]}


def submit_rashifal_window(period: str, rashis: list[str] | None = None) -> dict:
    """Called when a rashifal window turns over: those pages have new content at the same URLs, which is
    exactly the case IndexNow exists for."""
    from app.web import i18n

    paths = [i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period)
             for lang in i18n.LANGS
             for rashi in (rashis or i18n.RASHI_KEYS)]
    hubs = [i18n.url_for("rashifal-weekly" if period == "weekly" else "rashifal-hub", lang)
            for lang in i18n.LANGS]
    return submit(paths + hubs, reason=f"{period} window turned over")


def submit_everything() -> dict:
    """Every indexable URL, for the one-off run after a deploy."""
    from app.web import i18n

    return submit([path for path, *_ in i18n.all_paths()], reason="full sitemap")
