""""Sky right now": where the nine grahas actually are, for the home page's right rail.

ENGINE ONLY. No AI call is made anywhere under this module, and none ever should be - it is nine sidereal
positions from `app.engine.current_transits`, named in the reader's language. That is the whole point of it
as a panel: it is the one part of the page that is live, and it costs nothing per view.

CACHED, because it is on the busiest page of the site and every view would otherwise recompute nine
positions. The refresh interval is minutes rather than seconds on purpose - the fastest graha is Chandra at
roughly half a degree an hour, so a five-minute cache is at worst two arc-minutes stale, which is far below
the degree this panel prints. A slow graha does not move a printed digit in a day.

The names come from `app/rashifal/i18n.py`, the one table that owns Marathi spellings, so this panel says
मंगळ and शनी rather than the engine's stored Hindi - the same defect that reached the paid book on
2026-09-29 and the page titles on 2026-09-30.
"""

import datetime as dt
import logging
import threading
import time

from app.rashifal.i18n import graha_name, rashi_name

log = logging.getLogger(__name__)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Five minutes. See the module docstring for why this is not seconds: Chandra moves ~0.5°/h, so the printed
# degree is stale by at most two arc-minutes, and nothing else on the panel moves at all on this scale.
TTL_SECONDS = 300

_lock = threading.Lock()
_cached: tuple[float, dict] | None = None


def _rows(language: str) -> list[dict]:
    from app.engine import current_transits

    transits = current_transits()
    rows = []
    for position in transits["grahas"].values():
        graha, sign = position["graha"], position["sign"]
        rows.append({
            "key": graha["key"],
            "graha": graha_name(graha, language),
            # `sign["index"]` is ALREADY 1-based - it comes from `sign_info`, which takes a 0-based index
            # and returns a 1-based one - and `rashi_name` wants the 1-based form. Adding one here walked off
            # the end of the table for Pisces and dropped the whole panel, silently, exactly as designed.
            "sign": rashi_name(sign["index"], language),
            # The whole degree only. A panel that printed 12°47'47" would be asserting a precision it
            # refreshes every five minutes, and the second figure would be wrong before anybody read it.
            "degree": int(position["degree"]),
            "retrograde": bool(position["retrograde"]),
        })
    return rows


def snapshot(language: str) -> dict | None:
    """`{"rows": [...], "at": datetime}` for this language, or None if the engine could not answer.

    None rather than an exception or an empty panel: this is decoration on a page whose job is the kundali
    form, and an ephemeris failure must cost the page nothing. The caller drops the panel.

    All three languages are computed together and cached together, because the positions are identical and
    only the names differ - three separate caches would run the ephemeris three times for one instant.
    """
    global _cached

    now = time.time()
    with _lock:
        if _cached is not None and now - _cached[0] < TTL_SECONDS:
            return _cached[1].get(language)
        try:
            at = dt.datetime.now(IST)
            # The reader is in India and the panel says "as of": a UTC clock beside a sidereal position is
            # a time nobody here reads without converting it first.
            stamp = f"{at:%H:%M} IST"
            fresh = {lang: {"rows": _rows(lang), "at": at, "as_of": stamp} for lang in ("en", "hi", "mr")}
        except Exception:  # noqa: BLE001 - an ephemeris failure may not take the home page down
            log.exception("sky-right-now could not be computed; the panel will be dropped")
            return None
        _cached = (now, fresh)
        return fresh.get(language)


def reset_cache() -> None:
    """Tests only: the cache is keyed on nothing but time, so a test that freezes time needs it emptied."""
    global _cached

    with _lock:
        _cached = None
