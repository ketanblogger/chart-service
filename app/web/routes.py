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
from app.web import accounts, i18n, pages, seo, site
from app.web.policies import POLICY_PAGES, PolicyPage

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR.parent / "static"

TEMPLATES = WEB_DIR / "templates"
templates = Jinja2Templates(directory=TEMPLATES)
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


def _style_choices(lang: str) -> str:
    import json

    from app.ai import chat_style

    return json.dumps(chat_style.choices(lang), ensure_ascii=False)


def _free_answers_left(email: str) -> dict | None:
    """{"free_left", "paid_left"} for a signed-in reader, or None if it cannot be read.

    Read here rather than in the browser so the first paint is right: the composer learns the quota from
    its first API call, which is after the page has already made its promise.
    """
    try:
        from app.ai import chat_store
        from app.web import accounts

        with_id = accounts.account_id(email)
        row = chat_store.quota_for_user(with_id)
        return row
    except Exception:  # noqa: BLE001 - a promise that cannot be checked falls back to the generic offer
        return None


def account_menu(request, lang: str, path: str) -> dict | None:
    """What the header shows about the account, on EVERY page.

    None when `CHAT_LOGIN` is off: with the sign-in turned off there is no account to reach, and a link to a
    page that would only turn the visitor away is worse than no link.

    `here` is the path the visitor is on, so signing in returns them to it rather than to somewhere they
    never asked for. `short` is the part of the address before the @ - enough to tell two accounts apart on
    a shared machine, without printing the whole address into the chrome of every page.
    """
    if not site.CHAT_LOGIN:
        return None
    email = accounts.session_email(request)
    return {
        "email": email,
        "short": email.split("@")[0][:18] if email else "",
        "login_path": "/login" if lang == "en" else f"/{lang}/login",
        "orders_path": "/orders" if lang == "en" else f"/{lang}/orders",
        "here": path,
        # Only for an allowlisted address, and only as a link: the page itself answers 404 to everybody
        # else, so this is a convenience rather than the protection.
        "admin_path": "/admin" if accounts.is_admin(email) else None,
    }


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

    from app.web import muhurta_routes      # imported here: that module imports page_context from this one

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
        # The five styles a chat may answer in, named for this page's language. JSON because the browser
        # reads it off a data attribute; one table, on the server, shared with the replies themselves.
        "style_choices": _style_choices(lang),
        # A FEATURE NOBODY CAN FIND IS A FEATURE NOBODY USES - the same gap the sign-in had until this week,
        # when it existed only inside the AI astrologer. The muhurta finder lives outside the URL registry
        # (app/web/muhurta_routes.py says why), so it cannot be a NAV_KEY; this is its entry point, and it
        # is None whenever `site.MUHURTA` is off, which is also what the template keys on.
        "muhurta_link": ({"path": muhurta_routes.path_for(lang),
                          "label": muhurta_routes.COPY[lang]["heading"]} if site.MUHURTA else None),
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
    # The account menu is built HERE rather than in ten routes, for the same reason the design swap is: a
    # header that has to be wired into every route is a header that will be missing from one of them. It
    # needs the request (for the session cookie) and the page's own path (so signing in comes back here),
    # and `respond` is the one place that has both.
    context.setdefault("auth", pages.auth_copy(context.get("lang", "en")))
    context.setdefault("account_menu", account_menu(request, context.get("lang", "en"),
                                                    request.url.path or "/"))
    template, context = _preview(request, template, context)
    response = templates.TemplateResponse(request, template, context)
    response.headers["Content-Language"] = context["html_lang"]
    response.headers.update(headers or {})
    return response


def _preview(request: Request, template: str, context: dict) -> tuple[str, dict]:
    """Choose between `<name>.html` and `<name>_v2.html`. `site.DESIGN_V2` decides; the query string overrides.

    HERE, in the one funnel every page already goes through, rather than in each route: a design that has to
    be wired into eight routes is a design that will be wired into seven of them. A page with no `_v2`
    template simply keeps its own, so the switch is safe whatever stage the rework is at.

      DESIGN_V2=on (the default)   every page that has a v2 template serves it
      DESIGN_V2=off               every page serves the previous template
      ?design=v2 / ?design=v1     overrides either way, for one request

    `?design=v1` is what makes the rollback checkable: the previous page can be opened on the live site at
    any time without changing a setting. Neither query string needs a canonical of its own - `canonical` is
    built from the PATH in `page_context`, so both spellings already point at the clean URL.

    The extra context is merged only for a page that actually got a v2 template, so an ordinary render pays
    nothing for the switch existing - `design_v2_context` computes the sky panel and reads the catalogue.
    """
    choice = request.query_params.get("design")
    if choice == "v1" or not (site.DESIGN_V2 or choice == "v2"):
        return template, context
    candidate = template.replace(".html", "_v2.html")
    if not (TEMPLATES / candidate).is_file():
        return template, context
    # `v2_is_default` drives the robots meta: while the design is a preview behind a query string it must not
    # be indexed, and once it IS the site it must not carry a noindex. One flag, read in five templates.
    return candidate, {**context, **design_v2_context(context), "v2_is_default": site.DESIGN_V2}


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


def _rashis_in_zodiac_order(lang: str) -> list[dict]:
    """The twelve as the zodiac runs them, for the prototype's grid and rail picker (see the note below)."""
    labels = pages.get("rashifal-hub", lang).extra
    out = []
    for key in i18n.RASHI_KEYS:
        names = i18n.rashi_names(key, lang)
        out.append({**names, "label": pages.fill(labels["rashi_label"], **names),
                    "sub": pages.fill(labels["rashi_sub"], **names),
                    "path": i18n.url_for("rashifal-reading", lang, rashi=key, period="today")})
    return out


def design_v2_context(context: dict) -> dict:
    """Everything a v2 template needs that the live one does not. Prototype-only; see design_v2.py.

    Built from the PAGE CONTEXT rather than from (lang, copy), because every page has the context and not
    every page has a `copy` of the shape the home page has. The sky panel is engine-only and cached
    (app/web/sky.py): no AI call is made rendering any of these pages, and a None from it drops the panel
    rather than the page.
    """
    from app.payments import catalogue

    from . import design_v2, sky

    lang = context.get("lang") or context.get("html_lang") or "en"
    book = catalogue.item("kundali-report")
    return {
        "v2": design_v2.labels(lang),
        # ZODIAC ORDER, Mesha to Meena, and only here. `rashis` stays in demand order for the live page,
        # where the sequence is crawl priority - the first links on the most linked-to page of the site.
        # A PICKER is a different object: it is scanned by position, a reader knows where their own sign
        # falls in the twelve, and every sign is linked either way, so the ordering that helps a crawler
        # costs a human the one thing the grid is for. Settled in design review, 2026-09-30.
        "rashis_zodiac": _rashis_in_zodiac_order(lang),
        "need_tools": design_v2.NEED_TOOLS,
        "sign_glyph": lambda key: design_v2.SIGN_GLYPHS.get(key, ""),
        "tool_glyph": design_v2.glyph,
        "sky": sky.snapshot(lang),
        # The form's submit label belongs to the kundali tool, because it is the kundali tool's form.
        "kundali_copy": pages.get("kundali", lang),
        # From the catalogue, never typed here - the same rule the pricing page follows.
        "book_price": book.price_inr,
    }


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
        # The `?design=v2` prototype is picked up by `respond` itself (see `_preview`), so this route - and
        # every other one - needs to know nothing about it.
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
        # The page has to KNOW whether a sign-in stands between the reader and the chat, because the form
        # must say so before it is filled rather than after it is submitted. Both flags are read per request,
        # so `CHAT_LOGIN=off` takes the notice away with the gate.
        from app.web import accounts

        email = accounts.session_email(request) if site.CHAT_LOGIN else None
        signed_in = bool(email) if site.CHAT_LOGIN else True
        # WHAT THIS READER ACTUALLY HAS, not what a first-time visitor is offered. The page promised "your
        # first 2 questions are free" to somebody who had spent both of theirs, next to a paywall card
        # saying they were used - which reads as a fresh allowance that then refuses to work. None for a
        # visitor who is not signed in: they genuinely do get the offer.
        chat_left = _free_answers_left(email) if email else None
        context.update(copy=copy, endpoint=pages.CONSULTATION_ENDPOINT, chat_left=chat_left,
                       options=pages.purchase_offers("consultation", copy),
                       chat_pack_messages=offer["pack_messages"],
                       chat_free_messages=offer["free_messages"], more_tools=_more_tools(context, "consultation"),
                       auth=pages.auth_copy(lang), chat_login_required=site.CHAT_LOGIN, signed_in=signed_in,
                       login_path="/login" if lang == "en" else f"/{lang}/login",
                       chat_path=i18n.url_for("consultation", lang),
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


def _price_rows() -> list[str]:
    """The pricing page's product list, built from the catalogue at render time: one bullet per product.

    Razorpay refused international payments on 2026-09-29 for having no "Pricing of services" page. The
    prices were on the product pages all along; what did not exist was one page a reviewer could open. This
    builds it from `catalogue.all_items()`, so a new product appears here the day it is priced and a price
    change reaches this page without anyone remembering to edit it.
    """
    from app.payments import catalogue, gst

    return [f"{entry.name} - Rs {entry.price_inr} (includes Rs {gst.money(entry.gst.gst_paise)} GST)"
            for entry in catalogue.all_items()]


def _add_policy_route(page: PolicyPage) -> None:
    def policy_page(request: Request):
        fields = {"site_name": site.SITE_NAME, "legal_entity": site.LEGAL_ENTITY, "legal_address": site.LEGAL_ADDRESS,
                  "support_email": site.SUPPORT_EMAIL, "support_phone": site.SUPPORT_PHONE,
                  "jurisdiction": site.JURISDICTION, "policies_updated": page.updated or site.POLICIES_UPDATED,
                  "source_url": site.SOURCE_URL, "gstin": site.GSTIN,
                  # computed at render time so "no phone" reads as a sentence rather than an empty bullet
                  "gstin_line": site.gstin_line(), "support_phone_line": site.support_phone_line(),
                  "contact_details": site.contact_details()}

        def fill(block):
            # READ FROM THE CATALOGUE, never written into the copy. app/payments/catalogue.py is the only
            # place a price exists, and tests/test_pages_i18n.py fails any page showing a rupee figure that
            # disagrees with it - so a pricing page with the numbers typed in would be wrong the first time a
            # price moved, which is exactly what it must never be. It is the one field that is a LIST of
            # products rather than a sentence, so it renders as a bullet list: seven products joined into one
            # paragraph is not something a reviewer, or a customer, reads.
            if block == "{price_table}":
                return _price_rows()
            if isinstance(block, str):
                return block.format(**fields)
            # a bullet that fills to nothing (an optional detail this business does not have) is dropped
            return [filled for item in block if (filled := item.format(**fields).strip())]

        context = page_context(page.slug, "en")
        # the description is filled like every other block: a policy page that named the brand in its
        # <meta> used to print the placeholder itself, because the template read it straight off the page
        context.update(page=page, meta_description=page.meta_description.format(**fields),
                       h1=page.h1.format(**fields), intro=page.intro.format(**fields),
                       sections=[{"heading": section.heading, "blocks": [fill(block) for block in section.blocks]}
                                 for section in page.sections],
                       json_ld=[_json_ld(seo.breadcrumbs([("Home", "/"), (page.nav_label, page.path)]))])
        return respond(request, "policy.html", context)

    router.add_api_route(i18n.url_for(page.slug, "en"), policy_page, methods=["GET"], response_class=HTMLResponse,
                         name=page.slug)


for _policy in POLICY_PAGES.values():
    _add_policy_route(_policy)
