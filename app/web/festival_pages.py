"""/muhurta/lakshmi-puja-2026 - the festival's date, and its puja window in the reader's own city.

WHY A PAGE PER CITY AND NOT ONE TIME. The puja window is set by sunset and by the rising sign, and both
depend on where the reader is: Lakshmi Puja 2026 is 17:54-19:50 in Delhi and 18:27-20:27 in Mumbai. A
single time printed for the whole country is wrong for almost all of it.

THE DATES AND WINDOWS ARE CHECKED AGAINST PUBLISHED PANCHANGS, which is the one thing a page like this
must not get wrong - a family acts on it. 2026 Dhanteras 6 November and Lakshmi Puja 8 November, both
confirmed; the Delhi and Mumbai windows match a published panchang to the minute at all four ends.

BHAI DOOJ IS NOT HERE. Our Dwitiya times agree with the published ones to the minute, but the panchangs
disagree about which day that makes the festival, because on 10 November 2026 Dwitiya covers only part of
aparahna. The disagreement is about convention, not arithmetic, so it is reported and not published.

The city picker is a plain GET form. The site's CSP has no 'unsafe-inline' and the page must work with no
JavaScript at all, so there is nothing to execute: choosing a city reloads this page.
"""
from __future__ import annotations

import datetime as dt
import re
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.engine import cities as city_table
from app.engine import festivals
from app.rashifal.i18n import format_date
from app.web import i18n, muhurta_routes, pages, site
from app.web.rashifal import _breadcrumbs, _json_ld, _respond
from app.web.routes import page_context

log = logging.getLogger(__name__)
router = APIRouter()

#: How each festival is named in each tree. The engine's key is a slug, not a name a reader should see.
NAMES = {
    "dhanteras": {"en": "Dhanteras", "hi": "धनतेरस", "mr": "धनत्रयोदशी"},
    "lakshmi-puja": {"en": "Lakshmi Puja", "hi": "लक्ष्मी पूजा", "mr": "लक्ष्मीपूजन"},
}

#: The transliteration a Devanagari-tree reader types into a search box. The Hindi and Marathi titles
#: carry it beside the Devanagari name, which is the site's standing rule for those trees.
LATIN = {"dhanteras": "Dhanteras", "lakshmi-puja": "Lakshmi Puja"}


def _page(request: Request, lang: str, festival: str) -> HTMLResponse:
    """The festival's NEXT date, whenever the page is asked for.

    The year is computed here rather than carried in the URL. A dated page goes stale the day after
    the festival - and worse, the hub stopped linking it then, which is how six indexed pages came
    to have nothing pointing at them.
    """
    if festival not in i18n.FESTIVAL_SLUGS:
        raise HTTPException(status_code=404, detail="not found")
    year, _ = festivals.upcoming(festival, _today())

    wanted = (request.query_params.get("city") or "").strip()
    # An unknown city is not an error page: it is the eight-city table with nothing picked, because a
    # stale or mistyped link should still show the reader the festival.
    picked = None
    if wanted:
        try:
            picked = festivals.windows(festival, year, wanted)
        except KeyError:
            picked = None

    rows = festivals.all_cities(festival, year)
    reference = picked or rows[0]
    if not reference.get("date"):
        log.error("no date computed for %s %s", festival, year)
        raise HTTPException(status_code=404, detail="not found")

    name = NAMES[festival][lang]
    fields = {"festival": name, "year": str(year), "latin": LATIN[festival],
              "date": format_date(reference["date"].isoformat(), lang)}
    copy = pages.get("festival", lang, **fields)
    labels = {key: pages.fill(text, **fields, city=reference["city"]["name"],
                              tithi=_tithi_name(reference["tithi_at_observance"], lang),
                              named_tithi=_tithi_name(reference["tithi"], lang))
              for key, text in copy.extra.items()}
    path = i18n.url_for("festival", lang, festival=festival)

    # page_context builds the URL, which no longer carries a year; the COPY still names it, and gets
    # it through  above ("Dhanteras 2027").
    context = page_context("festival", lang, festival=festival)
    # THE MUHURTA FINDER IS BEHIND A FLAG, and site.MUHURTA is off by default - so it is neither a
    # breadcrumb nor a call to action unless it is actually being served. A link to a page the app does
    # not route is a 404 we put there ourselves, and it would have shipped on all six of these pages.
    finder = muhurta_routes.path_for(lang) if site.MUHURTA else None
    crumbs = [(context["ui"]["home"], context["home_path"])]
    if finder:
        crumbs.append((muhurta_routes.COPY[lang]["heading"], finder))
    crumbs.append((copy.h1, path))
    context.update(
        copy=copy, labels=labels, festival=festival, festival_name=name, year=year,
        rows=rows, picked=picked, reference=reference,
        title=copy.title, h1=copy.h1, meta_description=copy.meta_description,
        city_options=[city["name"] for city in city_table.CITIES],
        form_action=path,
        muhurta_path=finder,
        chat_path=i18n.url_for("consultation", lang),
        crumbs=crumbs, json_ld=[_json_ld(_breadcrumbs(crumbs))],
    )
    return _respond(request, "festival.html", context)


def _tithi_name(tithi: dict | None, lang: str) -> str:
    """The tithi in the reader's script, with its paksha, from the engine's own spellings."""
    if not tithi:
        return ""
    if lang in ("hi", "mr"):
        return f"{tithi['paksha']['devanagari']} {tithi['devanagari']}"
    return f"{tithi['paksha']['name']} {tithi['name']}"


#: "<festival>-2026" - the dated form that is already in Google's index.
_DATED = re.compile(r"^(?P<festival>[a-z-]+?)-(?P<year>20\d\d)$")


def _today() -> dt.date:
    """IST, like every other date this site decides - a festival turns over on India's calendar."""
    from app.rashifal.periods import IST

    return dt.datetime.now(IST).date()


for _lang in i18n.LANGS:
    def _route(request: Request, festival: str, _lang: str = _lang):
        # ONE ROUTE FOR BOTH FORMS. The festival slugs contain hyphens ("lakshmi-puja"), so a
        # separate "/muhurat/{festival}-{year}" pattern would shadow the evergreen one depending on
        # registration order. Parsing the trailing year here cannot be got wrong by a reordering.
        dated = _DATED.match(festival)
        if dated and dated.group("festival") in i18n.FESTIVAL_SLUGS:
            return RedirectResponse(
                i18n.url_for("festival", _lang, festival=dated.group("festival")), status_code=301)
        return _page(request, _lang, festival)

    router.add_api_route(i18n.PAGES["festival"][_lang], _route, methods=["GET"],
                         response_class=HTMLResponse, name=f"festival-{_lang}")
