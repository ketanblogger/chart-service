"""A year's muhurat dates per purpose: computed, month by month, and honest about its own limits.

Every expectation about vivah here is a rule the tradition states, checked against the dates the
engine actually produced rather than against a run's output: no Tuesday, no rikta tithi, no
amavasya, nothing while the Sun is in Dhanu, and every nakshatra from the classical list.
"""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.engine import muhurta
from app.main import app
from app.web import i18n
from app.web import muhurat_year as pages

YEAR = 2027


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def vivah():
    return muhurta.find("vivah", dt.date(YEAR, 1, 1), dt.date(YEAR, 12, 31), limit=400)["days"]


def test_the_five_purposes_each_have_a_page_in_each_tree(client):
    assert i18n.MUHURAT_PURPOSES == ("vivah", "griha-pravesh", "vehicle", "property", "naming")
    for purpose in i18n.MUHURAT_PURPOSES:
        for lang in i18n.LANGS:
            path = i18n.url_for("muhurat-year", lang, purpose=purpose, year=YEAR)
            response = client.get(path)
            assert response.status_code == 200, path
            h1 = pages.TITLES[purpose][lang][0].format(year=YEAR)
            assert f"<h1>{h1}</h1>" in response.text, path


def test_the_keyword_is_the_heading(client):
    """"vivah muhurat 2027" is 5,000 searches a month and rising. It is the H1, not a paraphrase."""
    assert "Vivah Muhurat 2027" in pages.TITLES["vivah"]["en"][0].format(year=YEAR)
    assert "विवाह मुहूर्त 2027" in pages.TITLES["vivah"]["hi"][0].format(year=YEAR)
    assert "विवाह मुहूर्त 2027" in pages.TITLES["vivah"]["mr"][0].format(year=YEAR)


def test_no_vivah_date_falls_on_a_tuesday(vivah):
    assert vivah, "no vivah dates at all in the year - is the rule reachable?"
    assert [d["date"] for d in vivah if dt.date.fromisoformat(d["date"]).weekday() == 1] == []


def test_no_vivah_date_falls_in_dhanurmas(vivah):
    """The Sun in Dhanu, roughly mid-December to mid-January, is not a wedding month anywhere in
    India. A list of auspicious dates that included it would be wrong in a way every family reading
    it would notice at once."""
    inside = [d["date"] for d in vivah
              if muhurta.day_facts(dt.date.fromisoformat(d["date"]))["sun_sign"]["name"] == "Dhanu"]
    assert inside == []
    # ...and the exclusion really bites: the year's first date is after Dhanurmas ends, and the last
    # is before it begins. If this ever passed trivially the rule would have stopped applying.
    january = [d["date"] for d in vivah if d["date"].startswith(f"{YEAR}-01")]
    december = [d["date"] for d in vivah if d["date"].startswith(f"{YEAR}-12")]
    assert january and min(january) >= f"{YEAR}-01-14"
    assert december and max(december) <= f"{YEAR}-12-16"


def test_every_vivah_date_has_a_classical_vivah_nakshatra(vivah):
    allowed = set(muhurta.purposes()["vivah"]["nakshatras"])
    assert len(allowed) == 11
    assert {d["nakshatra"]["name"] for d in vivah} <= allowed


def test_no_vivah_date_is_a_rikta_tithi_or_amavasya(vivah):
    for day in vivah:
        assert day["tithi"]["day"] not in (4, 9, 14), day["date"]
        assert day["tithi"]["name"] != "Amavasya", day["date"]


def test_the_sun_sign_rule_is_a_rule_the_engine_applies_not_a_filter_in_the_page():
    """It belongs in the rules file with the rest of the tradition, so the finder tool and the page
    cannot disagree about which dates are wedding dates."""
    rule = muhurta.purposes()["vivah"]
    assert rule["avoid_sun_signs"] == ["Dhanu"]
    facts = muhurta.day_facts(dt.date(YEAR, 1, 5))
    assert facts["sun_sign"]["name"] == "Dhanu"
    assert muhurta.judge(facts, "vivah")["passes"] is False


def test_every_month_appears_even_the_empty_ones():
    """A month missing from the list reads as an oversight; "no date this month" is information."""
    months = pages.months_for("vivah", YEAR, "en")
    assert [m["number"] for m in months] == list(range(1, 13))
    assert all(m["name"] for m in months)


def test_the_page_says_what_a_date_list_cannot_do(client):
    """The most consequential thing on this site to be wrong about is letting somebody think these
    dates are a muhurta chosen for two particular people."""
    import html as html_module

    for lang in i18n.LANGS:
        # Unescaped: the English copy says "a family's own astrologer", and the template escapes
        # that apostrophe to &#39; - so a raw search fails on the one language with punctuation.
        page = html_module.unescape(
            client.get(i18n.url_for("muhurat-year", lang, purpose="vivah", year=YEAR)).text)
        assert pages.COPY[lang]["limits"] in page
        assert pages.COPY[lang]["limits_heading"] in page


def test_the_vivah_page_offers_matching_and_the_biodata_maker(client):
    html = client.get(i18n.url_for("muhurat-year", "mr", purpose="vivah", year=YEAR)).text
    assert i18n.url_for("matching", "mr") in html
    assert i18n.url_for("biodata", "mr") in html


def test_the_dates_on_the_page_are_the_dates_the_engine_found(client, vivah):
    """The page must not be able to show a date the finder would refuse, or hide one it allows."""
    html = client.get(i18n.url_for("muhurat-year", "en", purpose="vivah", year=YEAR)).text
    import re

    shown = sum(len(m["days"]) for m in pages.months_for("vivah", YEAR, "en"))
    assert shown == len(vivah)
    assert pages.COPY["en"]["count"].format(n=shown, year=YEAR) in html
    assert len(re.findall(r'<td class="mu-date">', html)) == shown


@pytest.mark.parametrize("purpose", ["griha-pravesh", "vehicle", "property", "naming"])
def test_every_other_purpose_also_produces_dates(purpose):
    """A page with nothing on it is worse than no page, so each one is checked for real content."""
    days = muhurta.find(purpose, dt.date(YEAR, 1, 1), dt.date(YEAR, 12, 31), limit=400)["days"]
    assert len(days) > 20, f"{purpose} found only {len(days)} dates in a whole year"
    allowed = set(muhurta.purposes()[purpose]["nakshatras"])
    assert {d["nakshatra"]["name"] for d in days} <= allowed
