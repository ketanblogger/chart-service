"""Server-rendered public pages in three language trees (English `/`, Hindi `/hi/`, Marathi `/mr/`).

One system: URLs come from app/web/i18n.py, words from app/web/pages.py (+ content/<lang>.py), and every page is
rendered through `page_context()`, which supplies the language, the self-referencing canonical, the reciprocal
hreflang set, the navigation, the footer and the language switcher. Templates never spell a path: they call
`href("kundali")` (the page in the CURRENT language).

The pages never call the engine or any AI themselves: the browser posts the form to the JSON API (app/api.py) and
static/js/render.js draws the result. The rashifal pages live in app/web/rashifal.py.
"""

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.payments import razorpay
from app.web import i18n, pages, seo, site
from app.web.policies import POLICY_PAGES, PolicyPage

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR.parent / "static"

templates = Jinja2Templates(directory=WEB_DIR / "templates")
router = APIRouter(include_in_schema=False)

NAV_KEYS = (*i18n.TOOL_KEYS, "rashifal-hub", "consultation")  # header + footer, in this order


def _static_version() -> str:
    """Short hash of the static files, appended to their URLs so browsers refetch after a deploy."""
    digest = hashlib.sha256()
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


STATIC_VERSION = _static_version()


def _json_ld(data: dict) -> Markup:
    """JSON for a <script type="application/ld+json"> block ("</" escaped so it cannot close the tag)."""
    return Markup(json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/"))


def page_context(page_key: str | None, lang: str, path: str | None = None, **params) -> dict:
    """Everything base.html needs. `page_key` None = a page outside the registry (order page, error pages)."""
    ui = pages.ui(lang)
    common = pages.common_values(lang)
    if path is None:
        path = i18n.url_for(page_key, lang, **params)
    registered = page_key in i18n.PAGES

    def href(key: str, **kwargs) -> str:
        """Path of a page in the language of the page being rendered."""
        return i18n.url_for(key, lang, **kwargs)

    nav = []
    for key in NAV_KEYS:
        copy = pages.raw(key, lang)
        nav.append({"key": key, "label": ui["nav_rashifal"] if key == "rashifal-hub" else copy.nav_label,
                    "path": href(key), "blurb": pages.fill(copy.card_blurb, **common),
                    "current": key == page_key or (key == "rashifal-hub" and str(page_key).startswith("rashifal"))})
    return {
        "site_name": site.SITE_NAME, "site_tagline": ui["tagline"], "disclaimer": ui["disclaimer"],
        "base_url": site.base_url(), "canonical": site.base_url() + path, "static_version": STATIC_VERSION,
        "payments_enabled": razorpay.configured(),  # pay.js takes over the buy buttons only when keys are set
        "page_key": page_key, "lang": lang, "html_lang": i18n.HTML_LANG[lang], "og_locale": i18n.OG_LOCALE[lang],
        "ui": ui, "href": href, "nav": nav, "home_path": href("home"),
        "weekly_label": pages.raw("rashifal-weekly", lang).nav_label,
        "policy_links": [{"label": policy.nav_label, "path": i18n.url_for(slug, "en")}
                         for slug, policy in POLICY_PAGES.items()],
        # AGPL §13 source offer in the footer. /about is English-only, like the other policy pages.
        "source_path": i18n.url_for("about", "en"),
        "switcher": i18n.switcher(page_key if registered else None, lang, **(params if registered else {})),
        "alternates": [{"hreflang": code, "href": url}
                       for code, url in (i18n.alternates(page_key, **params) if registered else {}).items()],
    }


def _context(path: str) -> dict:
    """Base context for a bare path (app/hardening.py renders the 404 / 500 pages with it): the language is taken from
    the tree the path is in, so /hi/nope gets a Hindi header and footer."""
    found = i18n.resolve(path)
    if found:
        return page_context(found[0], found[1], **found[2])
    return page_context(None, i18n.lang_of_path(path), path=path)


def respond(request: Request, template: str, context: dict, headers: dict | None = None):
    response = templates.TemplateResponse(request, template, context)
    response.headers["Content-Language"] = context["html_lang"]
    response.headers.update(headers or {})
    return response


def _page_json_ld(copy: pages.PageCopy, page_key: str, lang: str, ui: dict) -> list[Markup]:
    """WebApplication + BreadcrumbList + FAQPage for a tool page (the FAQ block mirrors the visible FAQ)."""
    path = i18n.url_for(page_key, lang)
    blocks = [_json_ld(seo.web_application(copy.h1, path, copy.meta_description, i18n.HTML_LANG[lang])),
              _json_ld(seo.breadcrumbs([(ui["home"], i18n.url_for("home", lang)), (copy.nav_label, path)]))]
    if copy.faqs:
        blocks.append(_json_ld({**seo.faq_page(copy.faqs), "inLanguage": i18n.HTML_LANG[lang]}))
    return blocks


def _more_tools(context: dict, exclude: str) -> list[dict]:
    return [item for item in context["nav"] if item["key"] != exclude]


# ---- home ------------------------------------------------------------------------------------------------


def _add_home_route(lang: str) -> None:
    def home(request: Request):
        context = page_context("home", lang)
        copy = pages.get("home", lang)
        labels = pages.get("rashifal-hub", lang).extra
        rashis = []
        for key in i18n.rashis_by_demand(lang):  # SEO map §4: highest-demand rashis first
            names = i18n.rashi_names(key, lang)
            rashis.append({**names, "label": pages.fill(labels["rashi_label"], **names),
                           "sub": pages.fill(labels["rashi_sub"], **names),
                           "path": i18n.url_for("rashifal-reading", lang, rashi=key, period="today")})
        blocks = [_json_ld({**seo.website(), "url": site.base_url() + i18n.url_for("home", lang),
                            "inLanguage": i18n.HTML_LANG[lang]}),
                  _json_ld(seo.organization())]
        if copy.faqs:  # the visible FAQ block, mirrored for search engines exactly as the tool pages do it
            blocks.append(_json_ld({**seo.faq_page(copy.faqs), "inLanguage": i18n.HTML_LANG[lang]}))
        context.update(copy=copy, rashis=rashis, json_ld=blocks)
        return respond(request, "home.html", context)

    router.add_api_route(i18n.url_for("home", lang), home, methods=["GET"], response_class=HTMLResponse,
                         name=f"home-{lang}")


# ---- the four calculators ------------------------------------------------------------------------------------


def _add_tool_route(page_key: str, lang: str) -> None:
    spec = pages.TOOLS[page_key]

    def tool_page(request: Request):
        context = page_context(page_key, lang)
        copy = pages.get(page_key, lang)
        context.update(copy=copy, spec=spec, options=pages.purchase_offers(page_key, copy),
                       more_tools=_more_tools(context, page_key),
                       json_ld=_page_json_ld(copy, page_key, lang, context["ui"]))
        return respond(request, "tool.html", context)

    router.add_api_route(i18n.url_for(page_key, lang), tool_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"{page_key}-{lang}")


# ---- AI consultation -------------------------------------------------------------------------------------------


def _add_consultation_route(lang: str) -> None:
    def consultation_page(request: Request):
        """AI consultation chat (Phase 5). The page talks to /api/consultation/* via static/js/chat.js; the chat
        session is started in the page's language (app.js sends `language`)."""
        context = page_context("consultation", lang)
        copy = pages.get("consultation", lang)
        offer = pages.chat_offer()
        context.update(copy=copy, endpoint=pages.CONSULTATION_ENDPOINT,
                       options=pages.purchase_offers("consultation", copy),
                       chat_pack_messages=offer["pack_messages"],
                       chat_free_messages=offer["free_messages"], more_tools=_more_tools(context, "consultation"),
                       json_ld=_page_json_ld(copy, "consultation", lang, context["ui"]))
        return respond(request, "consultation.html", context)

    router.add_api_route(i18n.url_for("consultation", lang), consultation_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"consultation-{lang}")


for _lang in i18n.LANGS:
    _add_home_route(_lang)
    for _key in i18n.TOOL_KEYS:
        _add_tool_route(_key, _lang)
    _add_consultation_route(_lang)

# Calculators that exist in some trees only. Driven by page_langs rather than LANGS, so adding a language to
# one of these in the registry is all it takes to serve it.
for _key in i18n.EN_ONLY_TOOL_KEYS:
    for _lang in i18n.page_langs(_key):
        _add_tool_route(_key, _lang)


def language_home_without_slash(request: Request):
    return RedirectResponse(request.url.path + "/", status_code=301)


for _prefix in i18n.LANG_PREFIX.values():  # a language home typed without its trailing slash
    if _prefix:
        router.add_api_route(_prefix, language_home_without_slash, methods=["GET", "HEAD"], name=f"slash:{_prefix}")


# ---- legacy URLs of the pre-SEO-map site: permanent, single-hop redirects ------------------------------------------


def legacy(request: Request):
    target = i18n.legacy_redirect(request.url.path, request.url.query)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    return RedirectResponse(target, status_code=301, headers={"Cache-Control": "public, max-age=86400"})


for _pattern in i18n.LEGACY_ROUTE_PATTERNS:
    router.add_api_route(_pattern, legacy, methods=["GET", "HEAD"], name=f"legacy:{_pattern}")


# ---- order page: platform's flow, rendered in the ORDER's language -------------------------------------------------


@router.get("/order/{token}", response_class=HTMLResponse, name="order")
def order_page(token: str, request: Request):
    """Permanent "your purchase" page (Phase 6). Only paid orders have one; the token is the credential.

    Every word of it comes from app/payments/order_page.py (platform), in the language stored on the order - the report
    language the buyer chose, or the language of the consultation. Its first-paint status texts are tested to equal what
    pay.js shows after its refresh, including the consultation bundle (questions + the included Kundali PDF). Header,
    footer, <html lang> and Content-Language follow the same language; the page is outside the registry (no hreflang,
    never indexed)."""
    from app.payments import order_page as order_text
    from app.payments import service, store

    order = store.by_token(token) if 20 <= len(token) <= 80 else None
    if order is None or order["status"] != "paid":
        raise HTTPException(status_code=404, detail="order not found")
    view = service.status(order, reveal_token=True)  # also restarts a due / interrupted report job
    page = order_text.context(order, view)
    context = page_context(None, page["lang"], path=f"/order/{token}")
    context.update(view=view, token=token, order=page, info=page["info"], paid_on=page["paid_on"],
                   language_name=page["language_name"], consultation_path=i18n.url_for("consultation", page["lang"]))
    return respond(request, "order.html", context, {"Cache-Control": "private, no-store",
                                                    "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})


# ---- policy / trust pages (English only; linked from all three footers) --------------------------------------------


def _add_policy_route(page: PolicyPage) -> None:
    def policy_page(request: Request):
        fields = {"site_name": site.SITE_NAME, "legal_entity": site.LEGAL_ENTITY, "legal_address": site.LEGAL_ADDRESS,
                  "support_email": site.SUPPORT_EMAIL, "support_phone": site.SUPPORT_PHONE,
                  "jurisdiction": site.JURISDICTION, "policies_updated": site.POLICIES_UPDATED,
                  "source_url": site.SOURCE_URL, "gstin": site.GSTIN,
                  # computed at render time so "no phone" reads as a sentence rather than an empty bullet
                  "gstin_line": site.gstin_line(), "support_phone_line": site.support_phone_line(),
                  "contact_details": site.contact_details()}

        def fill(block):
            if isinstance(block, str):
                return block.format(**fields)
            # a bullet that fills to nothing (an optional detail this business does not have) is dropped
            return [filled for item in block if (filled := item.format(**fields).strip())]

        context = page_context(page.slug, "en")
        context.update(page=page, h1=page.h1.format(**fields), intro=page.intro.format(**fields),
                       sections=[{"heading": section.heading, "blocks": [fill(block) for block in section.blocks]}
                                 for section in page.sections],
                       json_ld=[_json_ld(seo.breadcrumbs([("Home", "/"), (page.nav_label, page.path)]))])
        return respond(request, "policy.html", context)

    router.add_api_route(i18n.url_for(page.slug, "en"), policy_page, methods=["GET"], response_class=HTMLResponse,
                         name=page.slug)


for _policy in POLICY_PAGES.values():
    _add_policy_route(_policy)
