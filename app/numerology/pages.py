"""The numerology calculator page: a form, and the numbers it works out.

SERVER-RENDERED, AND A POST. The result could have been a GET with the name and date in the query
string, which would make it linkable - and would also put somebody's name and date of birth in our
access log and in their browser history, and in the Referer header of every link they clicked next.
The rest of this site keeps birth details out of URLs for that reason and this page does the same.

NO JAVASCRIPT. The arithmetic is addition; sending a script to do it would mean the page did not
work where script is blocked, for no gain a reader could name.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import json

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from app.numerology import core
from app.numerology.copy import PAGE, PLANETS, SECTIONS
from app.web import i18n

#: Where the checked-in sample images live, so a missing one is detected rather than 404'd.
STATIC_SAMPLES = pathlib.Path(__file__).resolve().parents[2] / "app" / "static" / "img" / "sample"


def _date_error(fields: dict, lang: str) -> str | None:
    """Why the date could not be read, in the reader's language, or None if it was fine.

    THE DISTINCTION MATTERS TO A READER. An empty form needs "enter a day, a month and a year"; a
    filled one with 31 February needs to be told that date does not exist. Returning the same
    sentence for both makes the first reader think they have made a mistake they have not.
    """
    from app.numerology.copy import ERRORS

    if not any((fields.get(key) or "").strip() for key in ("day", "month", "year")):
        return None                                    # nothing typed: not an error, just a fresh page
    if _parse_date(fields) is not None:
        return None
    filled = all((fields.get(key) or "").strip() for key in ("day", "month", "year"))
    return ERRORS[lang]["bad_date" if filled else "no_date"]


def _parse_date(fields: dict) -> dt.date | None:
    """The date from three separate fields: day, month and year.

    NOT A NATIVE DATE INPUT. The browser renders one in its own locale, so 1991-04-03 shows as
    "04/03/1991" to a reader in India and reads as 4 March rather than 3 April. The rest of this
    site replaced every native date input for exactly that reason, with a test that those two dates
    cannot be confused - putting one back on a new page would undo that fix one page at a time.
    """
    try:
        day = int(fields.get("day") or 0)
        month = int(fields.get("month") or 0)
        year = int(fields.get("year") or 0)
        return dt.date(year, month, day)
    except (TypeError, ValueError):
        return None


async def _submitted(request: Request) -> dict:
    """The form's fields, read without python-multipart - the same parser app/blog/admin.py uses."""
    from urllib.parse import parse_qsl

    media = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if media != "application/x-www-form-urlencoded":
        return {}
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > 4096:        # a name and a date; anything larger is not this form
            return {}
    return dict(parse_qsl(body.decode("utf-8", "replace")))


def _report_price() -> int:
    """The numerology report's own price, so the ask box can say what the chat pack is NOT."""
    from app.payments import catalogue

    return catalogue.item("numerology-report").price_inr


def _consultation_path(lang: str, *, question: str = "") -> str:
    """Where a numerology CTA goes. The CHOSEN QUESTION rides in the URL; the reader does not.

    These links used to carry ?name=...&date=..., and the comment here called it "nothing sensitive
    and nothing new" on the grounds that the reader had typed both into a public calculator one
    screen ago. That reasoning was wrong. What a reader types into a form reaches one server and is
    gone; what is put in a URL is written into the access log of every hop, handed to third parties
    in the Referer header, kept in browser history, and copied intact by anybody who shares the
    link. A name and a date of birth together identify a person, and a shared link would hand a
    stranger's identity to whoever received it.

    The name and the date now travel in sessionStorage, written by the calculator page and read by
    the consultation page in the same tab - never leaving the browser. The question stays in the
    URL because it is the reader's own words about a topic, carries no identity, and a link to
    "ask about my career" is a reasonable thing to be able to share.

    WITHOUT JAVASCRIPT the handover simply does not happen and the consultation asks for a name and
    a date, which is the form it shows anyway. Nothing breaks; one convenience is lost.
    """
    from urllib.parse import urlencode

    params = {"numerology": "1"}
    if question:
        params["q"] = question
    return f"{i18n.url_for('consultation', lang)}?{urlencode(params)}"


def _numerology_tiers() -> dict:
    """{mini_price, mini_messages, pack_price, pack_messages} for the copy, from the catalogue.

    One source for the four numbers a reader is quoted. They are the tiers a NUMEROLOGY session is
    offered - questions only, never a bundled report - and the same entries the paywall and the till
    read, so the page cannot advertise one thing and charge another.
    """
    from app.payments import catalogue

    mini = catalogue.item(catalogue.NUMEROLOGY_MINI)
    pack = catalogue.item(catalogue.NUMEROLOGY_PACK)
    return {"mini_price": mini.price_inr, "mini_messages": mini.messages,
            "pack_price": pack.price_inr, "pack_messages": pack.messages}


def _ask_box(lang: str, *, on_mulank_page: bool = False, name: str = "", born=None) -> dict:
    """The paid consultation offer under a result: the chips, the price, and where it goes.

    THE CALCULATORS STAY FREE. This is the only paid thing on these pages and it uses the chat pack
    that already exists - no new payment flow, and the price is on the box BEFORE anybody starts,
    because a reader should know what a thing costs while deciding whether to want it.

    THE NUMBERS NOW RIDE INTO THE CHAT. This docstring used to say they did not, and that the box
    opened the consultation with only a topic set - which is exactly the dead end the proprietor
    found: every chip landed in the chart chat, which asked for a birth time and a city this page
    never collects, and the reader's numbers and chosen question were gone. The path carries the
    name, the date and the tapped question now, and the chat recomputes the numbers from that date
    (POST /api/consultation/start-numerology).

    `on_mulank_page` because the nine mulank pages have no calculator on them, so the lead cannot
    tell a reader there that their numbers are "worked out above".
    """
    from app.numerology.copy import ASK
    from app.web import pages as web_pages

    offer = web_pages.chat_offer()
    words = ASK[lang]
    # THE TIERS A NUMEROLOGY CHAT ACTUALLY SELLS, from the catalogue rather than from the chart
    # consultation's offer. This box used to quote the chart pack's price and promise its bundled
    # kundali report - a reading this consultation cannot produce, because it never asks for a birth
    # time or a city. Reading the numbers from the catalogue is what keeps the copy and the till
    # saying the same thing.
    tiers = _numerology_tiers()
    return {
        "ask": {
            "heading": words["heading"],
            "lead": words["lead_mulank" if on_mulank_page else "lead"].format(
                free=offer["free_messages"], report_price=_report_price(), **tiers),
            "chips": words["chips"],
            "cta": words["cta"],
            "note": words["note"],
            "path": _consultation_path(lang),
            # EACH CHIP CARRIES ITS OWN QUESTION, so the one the reader tapped is the one the input
            # box opens on. They were all the same link before, and the choice was lost.
            "chip_links": [{"text": chip,
                            "path": _consultation_path(lang, question=chip)}
                           for chip in words["chips"]],
        }
    }


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["numerology"]:
        _add(router, page_context, respond, _json_ld, lang)
        _add_check(router, page_context, respond, _json_ld, lang)
        _add_lo_shu(router, page_context, respond, _json_ld, lang)
        _add_report(router, page_context, respond, _json_ld, lang)
        for number in range(1, 10):
            _add_mulank(router, page_context, respond, _json_ld, lang, number)


def _report_cta(lang: str, *, name: str = "", born=None, result: dict | None = None) -> dict:
    """The one paid REPORT offer, shown under every numerology result and on every mulank page.

    It links to the report's own page rather than buying from here: somebody should see what is in a
    thing before they buy it, and the sample of each section is what that page is for.

    IT CARRIES THE NAME AND DATE when it is shown under a result, so the reader does not type their
    own name and birthday a second time on the next page to buy a report about them. The mulank
    pages pass neither, because they have no calculator and nothing to carry.
    """
    from app.numerology.copy import REPORT
    from app.web.pages import prices

    price = prices()["numerology-report"]
    words = REPORT[lang]
    return {"report_cta": {
        "heading": words["cta_from_result"],
        "body": words["cta_from_result_body"].format(price=price),
        # The primary label only where there IS a calculation - "my report" means nothing on a
        # mulank page, which has no numbers of the reader's in it.
        "button": (words["cta_button_primary"] if result else words["cta_button"]).format(price=price),
        "bar": words["bar"].format(price=price),
        "dismiss": words["bar_dismiss"],
        "path": _report_path(lang),
        # WHAT THE FORM POSTS. Empty on a mulank page, which has no calculator and nothing to carry;
        # the template then renders a plain link rather than a form with nothing in it.
        "carry": _carry_fields(name=name, born=born),
        "personal": _personal_line(lang, result),
        "preview": _report_preview(lang),
    }}


#: One page of the real report, per language, rendered from a document generated for an INVENTED
#: person (Asha Kulkarni, 14 May 1990) by scripts/sample_preview.py. Never a customer's, and never
#: a mock-up: a reader deciding whether to pay should see the thing being sold.
_PREVIEW_SIZE = (642, 909)


def _report_preview(lang: str) -> dict | None:
    """The sample page image, or None if that language's file is not checked in."""
    from app.numerology.copy import REPORT

    name = f"{lang}-numerology-5.webp"
    if not (STATIC_SAMPLES / name).exists():
        return None            # a missing picture is a card without one, never a broken image
    return {"src": f"/static/img/sample/{name}",
            "width": _PREVIEW_SIZE[0], "height": _PREVIEW_SIZE[1],
            "alt": REPORT[lang]["preview_alt"]}


def _join(items, lang: str) -> str:
    """"5, 6 and 7" - in the page's own language, and never a bare comma list for two items."""
    from app.numerology.copy import CARD

    items = [str(i) for i in items]
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} {CARD[lang]['and']} {items[-1]}"


def _personal_line(lang: str, result: dict | None) -> str:
    """What THIS reader's grid says, read back to them, from the calculation they are looking at.

    Only two things are claimed, and both are sections the report actually has: the Lo Shu reading
    and the spelling alternatives. No count of spellings is promised - the writer's brief asks for
    alternatives without fixing how many, and a card that says "3 options" when the report gives two
    has lied for money.
    """
    from app.numerology.copy import CARD, LO_SHU, PLANE_VERB

    if not result or not result.get("lo_shu"):
        return ""
    words, grid = CARD[lang], result["lo_shu"]
    missing = list(grid.get("missing") or [])
    line = (words["missing"].format(numbers=_join(missing, lang)) if missing
            else words["missing_none"])

    complete = [key for key, done in (grid.get("planes") or {}).items() if done]
    if complete:
        # The plane's own name without its "(4-9-2)" tail: that belongs in the table, not a sentence.
        names = [LO_SHU[lang]["plane_names"][key].split(" (")[0] for key in complete]
        many = len(complete) > 1
        line += words["planes"].format(
            planes=_join(names, lang),
            plane_word=words["plane_word_many" if many else "plane_word_one"],
            plane_verb=PLANE_VERB[lang]["many" if many else "one"]).rstrip()
    else:
        line += words["planes_none"]
    return line + words["tail"]


def _carry_fields(*, name: str = "", born=None) -> dict:
    """The hidden fields that take a reader's own entry to the report form, in a POST body.

    Returns {} when there is nothing to carry, which is the mulank pages' case.
    """
    if not born:
        return {}
    day = born if hasattr(born, "day") else None
    if day is None:
        try:
            day = dt.date.fromisoformat(str(born))
        except ValueError:
            return {}
    return {"name": (name or "").strip()[:60], "day": day.day, "month": day.month, "year": day.year}


def _report_path(lang: str) -> str:
    """The report page. NO QUERY STRING, EVER.

    This used to append ?name=...&day=...&month=...&year=..., and the comment beside the other
    builder called that "nothing sensitive and nothing new" because the reader had typed it into a
    public calculator one screen ago. That was wrong, and the difference is where the data ends up:
    a form post goes to one server and is gone, while a URL is written into the access log of every
    hop, sent to third parties in the Referer header, kept in browser history, and carried intact
    by anybody who copies the link to a friend. A name and a date of birth together identify a
    person. They travel in the POST body now.
    """
    return i18n.url_for("numerology-report", lang)


def _add_report(router, page_context, respond, _json_ld, lang: str) -> None:
    """The report's landing page: what is inside, a sample of each section, the price, the button."""
    from app.numerology.copy import REPORT
    from app.web.pages import prices

    path = i18n.url_for("numerology-report", lang)

    def _render(request: Request, entered=None, error=None):
        from app.web import seo as _seo
        from app.web import pages as web_pages

        entered = entered or {}
        price = prices()["numerology-report"]
        words = {key: (value.format(price=price) if isinstance(value, str) and "{price}" in value
                       else value)
                 for key, value in REPORT[lang].items()}
        born = _parse_date(entered)
        context = page_context("numerology-report", lang)
        context.update(
            error=error, words=words, price=price,
            entered_name=(entered.get("name") or "").strip()[:60],
            entered_day=entered.get("day", ""), entered_month=entered.get("month", ""),
            entered_year=entered.get("year", ""),
            month_names=web_pages.content(lang).UI["month_names"],
            years=list(range(dt.date.today().year, 1899, -1)),
            day_label=PAGE[lang]["day_label"], month_label=PAGE[lang]["month_label"],
            year_label=PAGE[lang]["year_label"], name_label=PAGE[lang]["name_label"],
            # THE BUTTON ONLY APPEARS ONCE THERE IS SOMETHING TO BUY WITH. Until a name and a date
            # are in, there is nothing to put on it, and a buy button that cannot work is worse
            # than one that is not there yet.
            order=({"product": "numerology-report", "price": price,
                    "payload": json.dumps({"name": (entered.get("name") or "").strip()[:60],
                                           "born": born.isoformat()}, ensure_ascii=False)}
                   if born and (entered.get("name") or "").strip() else None),
            numerology_path=i18n.url_for("numerology", lang),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (words["h1"], path)]))])
        return respond(request, "numerology_report.html", context)

    def report_page(request: Request):
        # PREFILLED FROM THE CALCULATOR. Somebody who has just typed their name and birthday into
        # the calculator should not type both again on the next page to buy a report about them.
        # It is a PREFILL and not a submission: nothing is validated into an error here, because the
        # reader has not pressed anything yet, and an error on arrival would be about the link
        # rather than about anything they did. A date that cannot exist simply prefills nothing.
        q = request.query_params
        entered = {"name": (q.get("name") or "").strip()[:60]}
        parts = {key: (q.get(key) or "").strip() for key in ("day", "month", "year")}
        if all(parts.values()) and _parse_date(parts):
            entered.update(parts)
        return _render(request, entered=entered)

    async def report_post(request: Request):
        fields = await _submitted(request)
        return _render(request, entered=fields, error=_date_error(fields, lang))

    router.add_api_route(path, report_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"numerology-report-{lang}")
    router.add_api_route(path, report_post, methods=["POST"], response_class=HTMLResponse,
                         name=f"numerology-report-post-{lang}")


#: WHICH DAYS OF THE MONTH GIVE EACH MULANK. 7 is the 7th, 16th and 25th; the page says so because
#: that is how a reader checks the number is theirs before reading a word about it.
_DAYS_FOR = {n: [d for d in range(1, 32) if core.reduce_to_digit(d) == n] for n in range(1, 10)}


def _mulank_faqs(number: int, lang: str) -> list[tuple[str, str]]:
    """The FAQ for one mulank page, ASSEMBLED FROM THE PAGE'S OWN DATA rather than written out nine
    times in three languages.

    Every answer comes from something already on the page - the dates, the ruling planet, and
    core.fit_groups, which is the single source for every number pairing on this site - so the FAQ
    cannot contradict the section above it, and the compatibility symmetry test covers these answers
    as well. Nothing here is generated at view time.
    """
    from app.numerology.copy import FAQ, PLANETS

    words = FAQ[lang]
    groups = core.fit_groups(number)
    joined = PAGE[lang].get("list_join", ", ")

    def numbers(key: str) -> str:
        return joined.join(str(n) for n in groups[key]) or PAGE[lang]["none"]

    filled = {
        "number": number,
        "days": joined.join(str(d) for d in _DAYS_FOR[number]),
        "planet": PLANETS[lang][number],
        "strong": numbers("strong"),
        "good": numbers("good"),
        "neutral": numbers("neutral"),
    }
    return [(question.format(**filled), answer.format(**filled))
            for question, answer in words.values()]


def _add_mulank(router, page_context, respond, _json_ld, lang: str, number: int) -> None:
    """One mulank page. The copy was written once by a model under the site's checker and committed;
    see scripts/generate_mulank.py. There is no model on this path and no cost per view."""
    path = i18n.url_for("mulank", lang, number=number)

    def mulank_page(request: Request):
        from app.web import seo as _seo

        try:
            from app.numerology.mulank_copy import MULANK
        except ImportError:                 # not generated yet: the page is simply not served
            raise HTTPException(status_code=404, detail="not found")
        page = (MULANK.get(str(number)) or {}).get(lang)
        if not page:
            raise HTTPException(status_code=404, detail="not found")

        context = page_context("mulank", lang, number=str(number))
        context.update(
            page=page, number=number, days=_DAYS_FOR[number], ruler=core.RULERS[number],
            title=page["title"], meta_description=page["meta"], h1=page["h1"],
            numerology_path=i18n.url_for("numerology", lang),
            back_label=PAGE[lang]["back_to_calculator"],
            others=[{"number": n, "path": i18n.url_for("mulank", lang, number=n)}
                    for n in range(1, 10) if n != number],
            **_ask_box(lang, on_mulank_page=True),
            **_report_cta(lang),
            # The paragraphs the page already had, now under headings, plus an FAQ built from the
            # page's own data. The planet is named in the page's language: it used to print
            # core.RULERS straight out, so a Hindi reader was told their number is ruled by "Moon".
            sections=SECTIONS[lang], planet=PLANETS[lang][number],
            faqs=_mulank_faqs(number, lang),
            chips_label=PAGE[lang]["mulank_chips_label"],
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (page["h1"], path)])),
                     _json_ld(_seo.faq_page(_mulank_faqs(number, lang)))])
        return respond(request, "mulank.html", context)

    router.add_api_route(path, mulank_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"mulank-{number}-{lang}")


def _add_lo_shu(router, page_context, respond, _json_ld, lang: str) -> None:
    """The Lo Shu grid on its own page - no name field in the way of the thing being searched for."""
    from app.numerology.copy import LO_SHU, PAGE

    path = i18n.url_for("lo-shu", lang)
    words = {**PAGE[lang], **LO_SHU[lang]}

    def _render(request: Request, result=None, entered=None, error=None):
        from app.web import seo as _seo
        from app.web import pages as web_pages

        entered = entered or {}
        context = page_context("lo-shu", lang)
        context.update(
            error=error, words=words, result=result,
            entered_day=entered.get("day", ""), entered_month=entered.get("month", ""),
            entered_year=entered.get("year", ""),
            month_names=web_pages.content(lang).UI["month_names"],
            years=list(range(dt.date.today().year, 1899, -1)),
            planes=core.PLANES,
            title=words["title"], meta_description=words["meta"], h1=words["h1"],
            numerology_path=i18n.url_for("numerology", lang),
            # THE SAME GRID, THE SAME CARD. This page draws the Lo Shu and nothing else, so the
            # personalised line is exactly as true here. It has no name field, so only the date is
            # carried - the report form asks for the name it still needs.
            **_report_cta(lang, born=_parse_date(entered), result={"lo_shu": result} if result else None),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (words["h1"], path)]))])
        return respond(request, "lo_shu.html", context)

    def lo_shu_page(request: Request):
        return _render(request)

    async def lo_shu_result(request: Request):
        fields = await _submitted(request)
        born = _parse_date(fields)
        if born is None:
            return _render(request, entered=fields, error=_date_error(fields, lang))
        return _render(request, result=core.lo_shu(born), entered=fields)

    router.add_api_route(path, lo_shu_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"lo-shu-{lang}")
    router.add_api_route(path, lo_shu_result, methods=["POST"], response_class=HTMLResponse,
                         name=f"lo-shu-post-{lang}")


def _add_check(router, page_context, respond, _json_ld, lang: str) -> None:
    """The mobile / vehicle / house / business number checker.

    ONE PAGE, FOUR KINDS. Four separate pages would say the same thing about different digits and
    compete with each other for the same phrases - and the arithmetic does not care which kind of
    number it is, so four pages would also be four places for it to drift.
    """
    from app.numerology.copy import CHECK, PAGE

    path = i18n.url_for("number-check", lang)
    words = {**CHECK[lang], "back_to_calculator": PAGE[lang]["back_to_calculator"]}

    def _render(request: Request, result=None, entered=None, error=None):
        from app.web import seo as _seo
        from app.web import pages as web_pages

        entered = entered or {}
        context = page_context("number-check", lang)
        context.update(
            error=error, words=words, result=result,
            entered_number=entered.get("number", ""),
            entered_day=entered.get("day", ""), entered_month=entered.get("month", ""),
            entered_year=entered.get("year", ""),
            month_names=web_pages.content(lang).UI["month_names"],
            years=list(range(dt.date.today().year, 1899, -1)),
            title=words["title"], meta_description=words["meta"], h1=words["h1"],
            numerology_path=i18n.url_for("numerology", lang),
            **_report_cta(lang),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (words["h1"], path)]))])
        return respond(request, "number_check.html", context)

    def check_page(request: Request):
        return _render(request)

    async def check_result(request: Request):
        fields = await _submitted(request)
        born = _parse_date(fields)
        # THE DATE IS OPTIONAL HERE. Somebody checking a number they are about to buy may not want
        # to type their birthday for it, and the number's own total does not need one - so they get
        # the number, and the fit only if they asked for it.
        result = core.check_number(
            fields.get("number") or "",
            mulank=core.mulank(born) if born else None,
            bhagyank=core.bhagyank(born) if born else None)
        # THE PAGE ALREADY EXPLAINS AN UNUSABLE NUMBER ITSELF, in its own words and in all three
        # languages - "there were no digits in that" - and tests/test_numerology_tools.py checks
        # that copy. My first version replaced it with a generic error and blanked the result, which
        # took away the better message. So the result always goes through, and `error` here is only
        # ever about the DATE: it is optional on this form, so a date that was typed and cannot
        # exist would otherwise make the fit section silently disappear.
        return _render(request, result=result, entered=fields, error=_date_error(fields, lang))

    router.add_api_route(path, check_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"number-check-{lang}")
    router.add_api_route(path, check_result, methods=["POST"], response_class=HTMLResponse,
                         name=f"number-check-post-{lang}")


def _add(router, page_context, respond, _json_ld, lang: str) -> None:
    path = i18n.url_for("numerology", lang)
    words = PAGE[lang]

    def _render(request: Request, result=None, name="", entered=None, error=None):
        from app.web import seo as _seo
        from app.web import pages as web_pages

        entered = entered or {}
        context = page_context("numerology", lang)
        context.update(
            error=error, words=words, result=result, entered_name=name,
            entered_day=entered.get("day", ""), entered_month=entered.get("month", ""),
            entered_year=entered.get("year", ""),
            month_names=web_pages.content(lang).UI["month_names"],
            years=list(range(dt.date.today().year, 1899, -1)),
            title=words["title"], meta_description=words["meta"], h1=words["h1"],
            chaldean=core.CHALDEAN, lo_shu_rows=core.LO_SHU_ROWS,
            kundali_path=i18n.url_for("kundali", lang),
            mulank_links=[{"number": n, "path": i18n.url_for("mulank", lang, number=n)}
                          for n in range(1, 10)],
            # KEYED BY NUMBER as well as listed, so a result card can link to its own page without
            # the template searching the list for it.
            mulank_paths={n: i18n.url_for("mulank", lang, number=n) for n in range(1, 10)},
            **_ask_box(lang, name=name, born=(result or {}).get("born")),
            **_report_cta(lang, name=name, born=(result or {}).get("born"), result=result),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (words["h1"], path)]))])
        return respond(request, "numerology.html", context)

    def numerology_page(request: Request):
        return _render(request)

    async def numerology_result(request: Request):
        fields = await _submitted(request)
        name = (fields.get("name") or "").strip()[:60]
        born = _parse_date(fields)
        if born is None:
            # WITH A MESSAGE. This used to re-render silently - same fields, no result, nothing said -
            # so 31 February looked like a broken button.
            return _render(request, name=name, entered=fields,
                           error=_date_error(fields, lang))
        return _render(request, result=core.profile(name, born), name=name, entered=fields)

    router.add_api_route(path, numerology_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"numerology-{lang}")
    router.add_api_route(path, numerology_result, methods=["POST"], response_class=HTMLResponse,
                         name=f"numerology-post-{lang}")
