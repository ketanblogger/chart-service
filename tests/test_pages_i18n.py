"""Every public page x language (SEO map §2): status, language signals, unique title / description / H1 site-wide,
self-referencing canonical, reciprocal hreflang, switcher targets, legacy 301s, and the page-config system itself
(three content modules in step, no hard-coded price, no unfilled placeholder)."""

import json
import re
from dataclasses import fields, is_dataclass

import pytest
from fastapi.testclient import TestClient

from app.main import _ROOT_FILES, app
from app.payments import catalogue
from app.web import i18n, pages
from tests.test_web import _Page

client = TestClient(app)
BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def crawl() -> dict[str, tuple]:
    """{path: (page_key, lang, params, response, parsed)} for all 246 registry URLs."""
    result = {}
    for path, key, lang, params in i18n.all_paths():
        response = client.get(path)
        assert response.status_code == 200, path
        result[path] = (key, lang, params, response, _Page(response.text))
    return result


def test_every_page_in_every_language_is_served_with_its_language_signals(crawl):
    assert len(crawl) == 247
    for path, (key, lang, _, response, page) in crawl.items():
        assert response.headers["content-language"] == lang, path
        assert f'<html lang="{lang}">' in response.text, path
        assert page.meta["og:locale"] == i18n.OG_LOCALE[lang], path
        assert page.links["canonical"] == BASE + path == page.meta["og:url"], path  # self-referencing
        assert len(page.h1) == 1 and page.h1[0], path
        assert 50 <= len(page.meta["description"]) <= 230, (path, len(page.meta["description"]))
        assert not re.search(r"\{[a-z_]+\}", response.text.split("<main", 1)[1].split("<script", 1)[0]), path
        for block in page.json_ld:
            if "inLanguage" in block:
                assert block["inLanguage"] == lang, (path, block["@type"])
        crumbs = [block for block in page.json_ld if block["@type"] == "BreadcrumbList"]
        if key not in ("home",):
            assert crumbs and crumbs[0]["itemListElement"][0]["item"] == BASE + i18n.url_for("home", lang if key not in i18n.POLICY_KEYS else "en"), path
            assert crumbs[0]["itemListElement"][-1]["item"] == BASE + path, path


def test_titles_descriptions_and_h1_are_unique_site_wide(crawl):
    for what, value in (("title", lambda p: p.title), ("description", lambda p: p.meta["description"]), ("h1", lambda p: p.h1[0])):
        seen: dict[str, str] = {}
        for path, (*_, page) in crawl.items():
            text = value(page)
            assert text not in seen, f"{what} of {path} duplicates {seen[text]}: {text}"
            seen[text] = path


def test_devanagari_pages_are_written_in_their_language(crawl):
    hindi_only, marathi_only = ("है", "और"), ("आहे", "आणि")
    for path, (key, lang, _, response, page) in crawl.items():
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", response.text, flags=re.S)
        body = re.sub(r"<header.*?</header>", " ", body, flags=re.S)  # the switcher names every language
        text = re.sub(r"<[^>]+>", " ", body)
        if lang == "en":
            assert len(re.findall(r"[ऀ-ॿ]", text)) < 0.1 * len(text), path
            continue
        assert len(re.findall(r"[ऀ-ॿ]", text)) > 0.3 * len(re.sub(r"\s", "", text)), path
        words = set(re.findall(r"[ऀ-ॿ]+", text))
        mine, other = (hindi_only, marathi_only) if lang == "hi" else (marathi_only, hindi_only)
        assert words & set(mine), path
        assert not words & set(other), (path, words & set(other))
        # title tags carry the transliterated query AND Devanagari (SEO map §1)
        assert re.search(r"[A-Za-z]{4,}", page.title) and re.search(r"[ऀ-ॿ]{3,}", page.title), (path, page.title)


def test_hreflang_is_complete_self_including_and_reciprocal(crawl):
    hreflang = {}
    for path, (key, lang, params, response, _) in crawl.items():
        links = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">', response.text))
        hreflang[BASE + path] = links
        # The predicate is how many languages the page HAS, not whether it is a policy page. POLICY_KEYS was
        # standing in for "single-language", and the two stopped being the same thing the moment a calculator
        # existed in one tree only.
        langs = i18n.page_langs(key)
        if len(langs) == 1:
            assert links == {}, path  # nothing to point at, so it must not claim alternates
            continue
        assert set(links) == set(langs) | {"x-default"}, path
        assert links[lang] == BASE + path, path  # names itself
        assert links["x-default"] == links["en"]
        assert links == i18n.alternates(key, **params)
    for url, links in hreflang.items():  # reciprocity: everything I point to points back to me with the same set
        for target in links.values():
            assert hreflang[target] == links, (url, target)


def test_language_switcher_leads_to_the_same_page_in_the_other_languages(crawl):
    for path, (key, lang, params, response, _) in crawl.items():
        header = response.text.split("<header", 1)[1].split("</header>", 1)[0]
        found = re.findall(r'<a href="([^"]+)" hreflang="(\w+)" lang="\w+" data-lang="(\w+)"( aria-current="true")?>([^<]+)</a>', header)
        assert [(item[2], item[4]) for item in found] == [("en", "English"), ("hi", "हिन्दी"), ("mr", "मराठी")], path
        for href, _, code, current, _ in found:
            assert bool(current) == (code == lang), path
            expected = i18n.url_for(key, code, **params) if code in i18n.page_langs(key) else i18n.url_for("home", code)
            assert href == expected, (path, code)


def test_navigation_and_footer_stay_inside_the_language_tree(crawl):
    for path, (key, lang, _, response, _) in crawl.items():
        if key in i18n.POLICY_KEYS:
            continue
        html = response.text
        chrome = html.split("<header", 1)[1].split("</header>", 1)[0] + html.split("<footer", 1)[1]
        chrome = re.sub(r'<nav class="lang-switch".*?</nav>', "", chrome, flags=re.S)
        # A link may leave the language tree only if it says so: the English-only pages (the policies and
        # the AGPL source offer) carry hreflang="en" on hi/mr pages. Anything else must stay in the tree.
        anchors = re.findall(r'<a\s([^>]*?)href="(/[^"]*)"([^>]*)>', chrome)
        links = [href for before, href, after in anchors if 'hreflang="en"' not in before + after]
        assert len(links) >= 12, path
        for href in links:
            found = i18n.resolve(href)
            assert found and found[1] == lang, (path, href)
        for before, href, after in anchors:  # and a marked link must really be an English-only page
            if 'hreflang="en"' in before + after:
                found = i18n.resolve(href)
                assert found and found[1] == "en", (path, href)
                assert lang != "en", (path, href)  # pointless marker on an English page
        for policy in i18n.POLICY_KEYS:  # policy pages are English-only and linked from all three footers
            assert f'href="{i18n.url_for(policy, "en")}"' in html, (path, policy)


def test_every_internal_link_on_every_page_resolves(crawl):
    checked = set()
    for path, (*_, response, _) in crawl.items():
        for href in set(re.findall(r'href="(/[^"#?]*)', response.text)):
            if href.startswith("/static/") or href in _ROOT_FILES or href in checked:
                continue
            checked.add(href)
            assert i18n.resolve(href) is not None, f"{path} links to {href}, which is not a registered page"
    assert len(checked) >= 246


@pytest.mark.parametrize("old, new", [
    ("/janam-kundali", "/birth-chart"), ("/kundali-matching", "/horoscope-matching"), ("/consultation", "/ai-astrologer"),
    ("/marathi-kundali", "/mr/kundali"), ("/rashifal", "/horoscope"), ("/rashifal?lang=hi", "/hi/rashifal"),
    ("/rashifal/mesha", "/horoscope/aries"), ("/rashifal/tula?lang=mr", "/mr/rashi-bhavishya/tula"),
    ("/rashifal/dhanu/today", "/horoscope/sagittarius/today"), ("/rashifal/mesha/3-months", "/horoscope/aries/monthly"),
    ("/rashifal/simha/3-months?lang=hi", "/hi/rashifal/singh/masik"),
    ("/rashifal/kumbha/yearly?lang=mr", "/mr/rashi-bhavishya/kumbh/varshik"), ("/hi", "/hi/"), ("/mr", "/mr/"),
])
def test_legacy_urls_redirect_permanently_in_one_hop(old, new):
    response = client.get(old, follow_redirects=False)
    assert response.status_code == 301 and response.headers["location"] == new
    landed = client.get(new, follow_redirects=False)
    assert landed.status_code == 200  # no chain


def test_unknown_legacy_and_cross_tree_urls_are_404():
    for path in ("/rashifal/libra", "/rashifal/mesha/monthly", "/rashifal/mesha/nope", "/horoscope/tula", "/hi/rashifal/libra",
                 "/mr/rashi-bhavishya/tula/today", "/horoscope/libra/aaj", "/hi/birth-chart", "/mr/horoscope", "/hi/about"):
        assert client.get(path, follow_redirects=False).status_code == 404, path


def test_weekly_hub_is_not_mistaken_for_a_rashi(crawl):
    for lang in i18n.LANGS:
        weekly, daily = i18n.url_for("rashifal-weekly", lang), i18n.url_for("rashifal-hub", lang)
        assert crawl[weekly][0] == "rashifal-weekly" and 'id="hub-cards"' in crawl[weekly][3].text
        assert crawl[weekly][4].title != crawl[daily][4].title
        assert crawl[weekly][3].text.count('class="card rashi-card"') == 12


def test_error_pages_follow_the_language_tree():
    english, hindi = client.get("/no-such-page"), client.get("/hi/no-such-page")
    assert english.status_code == hindi.status_code == 404
    assert f'href="{i18n.url_for("kundali", "hi")}"' in hindi.text and '<html lang="hi">' in hindi.text
    assert f'href="{i18n.url_for("kundali", "en")}"' in english.text and "noindex" in english.text


# ---- the page-config system ----------------------------------------------------------------------------------------


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif is_dataclass(value):
        for f in fields(value):
            yield from _strings(getattr(value, f.name))


def test_content_modules_are_in_step():
    reference = pages.content("en")
    for lang in i18n.LANGS:
        module = pages.content(lang)
        assert set(module.UI) == set(reference.UI), lang
        assert tuple(module.PAGES) == pages.COPY_KEYS, lang
        for key in pages.COPY_KEYS:
            copy, ref = module.PAGES[key], reference.PAGES[key]
            assert set(copy.extra) == set(ref.extra), (lang, key, set(copy.extra) ^ set(ref.extra))
            assert bool(copy.product) == bool(ref.product), (lang, key)
        for key in i18n.TOOL_KEYS:
            copy = module.PAGES[key]
            assert copy.product and copy.product.points and 4 <= len(copy.sections) and 4 <= len(copy.faqs) <= 8, (lang, key)
            assert copy.form_heading and copy.submit_label and copy.result_heading and copy.card_blurb, (lang, key)
        assert 4 <= len(module.PAGES["consultation"].faqs) <= 8


def test_local_pages_hold_exactly_the_pages_their_own_tree_has():
    """A calculator that exists in one language keeps its copy in that module's LOCAL_PAGES, because every
    module's PAGES must equal COPY_KEYS - that equality is what keeps the three trees in step, and a page
    existing in one language is a different thing from a page whose translation is missing.

    This pins the two halves together. A registry entry with no copy is a 500 on a live URL; copy with no
    registry entry is text nobody can reach, which nothing else here would notice.
    """
    for lang in i18n.LANGS:
        module = pages.content(lang)
        local = getattr(module, "LOCAL_PAGES", {})
        expected = {key for key in i18n.EN_ONLY_TOOL_KEYS if lang in i18n.page_langs(key)}
        assert set(local) == expected, (lang, set(local) ^ expected)
        for key, copy in local.items():
            # the same bar the shared tool pages are held to
            assert copy.product and copy.product.points, (lang, key)
            assert 4 <= len(copy.sections) and 4 <= len(copy.faqs) <= 8, (lang, key)
            assert copy.form_heading and copy.submit_label and copy.result_heading and copy.card_blurb, (lang, key)
            # it renders tool.html, so it needs every `extra` string that template reads for the page whose
            # renderer it borrows - a missing download_busy is an empty error message on a real failure path
            shared = pages.TOOLS[key].renderer
            reference = module.PAGES.get(shared)
            if reference is not None:
                missing = set(reference.extra) - set(copy.extra)
                assert not missing, (lang, key, missing)


def test_copy_never_hardcodes_a_price_a_quota_or_a_path():
    for lang in i18n.LANGS:
        module = pages.content(lang)
        for text in [*_strings(module.UI), *[s for copy in module.PAGES.values() for s in _strings(copy)]]:
            assert not re.search(r"₹\s*\d", text), (lang, text[:80])  # prices are {price...} placeholders
            assert not re.search(r"(Rs\.?|रु\.?|रुपये)\s*\d", text), (lang, text[:80])
            assert not re.search(r'href="/', text), (lang, text[:80])  # links are {url_...} placeholders
            for placeholder in re.findall(r"\{([^{}]*)\}", text):
                assert re.fullmatch(r"[a-z][a-z0-9_]*", placeholder), (lang, placeholder)


def test_prices_on_pages_are_the_catalogue_prices(crawl, monkeypatch):
    prices = catalogue.prices_inr()
    # The launch prices. This pin is meant to break when one changes - that is the point of it.
    assert prices == {"kundali-report-simple": 49, "kundali-report": 249, "matching-report": 99,
                      "mangal-dosha-remedy": 49, "sade-sati-guide": 49,
                      "consultation-basic": 99, "consultation-premium": 299}
    for lang in i18n.LANGS:
        for key, spec in pages.TOOLS.items():
            if lang not in i18n.page_langs(key):  # a calculator this tree does not have
                continue
            page = crawl[i18n.url_for(key, lang)][4]
            options = pages.purchase_options(key)  # one entry per tier the page sells, cheapest first
            assert [(p["data-product"], p["data-price-inr"]) for p in page.products] == \
                [(option["product"], str(prices[option["product"]])) for option in options]
            html = crawl[i18n.url_for(key, lang)][3].text
            for option in options:
                assert f"₹{prices[option['product']]}" in html
            assert set(re.findall(r"₹\s?(\d+)", html)) <= {str(value) for value in prices.values()}, (lang, key)
        chat = crawl[i18n.url_for("consultation", lang)]
        offered = [(p["data-product"], p["data-price-inr"]) for p in chat[4].products]
        assert offered == [("consultation-basic", str(prices["consultation-basic"])),
                           ("consultation-premium", str(prices["consultation-premium"]))]
        assert "consultation-pack" not in chat[3].text  # retired: honoured for old buyers, never offered
        paywall = chat[3].text.split('id="paywall-heading">', 1)[1].split("</h3>", 1)[0]
        assert f"₹{prices[pages.CONSULTATION_PRODUCT]}" in paywall and "10" in paywall and "PDF" in paywall


def test_a_price_change_reaches_every_language_without_touching_copy(monkeypatch):
    """Every tier's price, on every page, in every language, comes from the catalogue at request time."""
    # what the pages show today, read before the change so this test never needs a price written into it
    was = catalogue.prices_inr()
    changed = {catalogue.SIMPLE_REPORT: 37, catalogue.DETAILED_REPORT: 61,
               catalogue.BASIC_PACK: 123, catalogue.PREMIUM_PACK: 234}
    for product in (catalogue.SIMPLE_REPORT, catalogue.DETAILED_REPORT):
        monkeypatch.setitem(catalogue._REPORT_PRICES_INR, product, changed[product])
    # the consultation tiers are priced in the catalogue too, not in the chat settings: there are two of them
    monkeypatch.setitem(catalogue._PACKS, catalogue.BASIC_PACK, (changed[catalogue.BASIC_PACK], catalogue.SIMPLE_REPORT, True))
    monkeypatch.setitem(catalogue._PACKS, catalogue.PREMIUM_PACK, (changed[catalogue.PREMIUM_PACK], catalogue.DETAILED_REPORT, True))
    for lang in i18n.LANGS:
        pages_by_key = {"kundali": (catalogue.SIMPLE_REPORT, catalogue.DETAILED_REPORT),
                        "consultation": (catalogue.BASIC_PACK, catalogue.PREMIUM_PACK)}
        for key, products in pages_by_key.items():
            html = client.get(i18n.url_for(key, lang)).text
            for product in products:  # both tiers of that page move, and neither old price survives
                assert f"₹{changed[product]}" in html and f'data-price-inr="{changed[product]}"' in html
                assert not re.search(rf"₹\s?{was[product]}\b", html), (lang, key, product)
                assert f'data-price-inr="{was[product]}"' not in html
        chat = client.get(i18n.url_for("consultation", lang)).text
        assert f"₹{changed[catalogue.DETAILED_REPORT]}" in chat  # the tier copy names what the book costs on its own


def test_by_name_mode_has_its_own_section_faq_and_deep_link(crawl):
    for lang in i18n.LANGS:
        key, _, _, response, page = crawl[i18n.url_for("matching", lang)]
        html = response.text
        assert 'id="by-name"' in html and 'data-mode="name"' in html and 'data-mode="birth"' in html
        assert 'id="about-by-name"' in html  # its own H2 section in the long-form copy
        assert "name-note" in page.ids and "boy-name-hint" in page.ids and "girl-name-error" in page.ids
        copy = pages.get("matching", lang)
        section = next(s for s in copy.sections if s.anchor == "by-name")
        assert section.heading and len(" ".join(b for b in section.blocks if isinstance(b, str))) > 300
        assert sum(1 for q, _ in copy.faqs if re.search(r"name|नाम|नाव", q, re.I)) >= 2, lang
        placeholders = re.findall(r'data-name-placeholder="([^"]+)"', html)  # different example names for boy and girl
        assert len(placeholders) == 2 and placeholders[0] != placeholders[1], lang
        # deep link: same page, same canonical
        deep = _Page(client.get(i18n.url_for("matching", lang) + "?mode=name").text)
        assert deep.links["canonical"] == page.links["canonical"]
    assert "by name" in crawl["/horoscope-matching"][4].title.lower()
    assert "Kundli Milan by Name" in crawl["/hi/kundali-matching"][4].title
    assert "Patrika Matching" in crawl["/mr/patrika-matching"][4].title and "पत्रिका" in crawl["/mr/patrika-matching"][4].title


def test_seo_map_vocabulary_per_language(crawl):
    expectations = {
        "/birth-chart": r"birth chart", "/hi/kundli": r"kund(a)?li", "/mr/kundali": r"kundali.*marathi|marathi.*kundali",
        "/horoscope-matching": r"horoscope matching", "/hi/kundali-matching": r"kundali matching",
        "/ai-astrologer": r"ai astrolog", "/hi/ai-jyotish": r"jyotish|prediction", "/mr/ai-jyotish": r"jyotish",
        "/horoscope": r"horoscope today", "/hi/rashifal": r"aaj ka rashifal", "/mr/rashi-bhavishya": r"rashi bhavishya",
        "/horoscope/weekly": r"weekly horoscope", "/hi/rashifal/saptahik": r"saptahik rashifal",
        "/horoscope/libra/today": r"libra horoscope today", "/hi/rashifal/tula/aaj": r"tula rashi today",
        "/mr/rashi-bhavishya/tula/aaj": r"tula rashi bhavishya",
    }
    for path, pattern in expectations.items():
        page = crawl[path][4]
        assert re.search(pattern, page.title, re.I), (path, page.title)
    assert "तुला राशिफल आज" in crawl["/hi/rashifal/tula/aaj"][4].h1[0]
    assert "तूळ राशिभविष्य" in crawl["/mr/rashi-bhavishya/tula/aaj"][4].h1[0]
    visible = lambda path: re.sub(r"<[^>]+>", " ", crawl[path][3].text.split("<main", 1)[1].split("</main>")[0])  # noqa: E731
    for path in ("/mr/rashi-bhavishya", "/mr/rashi-bhavishya/tula/aaj", "/mr/rashi-bhavishya/tula"):
        assert "राशिफल" not in visible(path) and "राशीभविष्य" not in visible(path), path  # MR says राशिभविष्य
    for path in ("/horoscope", "/horoscope/weekly", "/horoscope/libra", "/horoscope/libra/today"):
        assert "rashifal" not in visible(path).lower(), path  # EN says horoscope


def test_json_ld_is_valid_and_faq_mirrors_the_page(crawl):
    for lang in i18n.LANGS:
        for key in (*i18n.TOOL_KEYS, "consultation"):
            _, _, _, response, page = crawl[i18n.url_for(key, lang)]
            copy = pages.get(key, lang)
            faq = next(block for block in page.json_ld if block["@type"] == "FAQPage")
            assert [q["name"] for q in faq["mainEntity"]] == [question for question, _ in copy.faqs]
            app_block = next(block for block in page.json_ld if block["@type"] == "WebApplication")
            assert app_block["url"] == BASE + i18n.url_for(key, lang) and app_block["inLanguage"] == lang
            json.dumps(page.json_ld)
