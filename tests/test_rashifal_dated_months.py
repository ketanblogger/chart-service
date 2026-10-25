"""The dated monthly pages: /hi/rashifal/dhanu/january-2027 and its eleven siblings.

The rolling /masik page is whatever month a reader arrives in. That is right for somebody who types
it and wrong for everything else: it cannot be linked to, it cannot be written ahead of time, and
in June it no longer says what it said in January. A dated month is the permanent address for one
month, written before the month starts, and these tests pin the four things that makes true -
the URL, the window, the canonical and the shape - plus the two it must NOT do: appear in a sitemap
with nothing written on it, or get picked up by the nightly generator.
"""
from __future__ import annotations

import datetime as dt

import re
from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rashifal import i18n as words
from app.rashifal import sitemap, store
from app.rashifal.generate import PERIOD_SLUGS as GENERATED_PERIODS
from app.rashifal.periods import (ALL_DATED_MONTHS, ALL_PERIODS, DATED_MONTHS, base_period, dated_month,
                                  is_dated_month, window_for)
from app.rashifal.prompts import sections_for
from app.web import i18n

client = TestClient(app)

TREES = ("en", "hi", "mr")


def test_a_dated_month_is_a_monthly_page_with_its_own_window():
    """The two halves of what "dated" means: the SHAPE is monthly, the WINDOW is one named month."""
    assert is_dated_month("2027-01") and not is_dated_month("monthly")
    assert dated_month("2027-01") == (2027, 1)
    assert base_period("2027-01") == "monthly"
    assert sections_for(base_period("2027-01")) == sections_for("monthly")
    assert len(sections_for(base_period("2027-01"))) == 16


@pytest.mark.parametrize("period, start, end", [
    ("2027-01", dt.date(2027, 1, 1), dt.date(2027, 1, 31)),
    ("2027-02", dt.date(2027, 2, 1), dt.date(2027, 2, 28)),   # 2027 is not a leap year
    ("2027-12", dt.date(2027, 12, 1), dt.date(2027, 12, 31)),
])
def test_the_window_is_that_month_whenever_you_ask(period, start, end):
    """A dated month ignores `moment` ENTIRELY, which is the whole difference from /masik.

    /masik in June is June. january-2027 is January in June, in December, and in 2029 - otherwise
    the permanent address would not be permanent, and a page written in December for January would
    start describing December the moment it was published.
    """
    for moment in (None, dt.datetime(2027, 6, 15, 9, 0), dt.datetime(2029, 1, 1, 0, 0)):
        window = window_for(period, moment)
        assert (window.start_date, window.end_date) == (start, end), f"at {moment}"
        assert window.key == start.isoformat()


def test_every_dated_month_resolves_in_every_tree():
    """The URL has to work in all three trees and round-trip back to the period key."""
    for period in ALL_DATED_MONTHS:
        for lang in TREES:
            path = i18n.url_for("rashifal-reading", lang, rashi="dhanu", period=period)
            assert path.endswith(f"-{period[:4]}"), path
            found = i18n.resolve(path)
            assert found == ("rashifal-reading", lang, {"rashi": "dhanu", "period": period}), path


def test_the_slug_names_the_month_in_english_in_all_three_trees():
    """"dhanu rashifal january 2027" is how the query is typed, so that is how the URL reads.

    One spelling per month also keeps the three trees' URLs parallel, which is what makes the
    hreflang set below reciprocal without a per-language month table to keep in step.
    """
    assert i18n.url_for("rashifal-reading", "hi", rashi="dhanu", period="2027-01") == \
        "/hi/rashifal/dhanu/january-2027"
    assert i18n.url_for("rashifal-reading", "mr", rashi="dhanu", period="2027-08") == \
        "/mr/rashi-bhavishya/dhanu/august-2027"
    assert i18n.url_for("rashifal-reading", "en", rashi="dhanu", period="2027-12") == \
        "/horoscope/sagittarius/december-2027"


def test_an_unregistered_month_is_not_a_url():
    """Only the months the registry publishes exist. 2026 and 2028 are not pages, and a reader who
    guesses one gets a 404 rather than a page with a year's worth of nothing on it."""
    assert i18n.resolve("/hi/rashifal/dhanu/january-2026") is None
    assert i18n.resolve("/hi/rashifal/dhanu/january-2028") is None
    assert i18n.resolve("/hi/rashifal/dhanu/thirteenth-2027") is None
    assert client.get("/hi/rashifal/dhanu/january-2026").status_code == 404


@pytest.mark.parametrize("lang", TREES)
def test_a_dated_page_renders_and_titles_itself_by_month(lang):
    path = i18n.url_for("rashifal-reading", lang, rashi="dhanu", period="2027-01")
    response = client.get(path)
    assert response.status_code == 200
    month = words.month_name(1, lang)
    assert month in response.text, f"{lang}: the title does not name {month}"
    assert "2027" in response.text
    # "मासिक" is the rolling page's word. A dated page names its month instead - that is what the
    # URL exists for, and a breadcrumb reading "Masik" on january-2027 tells the reader nothing.
    assert words.period_label("2027-01", lang) == f"{month} 2027"


def test_hreflang_is_reciprocal_across_the_three_trees():
    """All three versions must list the same set, or the signal is not reciprocal and is ignored."""
    sets = {}
    for lang in i18n.page_langs_for("rashifal-reading", rashi="dhanu", period="2027-01"):
        response = client.get(i18n.url_for("rashifal-reading", lang, rashi="dhanu", period="2027-01"))
        sets[lang] = sorted(set(re_findall_hreflang(response.text)))
    # THE SET IS THE TREES A READING EXISTS IN, like a blog post's. Where only Hindi and Marathi
    # have been written, English must NOT be advertised: a page may not name an hreflang alternate
    # the sitemap does not publish, which is exactly what the reciprocity check caught.
    written = i18n.page_langs_for("rashifal-reading", rashi="dhanu", period="2027-01")
    for lang in written:
        assert len(sets[lang]) == len(written), (lang, sets[lang], written)
        assert all("january-2027" in href for href in sets[lang]), sets[lang]
    assert sets[written[0]] == sets[written[-1]], "the set must be identical on every version"
    tags = client.get(i18n.url_for("rashifal-reading", written[0], rashi="dhanu", period="2027-01")).text
    assert tags.count('rel="alternate"') == len(written) + 1, "one per tree, plus x-default"
    assert 'hreflang="x-default"' in tags


def re_findall_hreflang(html: str) -> list[str]:
    import re

    return re.findall(r'<link rel="alternate" hreflang="[^"]+" href="([^"]+)"', html)


def _release(monkeypatch, period: str, langs=("hi",)) -> None:
    """Declare a month released, the way publishing one does - by editing the table.

    A test about what happens WHEN a month is released has to release one; reading the live table
    would make it pass or fail on whichever months happen to be published that week.
    """
    import app.rashifal.periods as periods
    import app.web.i18n as web_i18n
    import app.web.rashifal as rashifal_routes

    monkeypatch.setitem(periods.DATED_MONTH_LANGS, period, tuple(langs))
    monkeypatch.setattr(periods, "DATED_MONTHS", tuple(periods.DATED_MONTH_LANGS), raising=False)
    monkeypatch.setattr(rashifal_routes, "DATED_MONTHS", tuple(periods.DATED_MONTH_LANGS))
    monkeypatch.setattr(web_i18n._periods, "DATED_MONTHS", tuple(periods.DATED_MONTH_LANGS),
                        raising=False)
    # The sitemap imported the name directly, so patching the module it came from is not enough.
    import app.rashifal.sitemap as rashifal_sitemap

    monkeypatch.setattr(rashifal_sitemap, "DATED_MONTHS", tuple(periods.DATED_MONTH_LANGS))


def _store_a_page(rashi: str, period: str, lang: str = "hi") -> None:
    """A minimal stored reading, so a test can ask what changes once a dated month EXISTS."""
    from app.rashifal.brief import build_brief

    window = window_for(period)
    # A REAL BRIEF, not {}. The page renders its transit tables from the stored brief, so an empty
    # one raises KeyError on 'events' - and a fixture that cannot be rendered is not a fixture for
    # a test that renders the page.
    store.save_page(
        rashi, period,
        period_start=window.start_date.isoformat(), period_end=window.end_date.isoformat(),
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        model="test", brief_hash="0" * 16,
        content={lang: {"headline": "h", "summary": "s", "overview": "o", "tip": "t",
                        "sections": {"career_money": ["c"]}, "key_dates": []}},
        brief=build_brief(rashi, period), meta={"source": "test"})


def test_the_rolling_page_canonicals_to_the_dated_one_when_there_is_one(monkeypatch):
    """/masik and january-2027 carry the same reading in January, and only one may be canonical.

    The dated URL wins: it is the address that still means January in June. The rolling page keeps
    answering - somebody typed it - and hands its ranking to the dated one.
    """
    import app.web.rashifal as rashifal_routes

    january = dt.datetime(2027, 1, 10, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    monkeypatch.setattr(rashifal_routes, "_now", lambda: january)
    _release(monkeypatch, "2027-01")

    canonical_without = canonical_of("/hi/rashifal/dhanu/masik")
    assert canonical_without.endswith("/masik"), (
        "with nothing written for January the rolling page must stay canonical: pointing at an "
        "empty page would ask Google to prefer less content than it is looking at")

    _store_a_page("dhanu", "2027-01")
    assert canonical_of("/hi/rashifal/dhanu/masik").endswith("/january-2027")
    assert canonical_of("/hi/rashifal/dhanu/january-2027").endswith("/january-2027")


def canonical_of(path: str) -> str:
    import re

    found = re.search(r'<link rel="canonical" href="([^"]+)"', client.get(path).text)
    assert found, f"{path} has no canonical"
    return found.group(1)


def test_the_nightly_generator_never_writes_a_dated_month():
    """refresh() walks PERIOD_SLUGS. A dated month is written by hand, ahead of the month, and
    putting it in that list would make the nightly job try to produce 144 pages a year it has no
    brief for - and overwrite hand-written ones with generated prose."""
    assert not [period for period in DATED_MONTHS if period in GENERATED_PERIODS]
    assert len(GENERATED_PERIODS) == 5
    # The store, by contrast, must accept them: that is where the hand-written pages go.
    # The store accepts every month a URL could name, declared or not, so a page can be written and
    # checked before it is released.
    assert all(period in ALL_PERIODS for period in ALL_DATED_MONTHS)
    assert len(ALL_PERIODS) == len(GENERATED_PERIODS) + len(ALL_DATED_MONTHS)


def test_a_dated_month_reaches_the_sitemap_only_once_it_is_written(monkeypatch):
    """An unwritten dated URL is a thin page, and twelve per rashi is 144 thin pages. They are in
    the reverse index from the start - the URL belongs to this page key whether or not anybody has
    written it - but they stay out of the sitemap until there is a reading on them."""
    _release(monkeypatch, "2027-01")
    # The period is matched DIRECTLY, not through this module's DATED_MONTHS: that name was imported
    # at module load, before the release, so filtering through it finds nothing and the test passes
    # for the wrong reason.
    before = sitemap.rashifal_sitemap_entries("https://example.test")
    assert not [e for e in before if e["period"] == "2027-01"]

    _store_a_page("dhanu", "2027-01")
    after = sitemap.rashifal_sitemap_entries("https://example.test")
    dated = [e for e in after if e["period"] == "2027-01"]
    assert dated, "a written dated month must be in the sitemap"
    assert {e["rashi"] for e in dated} == {"dhanu"}, "only the rashi that has one"
    assert {e["period"] for e in dated} == {"2027-01"}
    # And it is listed as a monthly page, not as an unknown period.
    assert {e["changefreq"] for e in dated} == {"monthly"}


def test_the_dated_brief_carries_that_month_s_eclipses_and_no_months_table():
    """A month page wants the eclipses that fall INSIDE it and has no use for a months table."""
    from app.rashifal.brief import build_brief

    january = build_brief("dhanu", "2027-01")
    assert january["eclipses"] == [], "nothing eclipses in January 2027"
    assert "months" not in january, "a month page does not need a table of months"

    august = build_brief("dhanu", "2027-08")
    assert [one["date"] for one in august["eclipses"]] == ["2027-08-02", "2027-08-17"]
    # And it says what a reader HERE will see, not what the eclipse is on its own path.
    partial = next(one for one in august["eclipses"] if one["date"] == "2027-08-02")
    assert partial["kind"] == "total" and partial["india_kind"] == "partial"


def test_a_declared_month_has_every_rashi_written_in_every_tree_it_claims():
    """A declared month must have all twelve readings, in each tree it claims, ON DISK.

    CHECKED AGAINST content/rashifal/, NOT THE STORE. The first version read store.get_page, which
    cannot work: conftest points APP_DB at an empty temp file for every test, so the store is always
    empty here. That assertion only ever passed because the declaration was empty too, and it failed
    the moment a month was really declared - against content that existed. That is the worst kind of
    guard: green until the day it matters, then wrong about why.

    The payload files are the right thing to check anyway. They are what the deploy loads
    (scripts/rashifal_handwritten.py load), they are tracked, and they exist in any checkout - so
    this states exactly what publishing a month requires: the content ships with the declaration.

    Proved to bite by declaring 2027-07, which has no payloads: it names all twelve.
    """
    from app.rashifal.periods import DATED_MONTH_LANGS, RASHI_SLUGS

    content = Path(__file__).resolve().parents[1] / "content" / "rashifal"
    missing = []
    for period, langs in DATED_MONTH_LANGS.items():
        for rashi in RASHI_SLUGS:
            path = content / f"{rashi}-{period}.json"
            if not path.exists():
                missing.append(f"{path.name} (no payload at all)")
                continue
            written = set((json.loads(path.read_text(encoding="utf-8")).get("content") or {}))
            missing += [f"{path.name}:{lang}" for lang in langs if lang not in written]
    assert not missing, (
        f"{len(missing)} reading(s) are declared in DATED_MONTH_LANGS but not written: {missing[:8]}. "
        "Declaring a month publishes twelve URLs per tree; write them first.")


# ---- one URL per rashi-year ------------------------------------------------------------------------


def test_the_per_rashi_year_url_redirects_where_the_written_reading_lives():
    """/hi/rashifal/<rashi>/2027 -> /hi/rashifal/<rashi>/varshik, for all twelve, in both trees.

    The two URLs carried the same year. The rolling yearly page has the written reading AND the
    transit table; the dated one had the table alone and an FAQ promising a reading that existed one
    URL away. 301 rather than canonical: there is nothing on the dated page the target lacks.
    """
    from app.rashifal.periods import RASHI_SLUGS
    from app.web import rashifal as web_rashifal

    assert web_rashifal.YEAR_PAGE_REDIRECT_LANGS, "no tree redirects; this test would prove nothing"
    for lang in web_rashifal.YEAR_PAGE_REDIRECT_LANGS:
        for rashi in RASHI_SLUGS:
            source = i18n.url_for("rashifal-year", lang, rashi=rashi, year=2027)
            response = client.get(source, follow_redirects=False)
            assert response.status_code == 301, (source, response.status_code)
            assert response.headers["location"] == i18n.url_for(
                "rashifal-reading", lang, rashi=rashi, period="yearly"), source


def test_a_tree_either_publishes_the_year_page_or_redirects_it_never_both_or_neither():
    from app.web import rashifal as web_rashifal

    published, redirecting = set(i18n.YEAR_PAGE_LANGS), set(web_rashifal.YEAR_PAGE_REDIRECT_LANGS)
    assert published | redirecting == set(i18n.LANGS), (published, redirecting)
    assert not (published & redirecting), published & redirecting


def test_a_redirecting_year_url_is_not_in_the_published_set_and_nothing_links_to_it():
    """Unpublished AND unlinked. The redirect exists for URLs already in Google's index, not as a
    hop the site walks a reader through: the year hub's cards and the rolling page's own links point
    straight at the reading in those trees."""
    from app.web import rashifal as web_rashifal

    paths = {path for path, *_ in i18n.all_paths()}
    for lang in web_rashifal.YEAR_PAGE_REDIRECT_LANGS:
        for rashi in ("dhanu", "mesha"):
            assert i18n.url_for("rashifal-year", lang, rashi=rashi, year=2027) not in paths, lang
    for lang in i18n.YEAR_PAGE_LANGS:
        assert i18n.url_for("rashifal-year", lang, rashi="dhanu", year=2027) in paths, lang

    # THE EXACT URLS, not "anything ending in 2027": the hub legitimately carries its own hreflang
    # alternates and the gochar year links, which all end that way. An earlier version of this
    # assertion matched those and failed on a hub that was perfectly correct.
    from app.rashifal.periods import RASHI_SLUGS

    redirecting = {i18n.url_for("rashifal-year", lang, rashi=rashi, year=2027)
                   for lang in web_rashifal.YEAR_PAGE_REDIRECT_LANGS for rashi in RASHI_SLUGS}
    for lang in web_rashifal.YEAR_PAGE_REDIRECT_LANGS:
        hub = client.get(i18n.url_for("rashifal-year-hub", lang, year=2027))
        assert hub.status_code == 200
        linked = {href for href in re.findall(r'href="([^"]+)"', hub.text)} & redirecting
        assert not linked, f"the {lang} year hub links to URLs that only redirect: {sorted(linked)}"

    for lang in web_rashifal.YEAR_PAGE_REDIRECT_LANGS:
        page = client.get(i18n.url_for("rashifal-reading", lang, rashi="dhanu", period="yearly"))
        linked = {href for href in re.findall(r'href="([^"]+)"', page.text)} & redirecting
        assert not linked, f"the {lang} yearly reading links to URLs that only redirect: {sorted(linked)}"


def test_no_page_promises_a_written_reading_that_already_exists():
    """The FAQ said "yes, closer to the year" while twenty-four written readings were live."""
    from app.web import pages

    for lang in i18n.LANGS:
        copy = pages.get("rashifal-year", lang,
                         **i18n.rashi_names("dhanu", lang), year="2027")
        for question, answer in (copy.faqs or ()):
            assert "नज़दीक" not in answer and "जवळ" not in answer, (lang, question)
            assert "closer to the year" not in answer, (lang, question)
        assert "closer to the year" not in (copy.extra or {}).get("written_pending", ""), lang
