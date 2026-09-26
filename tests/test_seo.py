"""Phase 8: one sitemap for the three language trees (hreflang), robots, the indexability crawl, legacy 301s,
policy pages and production hardening. Built on the URL registry in app/web/i18n.py."""

import gzip
import html as html_module
import json
import re
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import hardening
from app.main import app
from app.web import STATIC_DIR, i18n, seo, site
from app.web.policies import POLICY_PAGES

client = TestClient(app)
BASE = "http://localhost:8000"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "xhtml": "http://www.w3.org/1999/xhtml"}


class Page(HTMLParser):
    """Just what an indexing crawler looks at."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.title, self.h1, self.meta, self.links, self.hrefs, self.json_ld, self.alternates = "", [], {}, {}, [], [], {}
        self.lang, self._capture, self._buffer = None, None, ""
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "meta" and (a.get("name") or a.get("property")):
            self.meta[a.get("name") or a.get("property")] = a.get("content", "")
        elif tag == "link" and a.get("rel") == "alternate" and a.get("hreflang"):
            self.alternates[a["hreflang"]] = a.get("href")
        elif tag == "link" and a.get("rel"):
            self.links[a["rel"]] = a.get("href")
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag in ("title", "h1") or (tag == "script" and a.get("type") == "application/ld+json"):
            self._capture, self._buffer = ("json_ld" if tag == "script" else tag), ""

    def handle_data(self, data):
        if self._capture:
            self._buffer += data

    def handle_endtag(self, tag):
        if self._capture == "title" and tag == "title":
            self.title = self._buffer.strip()
        elif self._capture == "h1" and tag == "h1":
            self.h1.append(" ".join(self._buffer.split()))
        elif self._capture == "json_ld" and tag == "script":
            self.json_ld.append(json.loads(self._buffer))
        else:
            return
        self._capture = None


def sitemap_urls() -> list[ET.Element]:
    response = client.get("/sitemap.xml")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/xml")
    return ET.fromstring(response.content).findall("sm:url", NS)


def local(url: str) -> str:
    assert url.startswith(BASE), url
    return url[len(BASE):] or "/"


# ---- sitemap + robots --------------------------------------------------------------------------------


def sitemap_map() -> dict[str, dict[str, str]]:
    """{loc: {hreflang: href}} from the served sitemap."""
    return {url.find("sm:loc", NS).text: {link.get("hreflang"): link.get("href") for link in url.findall("xhtml:link", NS)}
            for url in sitemap_urls()}


def test_one_sitemap_covers_all_three_language_trees():
    urls = sitemap_urls()
    locs = [local(url.find("sm:loc", NS).text) for url in urls]
    assert len(locs) == len(set(locs)) == 247 == sum(len(ref.langs) for ref in i18n.all_pages())
    assert set(locs) == {path for path, *_ in i18n.all_paths()}  # exactly the registry: nothing missing, nothing extra
    by_lang = {lang: [loc for loc in locs if i18n.lang_of_path(loc) == lang] for lang in i18n.LANGS}
    assert {lang: len(paths) for lang, paths in by_lang.items()} == {"en": 87, "hi": 80, "mr": 80}
    readings = [loc for loc in locs if (i18n.resolve(loc) or ("",))[0] == "rashifal-reading"]
    assert len(readings) == 180 and "/horoscope/libra/today" in readings and "/hi/rashifal/tula/aaj" in readings
    assert "/mr/rashi-bhavishya/meen/varshik" in readings
    for path in ("/", "/hi/", "/mr/", "/birth-chart", "/hi/kundli", "/mr/kundali", "/mr/patrika-matching", "/ai-astrologer",
                 "/horoscope", "/hi/rashifal", "/mr/rashi-bhavishya", "/horoscope/weekly", "/hi/rashifal/saptahik",
                 "/mr/rashi-bhavishya/saptahik", "/horoscope/leo", *[f"/{slug}" for slug in POLICY_PAGES]):
        assert path in locs, path
    # old URLs are redirects, never entries; no query strings; nothing private
    assert not [loc for loc in locs if "?" in loc or loc.startswith(("/order", "/api", "/rashifal", "/janam-kundali", "/marathi-kundali", "/consultation"))]
    for url in urls:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}(T[\d:+.-]+(Z|[+-]\d\d:\d\d)?)?", url.find("sm:lastmod", NS).text)
        assert url.find("sm:changefreq", NS).text in ("daily", "weekly", "monthly", "yearly")


def test_sitemap_hreflang_sets_are_complete_and_reciprocal():
    sitemap = sitemap_map()
    for ref in i18n.all_pages():
        expected = ref.alternates()
        for lang in ref.langs:
            assert sitemap[ref.url(lang)] == expected, ref.url(lang)  # the same set on every language version = reciprocal
        if len(ref.langs) > 1:
            assert set(expected) == {"en", "hi", "mr", "x-default"} and expected["x-default"] == expected["en"] == ref.url("en")
            assert all(expected[i18n.HTML_LANG[lang]] == ref.url(lang) for lang in ref.langs)
    assert sitemap[f"{BASE}/privacy"] == {}  # single-language pages carry no alternates
    assert sitemap[f"{BASE}/hi/rashifal/tula/aaj"] == {
        "en": f"{BASE}/horoscope/libra/today", "hi": f"{BASE}/hi/rashifal/tula/aaj", "mr": f"{BASE}/mr/rashi-bhavishya/tula/aaj",
        "x-default": f"{BASE}/horoscope/libra/today"}


def test_rashifal_lastmod_comes_from_the_store_and_survives_its_absence(monkeypatch):
    entries = {entry["loc"]: entry for entry in seo.sitemap_entries()}
    reading = entries[f"{BASE}/horoscope/libra/today"]
    assert "T" in reading["lastmod"] and reading["changefreq"] == "daily"            # a moment, from the rashifal window / store
    assert entries[f"{BASE}/mr/rashi-bhavishya/tula/aaj"]["lastmod"] == reading["lastmod"]  # one reading, three languages
    assert entries[f"{BASE}/horoscope/libra/yearly"]["changefreq"] == "monthly"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entries[f"{BASE}/birth-chart"]["lastmod"])      # hand-written page: content date
    monkeypatch.setattr(seo, "_rashifal_lastmods", lambda: {})  # rashifal layer unavailable: the sitemap must still render
    assert len(seo.sitemap_entries()) == 247 and client.get("/sitemap.xml").status_code == 200


def test_sitemap_and_robots_use_the_public_base_url(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://rashikundli.com/")
    text = client.get("/sitemap.xml").text
    assert "<loc>https://rashikundli.com/</loc>" in text and "<loc>https://rashikundli.com/hi/rashifal/mesh/saptahik</loc>" in text
    assert "localhost" not in text and 'hreflang="mr" href="https://rashikundli.com/mr/rashi-bhavishya/mesh/saptahik"' in text
    assert client.get("/robots.txt").text.rstrip().endswith("Sitemap: https://rashikundli.com/sitemap.xml")


def test_robots_txt_allows_the_site_and_blocks_orders_and_api():
    response = client.get("/robots.txt")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/plain")
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    for url in sitemap_urls():
        assert parser.can_fetch("Googlebot", url.find("sm:loc", NS).text)
    assert parser.can_fetch("*", f"{BASE}/static/css/site.css")
    for path in ("/order/abcdefghijklmnopqrstuvwxyz012345", "/api/chart", "/api/report/x/pdf"):
        assert not parser.can_fetch("Googlebot", BASE + path), path
    assert parser.site_maps() == [f"{BASE}/sitemap.xml"]


# ---- the "done when": every sitemap URL is live, indexable and well-formed -----------------------------------


def test_every_sitemap_url_is_indexable_in_its_language_and_every_internal_link_resolves():
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(client.get("/robots.txt").text.splitlines())
    direct = TestClient(app, follow_redirects=False)
    titles, descriptions, internal = {}, {}, {}
    for url, alternates in sitemap_map().items():
        path = local(url)
        response = direct.get(path)
        assert response.status_code == 200, path
        assert "noindex" not in response.headers.get("x-robots-tag", "").lower(), path
        assert parser.can_fetch("Googlebot", url), path
        page = Page(response.text)
        assert "noindex" not in page.meta.get("robots", "").lower(), path
        assert page.links.get("canonical") == url, (path, page.links.get("canonical"))  # self-referencing, absolute
        assert page.lang == i18n.HTML_LANG[i18n.lang_of_path(path)], (path, page.lang)   # /hi/ pages are Hindi, /mr/ Marathi
        assert page.alternates == alternates, path                                       # <head> hreflang == sitemap hreflang
        assert len(page.h1) == 1 and page.h1[0], path
        assert page.title and 50 <= len(page.meta.get("description", "")) <= 320, (path, len(page.meta.get("description", "")))
        assert page.meta["og:url"] == url and page.meta["og:title"] == page.title and page.meta["og:description"] == page.meta["description"]
        assert page.meta["og:site_name"] == site.SITE_NAME and page.meta["twitter:card"] == "summary" and page.meta["viewport"]
        assert page.json_ld, path
        # each language version is its own page, written to its own keyword - never the same title / description twice
        assert titles.setdefault(page.title, path) == path, f"duplicate title: {path} and {titles[page.title]}"
        assert descriptions.setdefault(page.meta["description"], path) == path, f"duplicate description: {path} and {descriptions[page.meta['description']]}"
        for href in page.hrefs:
            if href.startswith("/"):
                internal.setdefault(href.split("#", 1)[0], path)
    assert len(internal) > 200
    for href, found_on in sorted(internal.items()):
        response = direct.get(href)
        # 200 directly: a page must never link to an old URL that 301s, nor to anything missing
        assert response.status_code == 200, f"{href} (linked from {found_on}) -> {response.status_code}"
        assert not href.startswith("/order")


@pytest.mark.parametrize("old, query, new", [
    ("/janam-kundali", "", "/birth-chart"), ("/kundali-matching", "", "/horoscope-matching"), ("/consultation", "", "/ai-astrologer"),
    ("/marathi-kundali", "", "/mr/kundali"), ("/rashifal", "", "/horoscope"), ("/rashifal", "lang=hi", "/hi/rashifal"),
    ("/rashifal/tula", "lang=mr", "/mr/rashi-bhavishya/tula"), ("/rashifal/dhanu/today", "", "/horoscope/sagittarius/today"),
    ("/rashifal/mesha/3-months", "lang=hi", "/hi/rashifal/mesh/masik"), ("/rashifal/meena/yearly", "lang=mr", "/mr/rashi-bhavishya/meen/varshik"),
])
def test_old_urls_redirect_permanently_in_one_hop(old, query, new):
    assert i18n.legacy_redirect(old, query) == new
    response = TestClient(app, follow_redirects=False).get(old + (f"?{query}" if query else ""))
    assert response.status_code == 301, (old, response.status_code)
    assert response.headers["location"] in (new, BASE + new)
    assert TestClient(app, follow_redirects=False).get(new).status_code == 200  # one hop, straight to a live page


def test_structured_data_on_key_pages():
    def types(path):
        return {block["@type"] for block in Page(client.get(path).text).json_ld}

    assert {"WebSite", "Organization"} <= types("/")
    for lang in i18n.LANGS:
        for key in ("kundali", "matching", "mangal-dosha", "sade-sati", "consultation"):
            found = types(i18n.url_for(key, lang))
            assert {"BreadcrumbList", "FAQPage"} <= found, (key, lang, found)
        assert "BreadcrumbList" in types(i18n.url_for("rashifal-reading", lang, rashi="dhanu", period="today"))
    assert types("/privacy") == {"BreadcrumbList"}
    home = {block["@type"]: block for block in Page(client.get("/").text).json_ld}
    # the real support address is published as the Organization's contact point (it was withheld while it was
    # a placeholder); there is no phone, so no telephone property either
    assert home["Organization"]["name"] == site.SITE_NAME
    assert home["Organization"]["contactPoint"]["email"] == site.SUPPORT_EMAIL == "support@rashikundli.com"
    assert "telephone" not in home["Organization"]["contactPoint"]


def test_order_pages_and_errors_are_never_indexable():
    for path in ("/no-such-page", "/hi/no-such-page", "/mr/no-such-page"):
        missing = client.get(path)
        assert missing.status_code == 404 and "noindex" in missing.headers["x-robots-tag"] and 'content="noindex"' in missing.text
    assert client.get("/order/" + "A" * 32).status_code == 404


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval((STATIC_DIR / "js" / "pay.js").read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


def test_report_language_defaults_to_the_language_of_the_page(js):
    assert js("AstroPay.defaultReportLanguage('mr', 'en')") == "mr"   # on /mr/ pages the page language wins over an older choice
    assert js("AstroPay.defaultReportLanguage('hi', null)") == "hi"
    assert js("AstroPay.defaultReportLanguage('en', 'mr')") == "mr"   # English pages remember the visitor's last choice
    assert js("AstroPay.defaultReportLanguage('en', null)") == "en" and js("AstroPay.defaultReportLanguage('en', 'xx')") == "en"
    assert js("AstroPay.describe({status: 'paid', kind: 'report', fulfilment: 'ready'}, 'mr')")["title"] == "तुमचा अहवाल तयार आहे"
    assert js("AstroPay.describe({status: 'paid', kind: 'report', fulfilment: 'ready'}, 'hi')")["title"] == "आपकी रिपोर्ट तैयार है"
    assert js("AstroPay.describe({status: 'paid', kind: 'report', fulfilment: 'ready'})")["title"] == "Your report is ready"
    assert js("AstroPay.validateForm({email: 'x'}, 'mr')")[0]["message"].startswith("कृपया ई-मेल")


# ---- policy pages + brand ---------------------------------------------------------------------------------


def test_policy_pages_carry_the_real_business_details_and_nothing_personal():
    """Every policy page identifies the seller the way Razorpay and the E-Commerce Rules expect, from the one
    place those details live (app/web/site.py). The isolation rule still holds: this venture only."""
    assert list(POLICY_PAGES) == ["about", "contact", "privacy", "terms", "refund-policy", "disclaimer"]
    for path in ("/", "/hi/", "/mr/", "/birth-chart", "/hi/kundli", "/mr/ai-jyotish", "/mr/rashi-bhavishya/dhanu/aaj", "/terms"):
        html = client.get(path).text
        for slug in POLICY_PAGES:
            assert f'href="/{slug}"' in html, (path, slug)
    everything = ""
    for slug, config in POLICY_PAGES.items():
        html = client.get(f"/{slug}").text
        page = Page(html)
        assert page.title == f"{config.title} | {site.SITE_NAME}" and len(page.h1) == 1 and "{" not in re.sub(r"<script.*?</script>", "", html, flags=re.S)
        everything += html
    for needle in (site.LEGAL_ENTITY, site.LEGAL_ADDRESS, site.SUPPORT_EMAIL, site.GSTIN, site.JURISDICTION,
                   "Razorpay", "Anthropic", "Swiss Ephemeris", "faith-based", "5 to 7 working days",
                   "cannot be generated within 24 hours", "uid",
                   "Affero General Public License", site.SOURCE_URL):
        assert needle in everything, needle
    # nothing is outstanding: the source is published and every business detail is real
    assert site.placeholders_left() == []
    assert "[" not in site.LEGAL_ENTITY + site.LEGAL_ADDRESS + site.SUPPORT_EMAIL + site.GSTIN

    # ISOLATION: these pages describe this venture and nothing else the proprietor runs, and they never
    # print a personal mailbox. Asserted as an allowlist of domains rather than a blacklist of names, for
    # two reasons: a blacklist only catches the businesses someone remembered to list, and writing them
    # here would publish, in a public repository, the very names the rule exists to keep off the site.
    # The proprietor's own name IS printed on purpose - a sole proprietor is the seller, and the law
    # wants the seller identifiable.
    domains = set(re.findall(r"[a-z0-9][a-z0-9.-]*\.(?:com|org|in|net|io|co|ai|dev)\b", everything.lower()))
    # github: the AGPL source offer. googletagmanager: the analytics loader base.html puts in every page's head,
    # so it is in these pages' HTML too - it is a measurement host, not another venture of the seller's.
    assert domains <= {"rashikundli.com", "schema.org", "github.com", "www.googletagmanager.com"}, domains
    assert site.SUPPORT_EMAIL.endswith("@rashikundli.com")


def test_no_support_phone_is_a_decision_the_pages_state_in_words(monkeypatch):
    """"E-mail only" must read as a sentence, never as an empty bullet or a dangling comma - and it must not
    be reported forever as an outstanding placeholder, while a genuinely unfilled phone still is."""
    assert site.SUPPORT_PHONE == "" and not site.has_support_phone()
    assert "SUPPORT_PHONE" not in site.placeholders_left()      # decided: there is no phone
    contact = client.get("/contact").text
    assert "e-mail only" in contact and "Phone:" not in contact and "<li></li>" not in contact
    for page in ("/privacy", "/terms"):
        text = html_module.unescape(re.sub(r"<[^>]+>", " ", client.get(page).text))
        assert ", ," not in text and ": ," not in text and site.SUPPORT_EMAIL in text

    monkeypatch.setattr(site, "SUPPORT_PHONE", "[SUPPORT PHONE]")   # nobody has decided yet: still outstanding
    assert "SUPPORT_PHONE" in site.placeholders_left()
    assert "[SUPPORT PHONE]" in client.get("/contact").text

    monkeypatch.setattr(site, "SUPPORT_PHONE", "+91 98765 43210")   # a real number: shown with its hours
    contact = client.get("/contact").text
    assert "+91 98765 43210" in contact and "Monday to Friday" in contact and "e-mail only" not in contact
    assert "+91 98765 43210" in client.get("/terms").text           # and in the running text, without a gap
    assert "SUPPORT_PHONE" not in site.placeholders_left()


def test_the_gstin_is_printed_where_a_gst_registered_seller_names_itself():
    assert site.has_gstin() and site.gstin_line() == f"GSTIN: {site.GSTIN}"
    for page in ("/contact", "/terms", "/about"):
        assert site.GSTIN in client.get(page).text, page


def test_business_details_and_brand_are_configuration(monkeypatch):
    monkeypatch.setattr(site, "LEGAL_ENTITY", "Example Jyotish LLP")
    monkeypatch.setattr(site, "SUPPORT_EMAIL", "help@brand.example")
    html = client.get("/contact").text
    assert "Example Jyotish LLP" in html and "help@brand.example" in html and "[SUPPORT E-MAIL]" not in html
    assert "LEGAL_ENTITY" not in site.placeholders_left() and site.has_support_email()
    organization = next(block for block in Page(client.get("/").text).json_ld if block["@type"] == "Organization")
    assert organization["contactPoint"]["email"] == "help@brand.example"
    # the brand name is read from the environment in one place; no template or script hard-codes it
    for path in [*(STATIC_DIR.parent / "web" / "templates").glob("*.html"), *(STATIC_DIR / "js").glob("*.js")]:
        text = path.read_text(encoding="utf-8")
        assert "Kundali Online" not in text and "RashiKundli" not in text and "rashikundli" not in text.lower(), path.name
    source = (STATIC_DIR.parent / "web" / "site.py").read_text(encoding="utf-8")
    assert '_env("SITE_NAME", "RashiKundli")' in source and '_env("SUPPORT_EMAIL"' in source
    assert site.base_url() == "http://localhost:8000"  # the development default; production sets BASE_URL=https://rashikundli.com


# ---- hardening ------------------------------------------------------------------------------------------------


def test_security_headers_and_csp_on_every_kind_of_response():
    for path in ("/", "/hi/kundli", "/mr/rashi-bhavishya", "/api/cities", "/sitemap.xml", "/no-such-page", "/static/css/site.css"):
        headers = client.get(path).headers
        assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY", path
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin", path
        csp = dict(part.strip().split(" ", 1) for part in headers["content-security-policy"].split(";"))
        # No inline scripts, and exactly two third parties: Razorpay's checkout and Google's analytics loader.
        assert csp["script-src"] == "'self' https://checkout.razorpay.com https://www.googletagmanager.com", path
        # GA sends its hits by fetch/beacon and falls back to an image: without these two it would load and
        # then drop every pageview, which is the failure a script-src-only allowance hides.
        assert "https://*.google-analytics.com" in csp["connect-src"] and "https://*.google-analytics.com" in csp["img-src"]
        assert csp["frame-ancestors"] == "'none'" and csp["object-src"] == "'none'" and csp["base-uri"] == "'self'"
        assert "https://api.razorpay.com" in csp["frame-src"] and "https://api.razorpay.com" in csp["connect-src"]
        assert "strict-transport-security" not in headers  # BASE_URL is http://localhost here
    for template in (STATIC_DIR.parent / "web" / "templates").glob("*.html"):  # the CSP relies on this
        source = template.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*(src=|application/ld\+json))", source), template.name
        assert not re.search(r"\son[a-z]+=", source), template.name


def test_analytics_is_set_up_once_for_the_whole_site():
    """One GA4 property, from base.html alone: every page in all three trees carries the tag exactly once."""
    loader = 'src="https://www.googletagmanager.com/gtag/js?id=G-FYQ4092WMP"'
    bootstrap = 'data-ga-id="G-FYQ4092WMP"'
    for path in ("/", "/hi/", "/mr/", "/birth-chart", "/hi/kundli", "/mr/kundali", "/sidereal-birth-chart",
                 "/ai-astrologer", "/hi/ai-jyotish", "/horoscope/libra/today", "/mr/rashi-bhavishya/tula/aaj",
                 "/privacy", "/no-such-page"):
        html = client.get(path).text
        assert html.count(loader) == 1 and html.count(bootstrap) == 1, path
        assert html.count('src="/static/js/analytics.js') == 1, path
        assert html.count("G-FYQ4092WMP") == 2, path  # the loader's id= and the bootstrap's data attribute, nothing else
    # The measurement ID is configuration in ONE place. A second spelling anywhere is how two properties, or a
    # tag that keeps firing after the ID changes, get shipped without anything failing.
    templates = {t.name: t.read_text(encoding="utf-8") for t in (STATIC_DIR.parent / "web" / "templates").glob("*.html")}
    assert templates["base.html"].count("G-FYQ4092WMP") == 1
    for name, source in templates.items():
        assert name == "base.html" or ("gtag" not in source and "dataLayer" not in source), name
    script = (STATIC_DIR / "js" / "analytics.js").read_text(encoding="utf-8")
    assert "G-FYQ4092WMP" not in script and "dataLayer" in script  # the ID reaches it from the tag, not from here
    assert client.get("/static/js/analytics.js").status_code == 200


def test_hsts_only_on_https_and_csp_mode_switch(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://brand.example")
    assert client.get("/").headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    monkeypatch.setenv("CSP_MODE", "report-only")
    headers = client.get("/").headers
    assert "content-security-policy" not in headers and "checkout.razorpay.com" in headers["content-security-policy-report-only"]
    monkeypatch.setenv("CSP_MODE", "off")
    headers = client.get("/").headers
    assert "content-security-policy" not in headers and "content-security-policy-report-only" not in headers


def test_order_page_keeps_its_stricter_referrer_policy_and_static_files_cache_forever():
    versioned = re.search(r'href="(/static/css/site\.css\?v=\w+)"', client.get("/").text).group(1)
    assert client.get(versioned).headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/static/css/site.css").headers["cache-control"] == "public, max-age=3600"
    assert "immutable" not in client.get("/static/nope.css?v=1").headers.get("cache-control", "")
    assert "immutable" not in client.get("/birth-chart").headers.get("cache-control", "")


def test_responses_are_gzipped():
    response = client.get("/mr/kundali", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip" and "कुंडली" in response.text
    raw = TestClient(app).get("/sitemap.xml", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in raw.headers and len(gzip.compress(raw.content)) < len(raw.content) / 5


def test_error_pages_html_for_people_json_for_the_api():
    missing = client.get("/no-such-page")
    assert missing.status_code == 404 and missing.headers["content-type"].startswith("text/html")
    assert "Page not found" in missing.text and 'href="/birth-chart"' in missing.text and site.SITE_NAME in missing.text
    api = client.get("/api/no-such-route")
    assert api.status_code == 404 and api.json() == {"detail": "Not Found"}
    assert client.post("/no-such-page").status_code in (404, 405)

    def boom():
        raise RuntimeError("secret internal detail")

    app.add_api_route("/__boom", boom, methods=["GET"])
    app.add_api_route("/api/__boom", boom, methods=["GET"])
    try:
        quiet = TestClient(app, raise_server_exceptions=False)
        page = quiet.get("/__boom")
        assert page.status_code == 500 and "Something went wrong" in page.text and "secret internal detail" not in page.text
        api = quiet.get("/api/__boom")
        assert api.status_code == 500 and api.json()["detail"]["error"] == "server_error" and "secret" not in api.text
    finally:
        app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", "") not in ("/__boom", "/api/__boom")]


def test_production_config_check(monkeypatch):
    for name in ("SESSION_SECRET", "BASE_URL", "REPORTS_UNLOCKED", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "ANTHROPIC_API_KEY",
                 "ANTHROPIC_AUTH_TOKEN", "TRUST_PROXY", "APP_ENV", "CSP_MODE"):
        monkeypatch.delenv(name, raising=False)
    fatal, warnings = hardening.config_problems()
    # SESSION_SECRET and BASE_URL. SOURCE_URL is no longer fatal because it now names the published
    # repository; put a placeholder back and it becomes fatal again, which is the check that matters.
    assert len(fatal) == 2 and "SESSION_SECRET" in fatal[0] and "BASE_URL" in fatal[1]
    monkeypatch.setattr(site, "SOURCE_URL", "[PUBLIC SOURCE REPOSITORY URL]")
    fatal_again, _ = hardening.config_problems()
    assert any("SOURCE_URL" in problem for problem in fatal_again), fatal_again
    hardening.check_config()  # development: never blocks

    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="refusing to start"):
        hardening.check_config()
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("BASE_URL", "http://brand.example")
    assert any("https" in message for message in hardening.config_problems()[0])
    monkeypatch.setenv("BASE_URL", "https://brand.example")
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    assert any("REPORTS_UNLOCKED" in message for message in hardening.config_problems()[0])
    monkeypatch.setenv("REPORTS_UNLOCKED", "0")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "x")
    # a source offer that points at a placeholder is not an offer: production refuses to start on it
    assert any("SOURCE_URL" in message for message in hardening.config_problems()[0])
    monkeypatch.setattr(site, "SOURCE_URL", "https://github.com/example/astro")
    fatal, warnings = hardening.config_problems()
    assert fatal == [] and any("TEST key" in w for w in warnings) and any("WEBHOOK" in w for w in warnings)
    assert any("TRUST_PROXY" in w for w in warnings)
    assert not any("placeholders" in w for w in warnings), "the business details are all decided now"
    monkeypatch.setattr(site, "SUPPORT_PHONE", "[SUPPORT PHONE]")   # an undecided detail is still reported
    assert any("placeholders" in w and "SUPPORT_PHONE" in w for w in hardening.config_problems()[1])
    monkeypatch.setattr(site, "SUPPORT_PHONE", "")                  # "no phone" is a decision, not a gap
    assert not any("placeholders" in w for w in hardening.config_problems()[1])
    hardening.check_config()  # warnings only: starts


def test_readiness_endpoint(monkeypatch):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ok" and ready.headers["cache-control"] == "no-store"
    assert set(ready.json()["checks"]) == {"database", "ephemeris", "fonts", "storage"}
    assert "reference chart correct" in ready.json()["checks"]["ephemeris"]["detail"]

    from app.pdf import render
    monkeypatch.setattr(render, "FONTS_DIR", STATIC_DIR)  # no .ttf there
    broken = client.get("/health/ready")
    assert broken.status_code == 503 and broken.json()["checks"]["fonts"]["ok"] is False and broken.json()["checks"]["database"]["ok"]

    monkeypatch.setattr(hardening, "_chromium_cache", {"at": 0.0, "result": None})
    import app.pdf.browser as pdf_browser
    calls = []
    monkeypatch.setattr(pdf_browser, "chromium_available", lambda: (calls.append(1), (False, "no browser"))[1])
    first, second = client.get("/health/ready?chromium=1"), client.get("/health/ready?chromium=1")
    assert first.json()["checks"]["chromium"] == {"ok": False, "detail": "RuntimeError: no browser"} and second.status_code == 503
    assert len(calls) == 1  # cached: the endpoint cannot be used to launch browsers in a loop


def test_the_agpl_source_offer_is_on_the_site_and_in_the_repository(monkeypatch):
    """While the site links pyswisseph under the AGPL, network users must be offered the source (AGPL §13).
    The offer is configuration, like every other business detail: `SOURCE_URL` in the environment."""
    licence = (Path(__file__).resolve().parents[1] / "LICENSE").read_text(encoding="utf-8")
    assert "AGPL-3.0" in licence and "Swiss Ephemeris Professional License" in licence
    assert "first real paid order" in licence  # the position is explicitly temporary

    html = client.get("/about").text
    # The offer names the published repository. A placeholder here is not an offer, which is why
    # app/hardening.py refuses to start production while SOURCE_URL still holds one.
    assert "Affero General Public License" in html and site.SOURCE_URL in html
    assert "[PUBLIC SOURCE REPOSITORY URL]" not in html
    monkeypatch.setattr(site, "SOURCE_URL", "https://example.invalid/astro-source")
    html = client.get("/about").text
    assert "https://example.invalid/astro-source" in html


def test_the_smoke_check_scans_every_policy_page_for_placeholders():
    """The pre-launch check certifies that no [PLACEHOLDER] is left on the site. It used to read only
    /contact, which let the AGPL source offer on /about point at a placeholder and still pass - the one
    thing that has to be real before the site takes money. Keep the page list complete."""
    source = (Path(__file__).resolve().parents[1] / "scripts/smoke_check.py").read_text(encoding="utf-8")
    block = source[source.index('print("[business details]")'):source.index("if not args.no_pdf")]
    scanned = set(re.findall(r'"(/[a-z-]+)"', block))
    assert scanned == {f"/{slug}" for slug in POLICY_PAGES}, "every policy page must be scanned"

    # one rendered [PLACEHOLDER] per unset business detail, and the source offer is one of them
    rendered = {hit for slug in POLICY_PAGES
                for hit in re.findall(r"\[[A-Z][A-Z ,'/_-]+\]", client.get(f"/{slug}").text)}
    assert len(rendered) == len(site.placeholders_left()) == 0, rendered


# ---- the Organization logo is an image, not a favicon ----------------------------------------------


def test_the_organization_logo_is_a_raster_a_search_result_can_actually_use():
    """`Organization.logo` is the image Google may place beside the site in a result, and the guidance
    for it asks for a raster of at least 112px. It pointed at `/static/favicon.svg` - vector, authored
    for 16px - which is the wrong asset on both counts even though it is the right favicon.

    The test follows the URL to the file on disk rather than asserting the string, so it also catches the
    other way this goes wrong: a transparent PNG. An image with alpha gets composited onto whatever
    background the result uses, which is a gamble; `app/static/brand/main-logo.png` is exactly that and
    is the tempting wrong choice here.
    """
    Image = pytest.importorskip("PIL.Image", reason="Pillow is needed to inspect the logo")
    from app.web import STATIC_DIR, seo, site

    logo = seo.organization()["logo"]
    assert logo.startswith(site.base_url() + "/static/"), logo
    path = STATIC_DIR / logo.split("/static/", 1)[1]
    assert path.is_file(), f"Organization.logo points at {path}, which does not exist"
    assert path.suffix.lower() in (".png", ".jpg", ".jpeg"), (
        f"{path.name} is not a raster; Organization.logo has never reliably supported SVG")

    image = Image.open(path)
    assert min(image.size) >= 112, f"{path.name} is {image.size}; the guidance asks for at least 112px"
    alpha = image.convert("RGBA").getchannel("A").getextrema()
    assert alpha == (255, 255), (
        f"{path.name} has transparency {alpha}; a search result composites it onto an unknown background")
