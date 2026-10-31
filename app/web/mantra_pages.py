"""The mantra pages: one per text per language, plus a hub and a PDF.

THE RELEASE GATE LIVES IN THE HANDLER, not in the route table. Every page's route is registered at
start-up and answers 404 until its release date, so a release needs no deploy, no restart and no
job - the date arrives and the page starts answering. Registering routes conditionally would mean
the server had to be restarted on exactly the right morning to honour a date set weeks earlier.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import pathlib

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.mantra import texts as mantra_texts, translit
from app.web import i18n, mantra_copy

LANGS = ("en", "hi")
EXPLAINERS = pathlib.Path(__file__).resolve().parents[1] / "mantra/explainers"

#: The order the hub groups texts in, which is roughly how people think of them.
KIND_ORDER = ("chalisa", "aarti", "stotra", "sahasranamam", "mantra")


@functools.lru_cache(maxsize=128)
def _explainer(slug: str, lang: str) -> dict:
    path = EXPLAINERS / f"{slug}.{lang}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _text_or_404(slug: str) -> mantra_texts.Text:
    text = mantra_texts.BY_SLUG.get(slug)
    if text is None or not mantra_texts.is_live(text):
        raise HTTPException(status_code=404)
    return text


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in LANGS:
        _add_hub(router, page_context, respond, _json_ld, lang)
        for text in mantra_texts.PHASE_1:
            _add_text(router, page_context, respond, _json_ld, lang, text)
            _add_pdf(router, lang, text)


def _add_hub(router, page_context, respond, _json_ld, lang: str) -> None:
    from app.web import seo as _seo

    path = i18n.url_for("mantra-hub", lang)

    def hub(request: Request):
        words = mantra_copy.WORDS[lang]
        groups = []
        for kind in KIND_ORDER:
            items = [
                {"name": text.names[lang],
                 "path": i18n.url_for("mantra", lang, slug=text.slug),
                 "verses": words["verses_label"].format(count=len(mantra_texts.verses(text.slug)))}
                for text in mantra_texts.live() if text.kind == kind
            ]
            if items:
                # NOT "items": in a Jinja template `group.items` resolves to the dict's own
                # .items() method before it looks for the key, so the loop silently iterates a
                # bound method and raises. The muhurat pages hit this same collision.
                groups.append({"label": words["kinds"][kind], "texts": items})
        context = page_context("mantra-hub", lang)
        context.update({
            "words": words, "groups": groups, "h1": words["hub_h1"],
            "title": words["hub_title"], "lede": words["hub_lede"],
            "meta_description": words["hub_meta"][:180],
            "json_ld": [_json_ld(_seo.breadcrumbs([
                (context["ui"]["home"], i18n.url_for("home", lang)), (words["hub_h1"], path)]))],
        })
        return respond(request, "mantra_hub.html", context)

    router.add_api_route(path, hub, methods=["GET"], response_class=HTMLResponse,
                         name=f"mantra-hub-{lang}", include_in_schema=False)


def _add_text(router, page_context, respond, _json_ld, lang: str, text) -> None:
    from app.web import seo as _seo

    path = i18n.url_for("mantra", lang, slug=text.slug)

    def page(request: Request):
        _text_or_404(text.slug)
        words = mantra_copy.WORDS[lang]
        name = text.names[lang]
        verses = mantra_texts.verses(text.slug)
        explainer = _explainer(text.slug, lang)
        title = mantra_copy.title(name, text.names["en"], lang)
        context = page_context("mantra", lang, slug=text.slug)
        # THE PRIMARY KEYWORD IS THE TEXT'S NAME and the lede carries it inside the first hundred
        # words, which is where the brief asks for it and where a reader looks for confirmation
        # that they have landed on the right page.
        lede = explainer["intro"]
        context.update({
            "words": words, "name": name, "h1": name, "title": title, "lede": lede,
            "verses": verses,
            "roman": [translit.romanise(verse["text"]) for verse in verses],
            "explainer": explainer,
            "author": text.author,
            "sources": [{"label": source.label, "url": source.url} for source in text.sources],
            "updated": _updated(text, lang),
            "byline": mantra_copy.BYLINE[lang],
            "pdf_path": f"{path}.pdf",
            # THE POLICY PAGES EXIST IN ENGLISH ONLY, so the Hindi tree links to the English
            # ones rather than to a URL that was never built. Asking i18n for the Hindi About
            # raises KeyError, which is the right failure - it says the page is missing instead
            # of inventing a path.
            "about_path": i18n.url_for("about", "en"),
            "disclaimer_path": i18n.url_for("disclaimer", "en"),
            "related": _related(text, lang),
            "meta_description": mantra_copy.META[lang].format(name=name)[:180],
            "json_ld": [
                _json_ld(_article(text, lang, name, title, path)),
                _json_ld(_seo.breadcrumbs([
                    (context["ui"]["home"], i18n.url_for("home", lang)),
                    (words["hub_h1"], i18n.url_for("mantra-hub", lang)),
                    (name, path)])),
                _json_ld(_seo.faq_page([(item["q"], item["a"]) for item in explainer["faq"]])),
            ],
        })
        return respond(request, "mantra.html", context)

    router.add_api_route(path, page, methods=["GET"], response_class=HTMLResponse,
                         name=f"mantra-{text.slug}-{lang}", include_in_schema=False)


def _add_pdf(router, lang: str, text) -> None:
    path = f"{i18n.url_for('mantra', lang, slug=text.slug)}.pdf"

    async def pdf_route(request: Request):
        # Playwright's sync API cannot be driven from the event loop, so the render goes to a
        # worker thread - an async route calling it directly raises.
        from starlette.concurrency import run_in_threadpool

        _text_or_404(text.slug)
        body = await run_in_threadpool(_render_pdf, lang, text)
        return Response(content=body, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{text.slug}-{lang}.pdf"'})

    router.add_api_route(path, pdf_route, methods=["GET"],
                         name=f"mantra-pdf-{text.slug}-{lang}", include_in_schema=False)


def _render_pdf(lang: str, text) -> bytes:
    from markupsafe import Markup

    from app.pdf import browser
    from app.pdf.render import PDF_DIR, env

    # Markup, NOT a plain string: autoescaping inside a <style> block turns the quoted font
    # families into &#34;Report Devanagari&#34;, which is not valid CSS, so the browser falls back
    # to DejaVu and every Devanagari character prints as a box. It looks like a font problem and is
    # an escaping problem.
    css = Markup((PDF_DIR.parent / "biodata" / "sheet.css").read_text(encoding="utf-8"))
    html = env(lang).get_template("mantra_print.html").render(
        css=css, name=text.names[lang], words=mantra_copy.WORDS[lang],
        verses=mantra_texts.verses(text.slug), author=text.author,
        sources=[{"label": s.label, "url": s.url} for s in text.sources],
        byline=mantra_copy.BYLINE[lang], site="rashikundli.com")
    return browser.html_to_pdf(html)


def _updated(text, lang: str) -> str:
    """The release date is the last-updated date, because that is when the page became a page."""
    day = text.release or dt.date.today()
    return day.strftime("%d %B %Y") if lang == "en" else _hindi_date(day)


_HINDI_MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त",
                 "सितंबर", "अक्तूबर", "नवंबर", "दिसंबर")


def _hindi_date(day: dt.date) -> str:
    return f"{day.day} {_HINDI_MONTHS[day.month - 1]} {day.year}"


def _related(text, lang: str) -> list[dict]:
    """Only released siblings: a link to a 404 is worse than no link."""
    out = []
    for slug in text.related:
        sibling = mantra_texts.BY_SLUG.get(slug)
        if sibling is None or not mantra_texts.is_live(sibling):
            continue
        out.append({"name": sibling.names[lang],
                    "path": i18n.url_for("mantra", lang, slug=slug)})
    return out


def _article(text, lang: str, name: str, title: str, path: str) -> dict:
    from app.web import site

    day = (text.release or dt.date.today()).isoformat()
    return {
        "@context": "https://schema.org", "@type": "Article",
        "headline": title[:110], "inLanguage": lang,
        "mainEntityOfPage": site.base_url() + path,
        "about": {"@type": "Thing", "name": name},
        "datePublished": day, "dateModified": day,
        "author": {"@type": "Organization", "name": "RashiKundli"},
        "publisher": {"@type": "Organization", "name": "RashiKundli"},
    }
