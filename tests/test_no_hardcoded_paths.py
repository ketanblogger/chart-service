"""Nobody hardcodes an internal path again: every link in the web layer comes from the URL registry (app/web/i18n.py).

Templates use `href("page-key")` / values prepared by the routes; JavaScript gets its links from the server-rendered
page; copy uses {url_...} placeholders. The only literal paths allowed are /static/ assets and /api/ endpoints."""

import re
from pathlib import Path

from app.main import _ROOT_FILES  # /favicon.ico, /apple-touch-icon.png, /site.webmanifest
from app.web import i18n

WEB = Path(__file__).resolve().parents[1] / "app" / "web"
STATIC = WEB.parent / "static"

# Every first path segment that is (or used to be) a page: registry paths, legacy paths, /order.
_SEGMENTS = sorted({path.strip("/").split("/")[0] for path, *_ in i18n.all_paths() if path != "/"}
                   | {path.strip("/").split("/")[0] for path in i18n.LEGACY_ROUTE_PATTERNS} | {"order"})
_PAGE_PATH = re.compile(r"""["'(=\s]/(?:%s)(?=["'/?#\s)]|$)""" % "|".join(re.escape(s) for s in _SEGMENTS))


def _strip_comments(text: str) -> str:
    """Prose may mention URLs; code may not. Drops {# #} / <!-- --> / /* */ blocks and // line comments."""
    text = re.sub(r"\{#.*?#\}|<!--.*?-->|/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<=[;{}\s])//\s.*$", " ", text)


def _offenders(text: str) -> list[str]:
    return [m.group(0) for m in _PAGE_PATH.finditer(_strip_comments(text))]


def test_the_pattern_catches_what_it_should():
    for bad in ('href="/birth-chart"', "href='/hi/kundli'", 'fetch("/consultation")', 'href="/rashifal/tula/today"',
                '<a href="/mr/">', 'url = "/horoscope"', 'href="/janam-kundali#faq"', 'location = "/order/abc"'):
        assert _offenders(bad), bad
    for fine in ('src="/static/js/app.js"', 'fetch("/api/cities")', 'href="{{ href(\'kundali\') }}"', 'href="/"',
                 "api/consultation/start", "text/html", 'href="{{ item.path }}"'):
        assert not _offenders(fine), fine


def test_templates_have_no_hardcoded_internal_links():
    for template in sorted((WEB / "templates").glob("*.html")):
        text = template.read_text(encoding="utf-8")
        assert not _offenders(text), (template.name, _offenders(text))
        # A literal href may only be an asset: the /static/ mount, or one of the three files browsers fetch
        # from the root whatever the <head> says. Pages still come from the registry.
        for href in re.findall(r'href="(/[^"{]*)"', text):
            assert href.startswith("/static/") or href in _ROOT_FILES, (template.name, href)


def test_javascript_has_no_hardcoded_page_paths():
    for script in sorted((STATIC / "js").glob("*.js")):
        text = script.read_text(encoding="utf-8")
        assert not _offenders(text), (script.name, _offenders(text))
        for literal in re.findall(r"""["'](/[a-z][^"']*)["']""", text):
            assert literal.startswith(("/api/", "/static/")), (script.name, literal)


def test_python_web_layer_spells_paths_only_in_the_registry():
    allowed = {"i18n.py"}  # the registry itself
    for module in sorted([*WEB.glob("*.py"), *(WEB / "content").glob("*.py")]):
        if module.name in allowed:
            continue
        code = "\n".join(line for line in module.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("#"))
        code = re.sub(r'""".*?"""', "", code, flags=re.S)  # docstrings may describe URLs
        found = [hit for hit in _offenders(code) if "/order" not in hit]  # /order/{token} is platform's flow, not in the registry
        if module.name in ("policies.py", "seo.py", "site.py"):
            continue  # platform's modules: reported to the lead, not edited here
        assert not found, (module.name, found)
