"""/horoscope/2027 - the whole year for all twelve rashis.

"rashifal 2027" asks about the YEAR; the per-rashi pages answer "my sign in 2027". This page is the
one the big term is actually asking for, and it carries what is the same sky for everybody: where the
slow grahas stand, and the year's eclipses.

Invented people only; `tests/` is published.
"""

import pytest
from fastapi.testclient import TestClient

from app.engine import eclipses as ec
from app.main import app
from app.rashifal.year_facts import slow_graha_stays
from app.web import i18n

client = TestClient(app)
YEAR = 2027


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_hub_exists_in_every_tree(lang):
    response = client.get(i18n.url_for("rashifal-year-hub", lang, year=YEAR))
    assert response.status_code == 200


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_it_links_all_twelve_rashi_pages_for_that_year(lang):
    html = client.get(i18n.url_for("rashifal-year-hub", lang, year=YEAR)).text
    for rashi in i18n.RASHI_KEYS:
        href = i18n.url_for("rashifal-year", lang, rashi=rashi, year=YEAR)
        assert f'href="{href}"' in html, (lang, rashi)


def test_the_year_route_does_not_shadow_the_rashi_or_period_routes():
    """"/horoscope/2027" must not be read as a rashi slug, and "/horoscope/aries/today" must not be
    read as a year. Starlette matches in registration order, so the typed year route goes first."""
    for path in ("/horoscope/2027", "/horoscope/aries", "/horoscope/aries/2027",
                 "/horoscope/aries/today"):
        assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_transits_are_shown_without_a_house(lang):
    """The house is the only part that depends on whose chart it is. Showing one here - counted from
    Mesha, because Mesha is first - is the kind of quiet wrongness nobody notices for months."""
    stays = slow_graha_stays(YEAR)
    assert stays
    assert all("house" not in stay for stay in stays)


def test_the_transits_match_what_the_engine_found():
    """Shani enters Mesha in June 2027 and retrogrades back into Meena in October - the example the
    year_facts module's own docstring uses."""
    stays = slow_graha_stays(YEAR)
    shani = [s for s in stays if "Shani" in str(s["graha"])]
    signs = [s["sign"]["name"] for s in shani]
    assert signs == ["Meena", "Mesha", "Meena"], signs


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_eclipse_of_the_year_is_listed(lang):
    """A list that quietly omits the three penumbral ones is one a reader cannot check anywhere."""
    html = client.get(i18n.url_for("rashifal-year-hub", lang, year=YEAR)).text
    for one in ec.eclipses(YEAR):
        assert one["date"] in html, (lang, one["date"])


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_kind_is_fully_translated_not_half(lang):
    """"उपछाया lunar" - the adjective translated and the noun not - is worse than either language."""
    for one in ec.eclipses(YEAR):
        name = ec.full_name(one, lang)
        if lang == "en":
            assert "eclipse" in name
        else:
            assert "ग्रहण" in name, name
            assert "(" in name and "eclipse" in name, "the Roman phrase people type comes after it"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_grahan_shows_city_times_in_the_page_s_own_script(lang):
    """A Hindi page that says "Delhi" in Latin letters reads as machine-made, and the site's own
    language check refuses Latin words in a Devanagari page - which is how this was caught."""
    html = client.get(i18n.url_for("rashifal-year-hub", lang, year=YEAR)).text
    august = next(e for e in ec.eclipses(YEAR) if e["date"] == "2027-08-02")
    for city in august["cities"]:
        assert ec.city_name(city["city"], lang) in html, (lang, city["city"])
        assert city["maximum"] in html
    if lang != "en":
        assert "Mumbai" not in html and "Delhi" not in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_penumbral_note_is_on_the_page(lang):
    html = client.get(i18n.url_for("rashifal-year-hub", lang, year=YEAR)).text
    assert ec.PENUMBRAL_NOTE[lang][:40] in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_page_sells_nothing_and_points_at_the_free_chart(lang):
    html = client.get(i18n.url_for("rashifal-year-hub", lang, year=YEAR)).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    assert i18n.url_for("kundali", lang) in body
    assert "₹" not in body


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_prose_would_pass_the_site_s_own_checker(lang):
    """The same rules the blog is held to: no guarantee, no harm predicted at anybody.

    THE PROSE, NOT THE WHOLE PAGE. The twelve card labels carry the Hinglish rashi names on purpose -
    "kanya rashi 2027" is 50,000 searches a month and that is the entire reason those pages are
    titled the way they are - and the language check refuses Latin words in a Devanagari page. That
    rule is right for written prose and wrong for a deliberate keyword term, so this reads the intro
    and the answers rather than the whole document."""
    from app.blog import safety
    from app.web import pages as web_pages

    copy = web_pages.content(lang).PAGES["rashifal-year-hub"]
    prose = " ".join([web_pages.fill(copy.intro, year=str(YEAR)),
                      *[web_pages.fill(answer, year=str(YEAR)) for _q, answer in copy.faqs]])
    assert not safety.blocking_terms(prose, lang=lang), prose[:200]


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_the_transit_table_names_the_grahas_in_devanagari(lang):
    """"Guru" is not a keyword term, unlike the rashi card labels - it is just an untranslated word."""
    html = client.get(i18n.url_for("rashifal-year-hub", lang, year=YEAR)).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    assert "गुरु" in body or "गुरू" in body
    assert "शनि" in body or "शनी" in body
