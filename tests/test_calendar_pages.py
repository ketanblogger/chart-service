"""Diwali, the year's calendar and the ekadashi list as pages - plus the printable PDF."""
import io
import re

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.engine import festivals as festival_engine
from app.engine import hindu_calendar as calendar
from app.main import app
from app.web import calendar_pages as pages
from app.web.muhurat_year import MONTH_NAMES
from app.web import i18n

YEAR = 2027


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.mark.parametrize("key", ["diwali-year", "hindu-calendar", "ekadashi-year"])
@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_page_answers_in_every_tree(client, key, lang):
    response = client.get(i18n.url_for(key, lang, year=YEAR))
    assert response.status_code == 200
    h1 = pages.TITLES[key][lang][0].format(year=YEAR)
    assert f"<h1>{h1}</h1>" in response.text


def test_the_diwali_page_gives_a_window_per_city(client):
    """One time printed for the whole country is wrong for almost all of it: the window is set by
    sunset and the rising sign, and neither is the same in Mumbai and Kolkata."""
    html = client.get(i18n.url_for("diwali-year", "en", year=YEAR)).text
    for city in festival_engine.MAJOR_CITIES:
        assert city in html, city
    times = re.findall(r"<td>(\d{2}:\d{2})</td>", html)
    assert len(times) >= 2 * len(festival_engine.MAJOR_CITIES)
    # ...and they are genuinely different, which is the entire reason for the table.
    assert len(set(times)) > 2


def test_the_diwali_date_is_the_one_the_engine_decided(client):
    answer = festival_engine.windows("lakshmi-puja", YEAR, "Ujjain")
    html = client.get(i18n.url_for("diwali-year", "en", year=YEAR)).text
    assert str(answer["date"].day) in html and str(YEAR) in html


def test_the_calendar_lists_every_festival_the_engine_found(client):
    found = calendar.festivals(YEAR)
    months = pages.by_month(YEAR, "en")
    assert sum(len(month["festivals"]) for month in months) == len(found)
    assert [m["number"] for m in months] == list(range(1, 13))
    html = client.get(i18n.url_for("hindu-calendar", "en", year=YEAR)).text
    for item in found:
        assert item["names"]["en"] in html, item["key"]


def test_the_month_key_is_not_called_items():
    """Jinja resolves `month.items` to the DICT'S OWN .items method before it looks at the key, so a
    template iterating it gets a bound method and raises. A key named after something every mapping
    already has works everywhere except where it is used."""
    month = pages.by_month(YEAR, "en")[0]
    assert "festivals" in month and "items" not in month


def test_the_calendar_carries_the_amavasyas_and_purnimas(client):
    html = client.get(i18n.url_for("hindu-calendar", "mr", year=YEAR)).text
    assert pages.COPY["mr"]["amavasya_heading"] in html
    assert pages.COPY["mr"]["purnima_heading"] in html
    assert html.count(" · ") >= 20          # two lists of a dozen dates each


def test_the_ekadashi_page_lists_them_all_with_their_paksha(client):
    items = calendar.ekadashis(YEAR)
    html = client.get(i18n.url_for("ekadashi-year", "en", year=YEAR)).text
    assert len(re.findall(r'<td class="mu-date">', html)) == len(items)
    assert "Shukla" in html and "Krishna" in html


def test_every_page_says_which_convention_decided_the_date(client):
    """A family acts on these. Where a panchang can differ by a day, the page says so rather than
    picking one and sounding certain."""
    import html as html_module

    for key in ("diwali-year", "hindu-calendar", "ekadashi-year"):
        for lang in i18n.LANGS:
            page = html_module.unescape(client.get(i18n.url_for(key, lang, year=YEAR)).text)
            assert pages.COPY[lang]["convention"] in page, (key, lang)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_printable_calendar_is_one_a4_page_with_the_same_dates(client, lang):
    response = client.get(i18n.url_for("hindu-calendar", lang, year=YEAR) + "?print=1")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert round(float(box.width) / 72 * 25.4) == 210      # A4 and not shrunk to fit
    assert round(float(box.height) / 72 * 25.4) == 297
    text = reader.pages[0].extract_text()
    # PROBES THAT SURVIVE EXTRACTION, not the prettiest names. pypdf reconstructs text from glyph
    # codes, and a Devanagari conjunct often comes back with a replacement character where the
    # ligature was - "मकर संक्रांत" extracts as "मकर  सं\x00ां\x00त". That is a limit of reading
    # the PDF back, not of what is printed on it: the same file renders correctly and the font
    # coverage is asserted elsewhere. So the probes are a month name and a simple word.
    first_month = MONTH_NAMES[lang][0]
    assert first_month in text, f"{first_month!r} missing from the {lang} calendar"
    assert str(YEAR) in text


def test_the_new_pages_are_in_the_internal_link_map():
    from app.blog import links

    for lang in ("en", "hi", "mr"):
        targets = {key for key, _ in links.TERMS[lang].values()}
        assert {"biodata", "muhurat-year", "hindu-calendar", "ekadashi-year",
                "diwali-year"} <= targets, lang
