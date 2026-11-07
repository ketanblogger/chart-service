"""The biodata maker's routes: the form, the preview, and the two files.

NOTHING IS STORED BETWEEN THE FORM AND THE DOWNLOAD. The preview carries the same fields back as
hidden inputs, so pressing "download PDF" is one POST that rebuilds the sheet from what the person
typed. The obvious alternative - keep the answers under a key for a few minutes - would mean this
page held somebody's family details on the server, which is the one thing its privacy line promises
it does not do.

THE FORM POSTS URL-ENCODED, PHOTO INCLUDED. There is no multipart parser in this project and this
page is not the place to add one: the photo arrives as a data URI in an ordinary field, bounded by
the same limit the rest of the body has, and is decoded and checked by signature before anything is
done with it. It still never reaches the disk.
"""
from __future__ import annotations

import base64
import datetime as dt
from urllib.parse import parse_qsl

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.engine import find_city
from app.web import i18n
from app.web import seo as _seo

from . import copy as biodata_copy
from . import core, designs, docx, model, qr, sheet

# A whole biodata plus a photo. The photo dominates, and the page shrinks it before sending.
MAX_BODY = 3 * 1024 * 1024
MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"),
    "hi": ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर",
           "अक्टूबर", "नवंबर", "दिसंबर"),
    "mr": ("जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर",
           "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"),
}
FIRST_YEAR = 1940
PREMIUM_PRODUCT = "biodata-premium"


async def submitted(request: Request) -> dict:
    """The form's fields, without python-multipart - the same parser app/blog/admin.py uses."""
    media = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if media != "application/x-www-form-urlencoded":
        return {}
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            return {}
    return dict(parse_qsl(body.decode("utf-8", "replace")))


def photo_bytes(value: str) -> bytes | None:
    """The data URI the page sends back, decoded. `sheet.photo_data_uri` then checks the signature,
    so a field claiming to be a PNG and holding something else is dropped there, not trusted here."""
    text = (value or "").strip()
    if not text.startswith("data:image/") or ";base64," not in text:
        return None
    try:
        return base64.b64decode(text.split(";base64,", 1)[1], validate=True)
    except (ValueError, TypeError):
        return None


def birth_from(fields: dict) -> tuple[dt.date | None, dt.time | None, dict | None]:
    """Date, time and place as the form gives them. Every one of the three is optional."""
    try:
        day, month, year = (int(fields.get(key) or 0)
                            for key in ("birth_day", "birth_month", "birth_year"))
        born = dt.date(year, month, day)
    except (TypeError, ValueError):
        born = None
    at = model.parse_time(fields.get("birth_time_text", ""))
    city = (fields.get("birth_city") or "").strip()
    place = find_city(city) if city else None
    return born, at, place


def _kundli_for(fields: dict, language: str) -> dict | None:
    born, at, place = birth_from(fields)
    if born is None:
        return None
    if at is not None and place is not None:
        return core.from_birth(born, birth_time=at, lat=place["lat"], lon=place["lon"],
                               language=language)
    # A time with no place settles nothing extra: the lagna needs both. Fall back to the honest
    # date-only answer rather than pretending the hour helped.
    return core.from_birth(born, language=language)


def _muhurat_label(lang: str) -> str:
    """The wedding-dates link, in this tree's words - taken from the muhurat page's own title so the
    two can never say different things about the same page."""
    from app.web.muhurat_year import TITLES

    return TITLES["vivah"][lang][0].format(year=2027)


def _paid(request: Request) -> bool:
    """Whether this visitor has unlocked the premium designs."""
    from app.ai import entitlement

    try:
        return bool(entitlement.owns_product(request, PREMIUM_PRODUCT))
    except Exception:          # the unlock is a convenience; a lookup failure must not break the page
        return False


def _form_sections(fields: dict, language: str) -> list[dict]:
    out = []
    for section, declared in model.SECTIONS.items():
        out.append({
            "title": model.SECTION_TITLES[section][language],
            "fields": [{"key": key, "kind": kind, "label": model.FIELD_LABELS[key][language],
                        "value": fields.get(key, "")} for key, kind in declared],
        })
    # Devak and gotra print in the kundli block, so they are asked for with the birth details.
    out[-1]["fields"] += [{"key": key, "kind": kind, "label": model.FIELD_LABELS[key][language],
                           "value": fields.get(key, "")} for key, kind in model.LINEAGE]
    return out


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.LANGS:
        _add_maker(router, page_context, respond, _json_ld, lang)
        _add_word(router, page_context, respond, _json_ld, lang)


def _build_everything(fields_raw: dict, lang: str, *, paid: bool, request: Request):
    """The sheet's inputs, shared by the preview and both downloads so they cannot drift apart."""
    fields = model.fields_from(fields_raw)
    kundli = _kundli_for(fields_raw, lang)
    design_key = fields_raw.get("design") or designs.DEFAULT
    photo = photo_bytes(fields_raw.get("photo", "")) if paid else None
    frame = fields_raw.get("frame") or "square"

    qr_block, token = None, ""
    born, at, place = birth_from(fields_raw)
    if fields_raw.get("qr") and born is not None:
        token = qr.issue(birth_date=born, birth_time=at,
                         lat=place["lat"] if place else None,
                         lon=place["lon"] if place else None,
                         place=place["name"] if place else (fields_raw.get("birth_city") or ""),
                         person=fields.get("full_name", ""))
        url = _absolute(request, i18n.url_for("matching", lang) + f"?biodata={token}")
        qr_block = {"image": qr.image_data_uri(url), "caption": qr.CAPTION[lang]}
    return fields, kundli, design_key, photo, frame, qr_block, token


def _absolute(request: Request, path: str) -> str:
    """The QR has to carry a whole URL - it is scanned by a camera that has no idea what site it
    came from, so a relative path is simply not a link."""
    from app.web import site

    return site.base_url().rstrip("/") + path


def _add_maker(router, page_context, respond, _json_ld, lang: str) -> None:
    path = i18n.url_for("biodata", lang)
    words = biodata_copy.PAGE[lang]

    def view(request: Request, fields_raw: dict, sheet_html=None, submitted_fields=None,
             qr_link: str = ""):
        context = page_context("biodata", lang)
        paid = _paid(request)
        context.update({
            "words": words,
            # The title, the H1 and the meta description. These pages keep their copy with the rest
            # of the feature rather than in app/web/content (where PAGES must equal COPY_KEYS), so
            # they set them here the way the numerology pages set theirs. A page that does not set
            # them renders a hero with NO HEADING IN IT - which is exactly what the first screenshot
            # of this page showed, and what no test noticed.
            "title": words["title"],
            "meta_description": words["meta"],
            "h1": words["h1"],
            "labels": {key: names[lang] for key, names in model.FIELD_LABELS.items()},
            "form_sections": _form_sections(model.fields_from(fields_raw), lang),
            "entered": {key: fields_raw.get(key, "") for key in
                        ("birth_day", "birth_month", "birth_year", "birth_time_text",
                         "birth_city", "qr")},
            "months": list(enumerate(MONTHS[lang], start=1)),
            "years": list(range(dt.date.today().year, FIRST_YEAR - 1, -1)),
            "designs": designs.choices(language=lang, paid=paid),
            "chosen_design": fields_raw.get("design") or designs.DEFAULT,
            "paid": paid,
            "premium_amount": 9900,
            "qr_offered": True,
            "qr_link": qr_link,
            "qr_off": i18n.url_for("biodata", lang) + f"?qr_off={qr_link}" if qr_link else "",
            "sheet_html": sheet_html,
            "submitted": submitted_fields or {},
            "word_path": i18n.url_for("biodata-word", lang),
            "word_words": biodata_copy.WORD_PAGE[lang],
            "muhurat_path": i18n.url_for("muhurat-year", lang, purpose="vivah", year=2027),
            "muhurat_label": _muhurat_label(lang),
            "match_path": i18n.url_for("matching", lang),
            "kundli_path": i18n.url_for("kundali", lang),
            "json_ld": [_json_ld(_seo.breadcrumbs([
                (context["ui"]["home"], i18n.url_for("home", lang)),
                (words["h1"], path)]))],
        })
        return respond(request, "biodata.html", context)

    def maker_page(request: Request):
        off = request.query_params.get("qr_off")
        if off:
            qr.revoke(off)
            return RedirectResponse(path, status_code=303)
        return view(request, {})

    async def maker_post(request: Request):
        fields_raw = await submitted(request)
        want = fields_raw.get("want", "preview")
        paid = _paid(request)
        if want == "edit":
            return view(request, fields_raw)

        fields, kundli, design_key, photo, frame, qr_block, token = _build_everything(
            fields_raw, lang, paid=paid, request=request)

        if want == "docx":
            blob = docx.build(fields, language=lang, design_key=design_key, paid=paid,
                              kundli=kundli)
            return Response(blob, media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                headers={"Content-Disposition": 'attachment; filename="marriage-biodata.docx"'})

        html = sheet.build(fields, language=lang, design_key=design_key, paid=paid, photo=photo,
                           frame=frame, kundli=kundli, qr=qr_block)
        if want == "pdf":
            # IN A WORKER THREAD. This route is `async` because it has to read the form off the
            # request stream, and app/pdf/browser.py drives Playwright's SYNC api - calling it on
            # the event loop raises "you are using Playwright Sync API inside the asyncio loop" and
            # the download 500s, which is how this was found. A sync FastAPI route would already be
            # in the threadpool; an async one has to put it there itself.
            from starlette.concurrency import run_in_threadpool

            from app.pdf import browser

            pdf = await run_in_threadpool(browser.html_to_pdf, html)
            return Response(pdf, media_type="application/pdf",
                            headers={"Content-Disposition":
                                     'attachment; filename="marriage-biodata.pdf"'})

        keep = {key: value for key, value in fields_raw.items() if key != "want"}
        return view(request, fields_raw, sheet_html=html, submitted_fields=keep, qr_link=token)

    router.add_api_route(path, maker_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"biodata-{lang}", include_in_schema=False)
    router.add_api_route(path, maker_post, methods=["POST"], response_class=HTMLResponse,
                         name=f"biodata-post-{lang}", include_in_schema=False)


def _add_word(router, page_context, respond, _json_ld, lang: str) -> None:
    path = i18n.url_for("biodata-word", lang)
    words = biodata_copy.WORD_PAGE[lang]

    def word_page(request: Request):
        if request.query_params.get("download") == "1":
            blank = docx.build({}, language=lang, design_key="classic", kundli=None)
            return Response(blank, media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                headers={"Content-Disposition":
                         'attachment; filename="marriage-biodata-format.docx"'})
        context = page_context("biodata-word", lang)
        context.update({
            "words": words,
            "title": words["title"],
            "meta_description": words["meta"],
            "h1": words["h1"],
            "sections": [{"title": model.SECTION_TITLES[key][lang],
                          "fields": [model.FIELD_LABELS[field][lang] for field, _ in declared]}
                         for key, declared in model.SECTIONS.items()],
            "maker_words": biodata_copy.PAGE[lang],
            "maker_path": i18n.url_for("biodata", lang),
            "download_path": path + "?download=1",
            "json_ld": [_json_ld(_seo.breadcrumbs([
                (context["ui"]["home"], i18n.url_for("home", lang)),
                (words["h1"], path)]))],
        })
        return respond(request, "biodata_word.html", context)

    router.add_api_route(path, word_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"biodata-word-{lang}", include_in_schema=False)
