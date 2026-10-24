"""/rashi/makar-in-english - the English name of a rashi, and why the question is not as simple as it looks.

WHY THIS PAGE EXISTS. Search Console shows people typing "makar rashi in english", "vrishchik rashi 2027
english", "kanya rashi in english". They know their rashi by its Indian name and want the English one.
That is a one-word answer, and giving only the word would waste the visit.

THE THING WORTH SAYING. The English name they are matching it to is almost always being used for a SUN
sign - that is what a western horoscope means by "Capricorn" - while a rashi is a MOON sign, and the two
are the same for roughly one person in twelve. Somebody who has just learned that "Makar is Capricorn" and
then reads a Capricorn sun-sign horoscope is reading about somebody else. So the page answers the question
in its first sentence, says plainly what the difference is, and offers the free chart that settles it.

The reading underneath is TODAY'S, from the same store the rashifal pages read - not a second copy of the
engine, and never written here.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from app.rashifal import i18n as words
from app.rashifal import store
from app.web import i18n, pages
from app.web.rashifal import _breadcrumbs, _json_ld, _now, _respond
from app.web.routes import page_context

log = logging.getLogger(__name__)
router = __import__("fastapi").APIRouter()


def _page(request: Request, lang: str, rashi_slug: str) -> HTMLResponse:
    try:
        rashi = i18n.rashi_key(rashi_slug)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None

    # The slug in the URL is the INDIAN name in every tree, because the query is. A request for the
    # English spelling is not a second URL for the same page - it is a 404, so there is one canonical
    # address and nothing to choose between.
    if rashi_slug != i18n.rashi_slug(rashi, "hi"):
        raise HTTPException(status_code=404, detail="not found")

    names = i18n.rashi_names(rashi, lang)
    copy = pages.get("rashi-in-english", lang, **names)
    path = i18n.url_for("rashi-in-english", lang, rashi=rashi)

    today = None
    try:
        today = store.get_page(rashi, "today")
    except Exception:  # noqa: BLE001 - the page answers its question with or without a reading
        log.exception("today's reading could not be read for %s", rashi)

    # The rashi goes through, so the hreflang alternates can be built for the OTHER trees - without it
    # every alternate is a url_for call with no parameter and the page 500s before it renders.
    context = page_context("rashi-in-english", lang, rashi=rashi)
    # (name, path) TUPLES: _breadcrumbs unpacks each item as a pair, so a dict unpacks over its KEYS and
    # every crumb's URL becomes the base plus the literal string "path". The template reads the same pairs.
    crumbs = [
        (context["ui"]["home"], i18n.url_for("home", lang)),
        (copy.h1, path),
    ]
    context.update(
        copy=copy, names=names, rashi=rashi, today=today,
        title=copy.title, h1=copy.h1, meta_description=copy.meta_description,
        rashifal_path=i18n.url_for("rashifal-rashi", lang, rashi=rashi),
        kundali_path=i18n.url_for("kundali", lang),
        chat_path=i18n.url_for("consultation", lang),
        crumbs=crumbs, json_ld=[_json_ld(_breadcrumbs(crumbs))],
    )
    return _respond(request, "rashi_in_english.html", context)


for _lang in i18n.LANGS:
    # The literal "-in-english" stays IN the route, so the suffix is part of the address rather than
    # something the handler has to strip - and a request without it does not reach this page at all.
    _template = i18n.PAGES["rashi-in-english"][_lang]

    def _route(request: Request, rashi: str, _lang: str = _lang) -> HTMLResponse:
        return _page(request, _lang, rashi)

    router.add_api_route(_template, _route, methods=["GET"],
                         response_class=HTMLResponse, name=f"rashi-in-english-{_lang}")
