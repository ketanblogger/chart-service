"""SEO plumbing: /sitemap.xml, /robots.txt and the JSON-LD blocks shared by the page templates.

ONE sitemap for all three language trees, built on the URL registry app/web/i18n.py:
one <url> per (page, language) = 246 URLs - home, 4 tools and the consultation x3, the rashifal daily hub + weekly hub
x3, 12 rashi hubs x3, 60 readings x3 (= the 180 permanent rashifal URLs), and the 6 English-only policy pages. Every
multi-language <url> carries the full hreflang set (en / hi / mr + x-default) as xhtml:link - the same set on each
language version, which is what makes it reciprocal; it is the set `i18n.alternates()` also gives the page <head>.
Old URLs (/janam-kundali, /rashifal/..., ?lang=) are 301s (i18n.legacy_redirect) and never listed.

Never indexable: /order/* (noindex header + meta, and disallowed), /api/*. tests/test_seo.py crawls every sitemap
URL in-process and fails on a non-200, a noindex, a wrong canonical / lang / hreflang, a robots.txt block, a duplicate
title or description, or a broken or redirecting internal link.
"""

import datetime as dt
import logging
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from app.web import site

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

DISALLOW = ("/order/", "/api/")
# Deliberately a second copy of i18n.TOOL_KEYS + EN_ONLY_TOOL_KEYS: this module imports i18n inside functions
# to avoid a cycle. tests/test_seo.py pins the two together, so they cannot drift silently.
_TOOL_KEYS = ("kundali", "matching", "mangal-dosha", "sade-sati", "sidereal")
_READING_FREQ = {"today": ("daily", "0.8"), "weekly": ("weekly", "0.7"), "monthly": ("monthly", "0.6"),
                 "6-months": ("monthly", "0.6"), "yearly": ("monthly", "0.6")}


def _content_date() -> str:
    """lastmod of the hand-written pages: when their copy / templates last changed on disk (i.e. the last deploy that
    touched them) - not "today", which would teach Google to ignore our lastmod values."""
    web = Path(__file__).resolve().parent
    files = [*web.glob("*.py"), *(web / "templates").glob("*.html"), *(web / "content").glob("*.py")]
    return dt.datetime.fromtimestamp(max(path.stat().st_mtime for path in files), dt.timezone.utc).date().isoformat()


def _rashifal_lastmods() -> dict:
    """{(rashi, period): iso datetime} for the 60 readings + {"today": ..., "weekly": ...} window starts for the hubs.
    A reading's lastmod is when its stored text was generated; a page that still shows engine facts only changed when
    its current window began. Read from calc-engine's store - never from the AI. If that layer is unavailable the
    sitemap still renders (content date), because a broken sitemap is worse than a vague lastmod."""
    try:
        from app.rashifal import store
        from app.rashifal.periods import PERIOD_SLUGS, RASHI_SLUGS, to_ist, window_for

        now = to_ist(None)
        utc = lambda moment: moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds")  # noqa: E731
        starts = {period: utc(window_for(period, now).start) for period in PERIOD_SLUGS}
        stored = store.list_pages()
        lastmods: dict = {"today": starts["today"], "weekly": starts["weekly"]}
        for rashi in RASHI_SLUGS:
            for period in PERIOD_SLUGS:
                row = stored.get((rashi, period))
                lastmods[(rashi, period)] = row["generated_at"] if row else starts[period]
        return lastmods
    except Exception:  # noqa: BLE001
        log.exception("rashifal lastmod lookup failed; the sitemap falls back to the content date")
        return {}


def sitemap_entries() -> list[dict]:
    """[{"loc", "lastmod", "changefreq", "priority", "alternates": {hreflang: absolute url}}], one per (page, language)."""
    from app.web import i18n

    content_date, rashifal = _content_date(), _rashifal_lastmods()
    entries = []
    for ref in i18n.all_pages():
        params = ref.kwargs
        if ref.key == "home":
            lastmod, changefreq, priority = rashifal.get("today", content_date), "daily", "1.0"  # shows today's rashifal strip
        elif ref.key in _TOOL_KEYS:
            lastmod, changefreq, priority = content_date, "monthly", "0.9"
        elif ref.key == "consultation":
            lastmod, changefreq, priority = content_date, "monthly", "0.8"
        elif ref.key == "rashifal-hub":
            lastmod, changefreq, priority = rashifal.get("today", content_date), "daily", "0.9"
        elif ref.key == "rashifal-weekly":
            lastmod, changefreq, priority = rashifal.get("weekly", content_date), "weekly", "0.8"
        elif ref.key == "rashifal-rashi":
            lastmod, changefreq, priority = rashifal.get("today", content_date), "daily", "0.7"
        elif ref.key == "rashifal-reading":
            changefreq, priority = _READING_FREQ.get(params["period"], ("monthly", "0.6"))
            lastmod = rashifal.get((params["rashi"], params["period"]), content_date)
        else:  # policy / trust pages
            lastmod, changefreq, priority = content_date, "yearly", "0.2"
        alternates = ref.alternates()  # {} for single-language pages
        for lang in ref.langs:
            entries.append({"loc": ref.url(lang), "lang": lang, "key": ref.key, "lastmod": lastmod, "changefreq": changefreq,
                            "priority": priority, "alternates": alternates})
    return entries


def sitemap_xml() -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for item in sitemap_entries():
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(item['loc'])}</loc>")
        lines.append(f"    <lastmod>{escape(item['lastmod'])}</lastmod>")
        lines.append(f"    <changefreq>{item['changefreq']}</changefreq>")
        lines.append(f"    <priority>{item['priority']}</priority>")
        for hreflang, href in (item.get("alternates") or {}).items():
            lines.append(f"    <xhtml:link rel=\"alternate\" hreflang={quoteattr(hreflang)} href={quoteattr(href)}/>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt() -> str:
    # Disallow lines first: Google uses the longest match, but first-match parsers (Python's robotparser among
    # them) would let "Allow: /" win if it came first.
    lines = ["User-agent: *", *[f"Disallow: {path}" for path in DISALLOW], "Allow: /", "",
             f"Sitemap: {site.base_url()}/sitemap.xml"]
    return "\n".join(lines) + "\n"


@router.get("/sitemap.xml")
def sitemap() -> Response:
    return Response(sitemap_xml(), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> PlainTextResponse:
    return PlainTextResponse(robots_txt(), headers={"Cache-Control": "public, max-age=3600"})


# ---- JSON-LD ---------------------------------------------------------------------------------------


# The image a search result may show beside the site. NOT the favicon: Google's guidance for
# Organization.logo asks for a raster of at least 112px, and favicon.svg is vector and drawn for 16.
# Not the transparent brand mark either - an image with alpha is composited onto whatever background the
# result uses, which is a gamble. This one is 512x512, opaque, gold on the brand indigo, so it reads at
# any size on anything. tests/test_seo.py opens the file this points at and checks all three properties.
ORGANIZATION_LOGO = "/static/icons/icon-512.png"


def organization() -> dict:
    base = site.base_url()
    data = {"@context": "https://schema.org", "@type": "Organization", "@id": base + "/#organization",
            "name": site.SITE_NAME, "url": base + "/", "logo": base + ORGANIZATION_LOGO}
    if site.has_support_email():
        data["contactPoint"] = {"@type": "ContactPoint", "contactType": "customer support", "email": site.SUPPORT_EMAIL,
                                "availableLanguage": ["en", "mr", "hi"], "areaServed": "IN"}
    return data


def website() -> dict:
    base = site.base_url()
    return {"@context": "https://schema.org", "@type": "WebSite", "@id": base + "/#website", "name": site.SITE_NAME,
            "url": base + "/", "description": site.SITE_TAGLINE, "inLanguage": ["en", "mr", "hi"],
            "publisher": {"@id": base + "/#organization"}}


def web_application(name: str, path: str, description: str, language: str = "en") -> dict:
    """A free, browser-based tool (the four calculators, the Marathi kundali page, the consultation)."""
    base = site.base_url()
    return {"@context": "https://schema.org", "@type": "WebApplication", "name": name, "url": base + path,
            "description": description, "applicationCategory": "LifestyleApplication", "operatingSystem": "Any",
            "browserRequirements": "Requires JavaScript", "inLanguage": language, "isAccessibleForFree": True,
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"},
            "provider": {"@id": base + "/#organization"}}


def breadcrumbs(items: list[tuple[str, str]]) -> dict:
    base = site.base_url()
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": n, "name": name, "item": base + path} for n, (name, path) in enumerate(items, 1)]}


def faq_page(faqs) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": answer}}
        for question, answer in faqs]}
