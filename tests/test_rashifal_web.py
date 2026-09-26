"""Phase 7 x SEO map §4: the rashifal web layer in three language trees - 180 permanent reading URLs, 36 per-rashi hubs,
3 daily hubs and 3 weekly hubs - served from the store + engine, never from the AI."""

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from app.main import app
from app.rashifal import generate, store
from app.rashifal import i18n as words
from app.rashifal.generate import refresh
from app.rashifal.periods import IST, PERIOD_SLUGS, RASHI_SLUGS
from app.web import i18n, pages, site
from app.web import rashifal as web_rashifal
from tests.rashifal_fake import MARK, MARK_DEVANAGARI, FakeRashifalClient
from tests.test_web import _Page

client = TestClient(app)
NOW = dt.datetime(2026, 9, 21, 10, 0, tzinfo=IST)  # Monday
BASE = "http://localhost:8000"
MARKS = {"en": MARK, **MARK_DEVANAGARI}


def reading_urls(lang: str) -> list[str]:
    return [i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period)
            for rashi in i18n.RASHI_KEYS for period in i18n.PERIOD_KEYS]


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(web_rashifal, "_now", lambda: NOW)


@pytest.fixture
def populated(monkeypatch):
    monkeypatch.setattr(generate, "_utcnow", lambda: dt.datetime(2026, 9, 20, 18, 37, tzinfo=dt.timezone.utc))
    fake = FakeRashifalClient()
    assert refresh(moment=NOW, client=fake).ok  # one call per page or per (page, language): calc-engine's business
    rows = store.list_pages()
    assert len(rows) == 60 and all(set(row["languages"]) == set(i18n.LANGS) for row in rows.values())
    return fake


def _get(path: str) -> tuple[_Page, str]:
    response = client.get(path)
    assert response.status_code == 200, path
    return _Page(response.text), response.text


def _assert_unique(found: list[_Page], urls: list[str]):
    assert len(found) == len(urls)
    for values in ([p.title for p in found], [p.h1[0] for p in found], [p.meta["description"] for p in found]):
        assert len(set(values)) == len(urls)
    assert [p.links["canonical"] for p in found] == [BASE + url for url in urls]
    assert all(len(p.h1) == 1 for p in found)


# ---- the 180 URLs --------------------------------------------------------------------------------


def test_the_urls_are_exactly_the_seo_map():
    en, hi, mr = (reading_urls(lang) for lang in i18n.LANGS)
    assert len(set(en + hi + mr)) == 180
    assert all(re.fullmatch(r"/horoscope/[a-z]+/(today|weekly|monthly|6-months|yearly)", url) for url in en)
    assert all(re.fullmatch(r"/hi/rashifal/[a-z]+/(aaj|saptahik|masik|6-mahine|varshik)", url) for url in hi)
    assert all(re.fullmatch(r"/mr/rashi-bhavishya/[a-z]+/(aaj|saptahik|masik|6-mahine|varshik)", url) for url in mr)
    assert "/horoscope/sagittarius/today" in en and "/hi/rashifal/dhanu/masik" in hi and "/mr/rashi-bhavishya/singh/varshik" in mr
    # the registry's internal keys are the store's keys, and calc-engine's URL helper agrees with the registry
    assert list(i18n.RASHI_KEYS) == RASHI_SLUGS and list(i18n.PERIOD_KEYS) == PERIOD_SLUGS
    from app.rashifal.periods import url_path

    for lang in i18n.LANGS:
        assert url_path(lang) == i18n.url_for("rashifal-hub", lang)
        assert url_path(lang, period="weekly") == i18n.url_for("rashifal-weekly", lang)
        for rashi in RASHI_SLUGS:
            for period in PERIOD_SLUGS:
                assert url_path(lang, rashi, period) == i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_all_pages_render_without_any_content_as_transit_fact_pages(lang):
    found, urls = [], reading_urls(lang)
    for url in urls:
        page, html = _get(url)
        found.append(page)
        assert "pending" in page.ids and "reading" not in page.ids  # honest: no reading yet ...
        assert "transit-facts" in page.ids and html.count("<tr") >= 9  # ... but never an empty shell
        assert "period-range" in page.ids and "2026" in html  # the date is visible
        assert "rashifal-disclaimer" in page.ids
    _assert_unique(found, urls)


def test_a_fact_page_is_the_engines(monkeypatch):
    page, html = _get("/horoscope/leo/today")
    assert "Monday, 21 September 2026" in html and "Shukla Dashami" in html and "Uttarashadha" in html
    assert "Shani dhaiya is active" in html  # Simha: Saturn in the 8th - from the engine
    block = next(b for b in page.json_ld if b["@type"] == "WebPage")
    assert block["dateModified"] == "2026-09-20T18:30:00+00:00" and block["url"] == BASE + "/horoscope/leo/today"
    assert block["inLanguage"] == "en"
    # the monthly page (new period) renders from the engine as well: 1-30 September
    _, monthly = _get("/hi/rashifal/singh/masik")
    assert "1 सितंबर 2026 – 30 सितंबर 2026" in monthly
    _, marathi = _get("/mr/rashi-bhavishya/singh/aaj")
    assert "सोमवार, 21 सप्टेंबर 2026" in marathi and "मंगळ" in marathi and "शनी" in marathi and "ग्रहस्थिती" in marathi
    _, hindi = _get("/hi/rashifal/singh/aaj")
    assert "सोमवार, 21 सितंबर 2026" in hindi and "मंगल" in hindi and "शनि" in hindi and "मंगळ" not in hindi


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_all_pages_render_their_stored_reading_in_their_language_and_are_unique(populated, lang):
    found, urls = [], reading_urls(lang)
    for url in urls:
        page, html = _get(url)
        found.append(page)
        assert "reading" in page.ids and "pending" not in page.ids and MARKS[lang] in html
        for other in set(MARKS.values()) - {MARKS[lang]}:
            assert other not in html  # one language per URL
    _assert_unique(found, urls)
    assert not any(re.search(r"\d{4}", p.links["canonical"].removeprefix(BASE)) for p in found)  # permanent, never date-stamped
    # The TITLE carries a date on exactly two periods, and the URL on none - the line above protects that.
    # Monthly and yearly are the ones people date in the query ("dhanu rashifal september 2026",
    # "<sign> rashifal 2027"), and both regenerate when their window rolls, so the title is never stale.
    # Daily, weekly and 6-month stay undated: 6-month is a rolling window that names no period anyone
    # types, and a dated daily or weekly title reads as stale the moment it rolls.
    dated_periods = {"monthly", "yearly"}
    for page, url in zip(found, urls):
        period = i18n.resolve(url.removeprefix(BASE))[2].get("period")
        assert bool(re.search(r"20\d\d", page.title)) == (period in dated_periods), (url, page.title)


def test_titles_and_h1_follow_the_top_query_pattern_per_language(populated):
    en, _ = _get("/horoscope/libra/today")
    hi, _ = _get("/hi/rashifal/tula/aaj")
    mr, _ = _get("/mr/rashi-bhavishya/tula/aaj")
    assert en.title.startswith("Libra Horoscope Today") and en.h1[0].startswith("Libra Horoscope Today")
    assert hi.title.startswith("Tula Rashi Today – तुला राशिफल आज") and hi.h1 == ["Tula Rashi Today – तुला राशिफल आज"]
    assert mr.title.startswith("Tula Rashi Bhavishya") and "तूळ राशिभविष्य" in mr.title and "तूळ राशिभविष्य" in mr.h1[0]
    for page in (en, hi, mr):
        assert page.title.endswith(f"| {site.SITE_NAME}")
    assert hi.title == f"{words.page_title('tula', 'today', 'hi')} | {site.SITE_NAME}"  # calc-engine's templates
    assert _get("/horoscope")[0].h1 == [words.hub_h1("today", "en")]
    assert _get("/hi/rashifal/saptahik")[0].h1 == [words.hub_h1("weekly", "hi")]


def test_a_populated_page_has_everything_the_seo_map_asks_for(populated):
    page, html = _get("/horoscope/sagittarius/weekly")
    assert page.meta["og:url"] == page.links["canonical"] == BASE + "/horoscope/sagittarius/weekly"
    assert page.meta["og:type"] == "article" and 70 <= len(page.meta["description"]) <= 220
    assert "21 September 2026 – 27 September 2026" in html  # the period, in visible text
    assert "Last updated" in html and "21 September 2026, 00:07 IST" in html  # 18:37 UTC on the 20th
    stored = store.get_page("dhanu", "weekly")
    for text in (stored["content"]["en"]["headline"], stored["content"]["en"]["tip"], "Career and money", "Love and family",
                 "Health and wellbeing", "Key dates"):
        assert text in html
    article = next(b for b in page.json_ld if b["@type"] == "Article")
    assert article["dateModified"] == "2026-09-20T18:37:00+00:00" == article["datePublished"]
    assert article["mainEntityOfPage"] == BASE + "/horoscope/sagittarius/weekly" and article["isAccessibleForFree"] is True
    crumbs = next(b for b in page.json_ld if b["@type"] == "BreadcrumbList")
    assert [item["item"] for item in crumbs["itemListElement"]] == [
        BASE + "/", BASE + "/horoscope", BASE + "/horoscope/sagittarius", BASE + "/horoscope/sagittarius/weekly"]

    # key dates: the date and the event text come from the engine brief, the note from the reading
    event = stored["brief"]["events"][0]
    assert words.format_date(event["date"], "en") in html and words.describe_event(event, "en") in html

    # three clearly marked, empty, hidden ad containers and no ad / third-party code
    slots = re.findall(r'<div class="ad-slot" data-ad-slot="([a-z-]+)" hidden></div>', html)
    assert slots == ["rashifal-top", "rashifal-mid", "rashifal-bottom"]
    for url in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert url.startswith(("/", "#", BASE, "https://www.googletagmanager.com/gtag/js?id=")), url
    # a static page: no JS needed to read it - the only scripts are the two site-wide ones from base.html, the
    # analytics bootstrap and the header nicety. Nothing here is page-level. (The async analytics loader is
    # `<script async src=`, which this pattern deliberately does not match; test_seo.py counts that one.)
    assert re.findall(r'<script src="([^"?]+)', html) == ["/static/js/analytics.js", "/static/js/nav.js"]
    assert "paywall" not in html.lower() and "data-product" not in html  # always free


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_internal_links_stay_in_the_language_and_follow_search_demand(populated, lang):
    path = i18n.url_for("rashifal-reading", lang, rashi="dhanu", period="weekly")
    _, html = _get(path)

    def nav(heading_id):
        return html[html.index(f'id="{heading_id}"'):].split("</nav>")[0]

    # the same rashi's other four periods
    assert re.findall(r'href="([^"]+)"', nav("other-periods-heading")) == [
        i18n.url_for("rashifal-reading", lang, rashi="dhanu", period=period) for period in i18n.PERIOD_KEYS if period != "weekly"]
    # the other eleven rashis for this period, highest search demand first (SEO map §4), then the weekly hub
    others = re.findall(r'href="([^"]+)"', nav("other-rashis-heading"))
    assert others[:-1] == [i18n.url_for("rashifal-reading", lang, rashi=rashi, period="weekly")
                           for rashi in i18n.rashis_by_demand(lang) if rashi != "dhanu"]
    assert others[-1] == i18n.url_for("rashifal-weekly", lang)
    # rashi hub + daily hub (breadcrumbs), the kundali tool and the consultation - all in the SAME language
    for key, params in (("rashifal-rashi", {"rashi": "dhanu"}), ("rashifal-hub", {}), ("kundali", {}), ("consultation", {})):
        assert f'href="{i18n.url_for(key, lang, **params)}"' in html, key
    main = html.split("<main", 1)[1].split("</main>", 1)[0]
    for href in re.findall(r'href="(/[^"]*)"', main):
        assert i18n.resolve(href)[1] == lang, href
    assert {"hi": "tula", "en": "karka", "mr": "simha"}[lang] == i18n.rashis_by_demand(lang)[0]


def test_headers():
    response = client.get("/horoscope/aries/today")
    assert response.headers["cache-control"] == "public, max-age=300" and response.headers["content-language"] == "en"
    assert response.headers["last-modified"] == "Sun, 20 Sep 2026 18:30:00 GMT"
    assert client.get("/mr/rashi-bhavishya/mesh/aaj").headers["content-language"] == "mr"
    assert client.get("/hi/rashifal").headers["content-language"] == "hi"


def test_ai_text_is_escaped(populated):
    page = store.get_page("mesha", "today")
    page["content"]["hi"]["headline"] = "<script>alert(1)</script> स्थिर दिन"
    page["content"]["hi"]["summary"] = "<img src=x onerror=alert(2)> सार"
    store.save_page("mesha", "today", period_start=page["period_start"], period_end=page["period_end"],
                    generated_at=page["generated_at"], model=page["model"], brief_hash=page["brief_hash"],
                    content=page["content"], brief=page["brief"], meta=page["meta"])
    for path in ("/hi/rashifal/mesh/aaj", "/hi/rashifal", "/hi/rashifal/mesh"):
        html = client.get(path).text
        assert "<script>alert(1)" not in html and "<img src=x" not in html, path
    assert "&lt;script&gt;alert(1)" in client.get("/hi/rashifal/mesh/aaj").text


def test_a_language_without_a_stored_reading_falls_back_to_facts_in_that_language(monkeypatch):
    monkeypatch.setenv("RASHIFAL_LANGUAGES", "en")
    refresh(["today"], ["mesha"], moment=NOW, client=FakeRashifalClient())
    page, html = _get("/horoscope/aries/today")
    assert "reading" in page.ids and MARK in html
    page, html = _get("/mr/rashi-bhavishya/mesh/aaj")  # the URL exists all the same: facts, in Marathi
    assert "pending" in page.ids and "reading" not in page.ids and MARK not in html
    assert "ग्रहस्थिती" in html and "मंगळ" in html
    assert "पढ़ें" not in html and "Read" not in html.split("<main", 1)[1].split("</main>")[0]


# ---- never the AI, stale content, 404s -----------------------------------------------------------


def test_page_views_never_touch_the_ai_client(populated, monkeypatch):
    import anthropic

    from app.ai import client as ai_client

    def boom(*args, **kwargs):
        raise AssertionError("a page view reached the AI layer")

    calls_before = len(populated.calls)
    monkeypatch.setattr(ai_client.ClaudeClient, "__init__", boom)
    monkeypatch.setattr(ai_client.ClaudeClient, "generate_json", boom)
    monkeypatch.setattr(ai_client.ClaudeClient, "generate_json_batch", boom)
    monkeypatch.setattr(anthropic, "Anthropic", boom)
    monkeypatch.setattr(generate, "refresh", boom)
    paths = [path for path, key, *_ in i18n.all_paths() if key.startswith("rashifal") or key == "home"]
    assert len(paths) == 180 + 36 + 3 + 3 + 3
    for path in paths:
        assert client.get(path).status_code == 200, path
    store.rollback("mesha", "today")
    with TestClient(app) as fresh:  # also with no content at all, after app start-up
        monkeypatch.setenv("APP_DB", str(store.db.db_path().with_name("empty.db")))
        for path in ("/horoscope/aries/yearly", "/hi/rashifal", "/mr/rashi-bhavishya/saptahik", "/horoscope/aries"):
            assert fresh.get(path).status_code == 200, path
    assert len(populated.calls) == calls_before
    source = open(web_rashifal.__file__, encoding="utf-8").read()
    imported = " ".join(re.findall(r"^from app\.rashifal[\w.]* import (.*)$", source, re.M))
    assert "generate" not in imported and "refresh" not in imported
    assert "ClaudeClient" not in source and "app.ai" not in source and "anthropic" not in source


def test_yesterdays_reading_stays_up_and_says_so_until_the_refresh_runs(populated, monkeypatch):
    monkeypatch.setattr(web_rashifal, "_now", lambda: dt.datetime(2026, 9, 22, 0, 2, tzinfo=IST))
    page, html = _get("/horoscope/aries/today")
    assert "stale-note" in page.ids and "reading" in page.ids and MARK in html
    assert "Tuesday, 22 September 2026" in html  # the page's period is today ...
    assert "Reading for: Monday, 21 September 2026" in html  # ... and the reading is labelled with its own day
    assert "Shukla Ekadashi" in html  # facts are already today's (engine)
    week, _ = _get("/horoscope/aries/weekly")
    assert "stale-note" not in week.ids  # same week: still current
    hub, hub_html = _get("/horoscope")  # the daily hub does not pass yesterday's summaries off as today's
    assert MARK not in hub_html and "Tuesday, 22 September 2026" in hub_html


@pytest.mark.parametrize("path", [
    "/horoscope/mesha/today", "/horoscope/Aries/today", "/horoscope/aries/daily", "/horoscope/aries/Today",
    "/horoscope/aries/3-months", "/horoscope/aries/aaj", "/horoscope/ophiuchus", "/horoscope/aries/today/2026-09-21",
    "/horoscope/13/today", "/hi/rashifal/aries/aaj", "/hi/rashifal/mesh/today", "/hi/rashifal/mesha/aaj",
    "/mr/rashi-bhavishya/mesh/weekly", "/mr/rashifal/mesh/aaj", "/hi/rashi-bhavishya", "/hi/horoscope/aries/today",
    "/horoscope/weekly/weekly", "/hi/rashifal/saptahik/aaj",
])
def test_unknown_slugs_are_404(path):
    assert client.get(path).status_code == 404


# ---- hubs ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_daily_and_weekly_hubs_show_all_12_rashis_with_their_summaries(populated, lang):
    for page_key, period in (("rashifal-hub", "today"), ("rashifal-weekly", "weekly")):
        path = i18n.url_for(page_key, lang)
        page, html = _get(path)
        assert page.links["canonical"] == BASE + path and len(page.h1) == 1
        assert html.count('class="card rashi-card"') == 12
        cards = html.split('id="hub-cards"', 1)[1].split("</ul>", 1)[0]
        linked = re.findall(r'<h2><a href="([^"]+)"', cards)
        assert linked == [i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period)
                          for rashi in i18n.rashis_by_demand(lang)]  # demand order, same language
        for rashi in i18n.RASHI_KEYS:
            row = store.get_page(rashi, period)["content"][lang]
            assert row["summary"] in html or row["summary"].replace("'", "&#39;") in html, (lang, rashi)
        assert "period-range" in page.ids and "last-updated" in page.ids and "2026" in html  # date + last updated
        other = i18n.url_for("rashifal-weekly" if page_key == "rashifal-hub" else "rashifal-hub", lang)
        for href in (other, i18n.url_for("kundali", lang), i18n.url_for("consultation", lang)):
            assert f'href="{href}"' in html
        copy = pages.get(page_key, lang)
        for text in (copy.intro, copy.sections[0].heading, copy.faqs[0][0]):
            assert str(escape(text)) in html, text
        assert next(b for b in page.json_ld if b["@type"] == "CollectionPage")["inLanguage"] == lang
        assert re.search(r'<a href="%s" aria-current="page">' % re.escape(i18n.url_for("rashifal-hub", lang)), html)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_hubs_without_content_show_engine_facts_not_empty_cards(lang):
    _, html = _get(i18n.url_for("rashifal-hub", lang))
    cards = html.split('id="hub-cards"', 1)[1].split("</ul>", 1)[0]
    assert cards.count("<li") == 12 and "last-updated" not in html
    bala = words.UI[lang]["chandra_bala_good"].split(":")[0]
    assert cards.count(bala) == 12  # every card carries the day's Moon facts for that rashi


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_rashi_hub(populated, lang):
    path = i18n.url_for("rashifal-rashi", lang, rashi="kumbha")
    page, html = _get(path)
    names = i18n.rashi_names("kumbha", lang)
    assert page.links["canonical"] == BASE + path and names["rashi"] in page.h1[0]
    assert set(re.findall(r'href="(%s/[a-z0-9-]+)"' % re.escape(path), html)) == {
        i18n.url_for("rashifal-reading", lang, rashi="kumbha", period=period) for period in i18n.PERIOD_KEYS}
    assert store.get_page("kumbha", "today")["content"][lang]["headline"] in html
    assert names["lord"] in html  # Saturn, named in the page language: Saturn (Shani) / शनि / शनी
    assert {"en": "Sade sati is active", "hi": "साढ़ेसाती चल रही है", "mr": "साडेसाती सुरू आहे"}[lang] in html
    others = html.split('id="others-heading"', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r'href="([^"]+)"', others)[:11] == [
        i18n.url_for("rashifal-rashi", lang, rashi=rashi) for rashi in i18n.rashis_by_demand(lang) if rashi != "kumbha"]
    for key in ("sade-sati", "kundali", "consultation", "rashifal-hub", "rashifal-weekly"):
        assert f'href="{i18n.url_for(key, lang)}"' in html, key
    titles = {_get(i18n.url_for("rashifal-rashi", lang, rashi=rashi))[0].title for rashi in i18n.RASHI_KEYS}
    assert len(titles) == 12


def test_nav_labels_use_each_languages_word_for_rashifal():
    assert re.search(r'<a href="/horoscope">Horoscope</a>', client.get("/").text)
    assert re.search(r'<a href="/hi/rashifal">राशिफल</a>', client.get("/hi/").text)
    assert re.search(r'<a href="/mr/rashi-bhavishya">राशिभविष्य</a>', client.get("/mr/").text)
