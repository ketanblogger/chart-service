"""/sade-sati/capricorn - when Sade Sati runs for a Moon sign, with the dates Saturn's motion gives.

Sade Sati is the roughly seven-and-a-half years Saturn spends in the twelfth sign from the natal Moon, the
sign itself, and the second from it. People search for it by rashi and in a particular state of mind, so
these pages carry three things: whether it is running NOW for that sign, the exact dates of the previous,
current and next cycle, and the three phases inside the current one.

EVERY DATE COMES FROM `engine.sadesati.cycles`, which reads Saturn's real sidereal ingresses. Nothing here
adds thirty months to anything: Saturn retrogrades, and over 1950-2100 two thirds of its sign crossings are
returns to a sign it had already left, so a phase has a first entry and a final exit with gaps between. The
page says how many times Saturn came back, because that is why a phase runs longer than two and a half
years and why two published tables disagree about the same cycle.

THE TONE IS DELIBERATE. Somebody arriving here has usually been told Sade Sati is a disaster. The copy says
what it is, gives the dates, and does not embroider; the pages are honest about Saturn being slow and
demanding without predicting ruin, and the remedies section is kept to what the tradition actually
prescribes rather than anything we would sell.
"""
from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.engine import sadesati
from app.rashifal.i18n import format_date
from app.web import i18n, pages
from app.web.rashifal import _breadcrumbs, _json_ld, _respond
from app.web.routes import page_context

log = logging.getLogger(__name__)
router = APIRouter()

#: The reader is told which phase is running in words, not by a key name.
PHASE_KEYS = ("rising", "peak", "setting")


def _page(request: Request, lang: str, slug: str) -> HTMLResponse:
    try:
        rashi = i18n.rashi_key(slug)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None

    # One canonical address per tree: the slug this tree spells is the only one that answers here.
    if slug != i18n.rashi_slug(rashi, lang):
        raise HTTPException(status_code=404, detail="not found")

    names = i18n.rashi_names(rashi, lang)
    copy = pages.get("sade-sati-rashi", lang, **names)
    path = i18n.url_for("sade-sati-rashi", lang, rashi=rashi)

    index = i18n.RASHI_KEYS.index(rashi) + 1
    cycles = sadesati.cycles(index, dt.datetime.now(dt.timezone.utc))
    # IN THIS READER'S LANGUAGE AND CALENDAR WORDS. The engine speaks ISO, which is right for an engine
    # and wrong on a page: "2049-03-06" asks a Marathi reader to parse a format before reading a date.
    # The site already has the formatter the rashifal pages use, so there is no second month table here.
    cycles = _localise(cycles, lang)

    context = page_context("sade-sati-rashi", lang, rashi=rashi)
    crumbs = [
        (context["ui"]["home"], i18n.url_for("home", lang)),
        (copy.nav_label, i18n.url_for("sade-sati", lang)),
        (copy.h1, path),
    ]
    context.update(
        copy=copy, names=names, rashi=rashi, cycles=cycles,
        title=copy.title, h1=copy.h1, meta_description=copy.meta_description,
        calculator_path=i18n.url_for("sade-sati", lang),
        kundali_path=i18n.url_for("kundali", lang),
        chat_path=i18n.url_for("consultation", lang),
        rashifal_path=i18n.url_for("rashifal-rashi", lang, rashi=rashi),
        crumbs=crumbs, json_ld=[_json_ld(_breadcrumbs(crumbs))],
    )
    return _respond(request, "sade_sati_rashi.html", context)


for _lang in i18n.LANGS:
    def _route(request: Request, rashi: str, _lang: str = _lang) -> HTMLResponse:
        return _page(request, _lang, rashi)

    router.add_api_route(i18n.PAGES["sade-sati-rashi"][_lang], _route, methods=["GET"],
                         response_class=HTMLResponse, name=f"sade-sati-rashi-{_lang}")


def _localise(cycles: dict, lang: str) -> dict:
    """A COPY with every date spelled in the reader's language. The engine's ISO strings stay the source;
    this only changes how they are written, so a formatting choice can never move a date.

    A COPY AND NOT AN IN-PLACE REWRITE. Rewriting the engine's own dict is safe only as long as nothing
    caches it, and this module is built to be cached - the segment table under `cycles()` already is. The
    day `cycles()` gains a cache whose key does not change per request, an in-place rewrite would hand
    the next reader the previous reader's language: Devanagari dates rendered into an English page, in
    production, in one language only. Not mutating somebody else's data costs one dict copy.
    """
    out = dict(cycles)
    for key in ("previous", "current", "next"):
        cycle = out.get(key)
        if not cycle:
            continue
        fresh = dict(cycle)
        for group in ("phases", "periods"):
            if cycle.get(group):
                fresh[group] = [{**item, **{field: format_date(item[field], lang)
                                            for field in ("start", "end") if item.get(field)}}
                                for item in cycle[group]]
        for field in ("start", "end"):
            if cycle.get(field):
                fresh[field] = format_date(cycle[field], lang)
        out[key] = fresh
    return out
