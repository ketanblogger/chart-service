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
import json

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from app.numerology import core
from app.numerology.copy import PAGE
from app.web import i18n


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


def _ask_box(lang: str) -> dict:
    """The paid consultation offer under a result: the chips, the price, and where it goes.

    THE CALCULATORS STAY FREE. This is the only paid thing on these pages and it uses the chat pack
    that already exists - no new payment flow, and the price is on the box BEFORE anybody starts,
    because a reader should know what a thing costs while deciding whether to want it.

    WHAT IS NOT DONE YET, and is deliberately not faked: the computed numbers do not ride into the
    chat. Doing that means extending the chat's own context (app/ai/chat_prompts.py builds a
    <chart_data> block from a birth chart) and carrying the numbers through sign-in, which is a
    change inside a live paid feature. Until then this box opens the consultation with the topic
    set, exactly as every other page on this site starts a chat.
    """
    from app.numerology.copy import ASK
    from app.web import pages as web_pages

    offer = web_pages.chat_offer()
    words = ASK[lang]
    return {
        "ask": {
            "heading": words["heading"],
            "lead": words["lead"].format(free=offer["free_messages"],
                                         messages=offer["pack_messages"],
                                         price=offer["price_inr"]),
            "chips": words["chips"],
            "cta": words["cta"],
            "note": words["note"],
            "path": f"{i18n.url_for('consultation', lang)}?topic=numerology",
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


def _report_cta(lang: str) -> dict:
    """The one paid REPORT offer, shown under every numerology result and on every mulank page.

    It links to the report's own page rather than buying from here: somebody should see what is in a
    thing before they buy it, and the sample of each section is what that page is for.
    """
    from app.numerology.copy import REPORT
    from app.web.pages import prices

    price = prices()["numerology-report"]
    words = REPORT[lang]
    return {"report_cta": {
        "heading": words["cta_from_result"],
        "body": words["cta_from_result_body"].format(price=price),
        "button": words["cta_button"],
        "path": i18n.url_for("numerology-report", lang),
    }}


def _add_report(router, page_context, respond, _json_ld, lang: str) -> None:
    """The report's landing page: what is inside, a sample of each section, the price, the button."""
    from app.numerology.copy import REPORT
    from app.web.pages import prices

    path = i18n.url_for("numerology-report", lang)

    def _render(request: Request, entered=None):
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
            words=words, price=price,
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
        return _render(request)

    async def report_post(request: Request):
        return _render(request, entered=await _submitted(request))

    router.add_api_route(path, report_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"numerology-report-{lang}")
    router.add_api_route(path, report_post, methods=["POST"], response_class=HTMLResponse,
                         name=f"numerology-report-post-{lang}")


#: WHICH DAYS OF THE MONTH GIVE EACH MULANK. 7 is the 7th, 16th and 25th; the page says so because
#: that is how a reader checks the number is theirs before reading a word about it.
_DAYS_FOR = {n: [d for d in range(1, 32) if core.reduce_to_digit(d) == n] for n in range(1, 10)}


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
            **_ask_box(lang),
            **_report_cta(lang),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (page["h1"], path)]))])
        return respond(request, "mulank.html", context)

    router.add_api_route(path, mulank_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"mulank-{number}-{lang}")


def _add_lo_shu(router, page_context, respond, _json_ld, lang: str) -> None:
    """The Lo Shu grid on its own page - no name field in the way of the thing being searched for."""
    from app.numerology.copy import LO_SHU, PAGE

    path = i18n.url_for("lo-shu", lang)
    words = {**PAGE[lang], **LO_SHU[lang]}

    def _render(request: Request, result=None, entered=None):
        from app.web import seo as _seo
        from app.web import pages as web_pages

        entered = entered or {}
        context = page_context("lo-shu", lang)
        context.update(
            words=words, result=result,
            entered_day=entered.get("day", ""), entered_month=entered.get("month", ""),
            entered_year=entered.get("year", ""),
            month_names=web_pages.content(lang).UI["month_names"],
            years=list(range(dt.date.today().year, 1899, -1)),
            planes=core.PLANES,
            title=words["title"], meta_description=words["meta"], h1=words["h1"],
            numerology_path=i18n.url_for("numerology", lang),
            **_report_cta(lang),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (words["h1"], path)]))])
        return respond(request, "lo_shu.html", context)

    def lo_shu_page(request: Request):
        return _render(request)

    async def lo_shu_result(request: Request):
        fields = await _submitted(request)
        born = _parse_date(fields)
        if born is None:
            return _render(request, entered=fields)
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

    def _render(request: Request, result=None, entered=None):
        from app.web import seo as _seo
        from app.web import pages as web_pages

        entered = entered or {}
        context = page_context("number-check", lang)
        context.update(
            words=words, result=result,
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
        return _render(request, result=result, entered=fields)

    router.add_api_route(path, check_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"number-check-{lang}")
    router.add_api_route(path, check_result, methods=["POST"], response_class=HTMLResponse,
                         name=f"number-check-post-{lang}")


def _add(router, page_context, respond, _json_ld, lang: str) -> None:
    path = i18n.url_for("numerology", lang)
    words = PAGE[lang]

    def _render(request: Request, result=None, name="", entered=None):
        from app.web import seo as _seo
        from app.web import pages as web_pages

        entered = entered or {}
        context = page_context("numerology", lang)
        context.update(
            words=words, result=result, entered_name=name,
            entered_day=entered.get("day", ""), entered_month=entered.get("month", ""),
            entered_year=entered.get("year", ""),
            month_names=web_pages.content(lang).UI["month_names"],
            years=list(range(dt.date.today().year, 1899, -1)),
            title=words["title"], meta_description=words["meta"], h1=words["h1"],
            chaldean=core.CHALDEAN, lo_shu_rows=core.LO_SHU_ROWS,
            kundali_path=i18n.url_for("kundali", lang),
            mulank_links=[{"number": n, "path": i18n.url_for("mulank", lang, number=n)}
                          for n in range(1, 10)],
            **_ask_box(lang),
            **_report_cta(lang),
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
            return _render(request, name=name, entered=fields)
        return _render(request, result=core.profile(name, born), name=name, entered=fields)

    router.add_api_route(path, numerology_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"numerology-{lang}")
    router.add_api_route(path, numerology_result, methods=["POST"], response_class=HTMLResponse,
                         name=f"numerology-post-{lang}")
