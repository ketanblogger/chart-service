"""Shani, Guru and Rahu-Ketu: one page per slow graha per year.

"jupiter transit 2026" is 50,000 searches a month and the gochar terms 5,000 each. The site has had
these dates all along - they come from the same ephemeris scan the charts use - and nowhere to put
them.

WHAT IS COMPUTED AND WHAT IS WRITTEN. Every date is computed. The sentence under each rashi is about
the HOUSE, written once by hand and reused wherever that house lands, which is why twelve sentences
cover all twelve rashis on all three pages and cannot drift between them.

Invented people only; `tests/` is published.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n
from app.web.gochar_pages import COPY, GRAHA_LABELS, HOUSE_MEANINGS, houses_for, stays_for

client = TestClient(app)
YEAR = 2027


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("slug", ["shani", "guru", "rahu-ketu"])
def test_every_gochar_page_serves(lang, slug):
    response = client.get(i18n.url_for("gochar", lang, graha=slug, year=YEAR))
    assert response.status_code == 200


def test_the_dates_are_the_ones_the_engine_found():
    """Shani enters Mesha in June 2027 and retrogrades back into Meena in October - the example
    year_facts uses in its own docstring."""
    signs = [s["sign"]["name"] for s in stays_for("shani", YEAR)]
    assert signs == ["Meena", "Mesha", "Meena"], signs


def test_rahu_and_ketu_are_always_opposite():
    """They share a page because they are always six signs apart; deriving Ketu from Rahu is exact,
    and scanning it separately would be the same work twice for one addition."""
    stays = stays_for("rahu-ketu", YEAR)
    rahu = [s for s in stays if "Rahu" in str(s["graha"])]
    ketu = [s for s in stays if "Ketu" in str(s["graha"])]
    assert rahu and len(rahu) == len(ketu)
    for one, other in zip(rahu, ketu):
        assert (one["sign"]["index"] - other["sign"]["index"]) % 12 == 6
        assert one["start"] == other["start"] and one["end"] == other["end"]


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_each_page_covers_all_twelve_rashis_and_links_their_year_pages(lang):
    rows = houses_for("shani", YEAR, lang)
    assert len(rows) == 12
    html = client.get(i18n.url_for("gochar", lang, graha="shani", year=YEAR)).text
    for row in rows:
        assert row["spans"], row["rashi"]
        assert f'href="{row["path"]}"' in html, (lang, row["rashi"])


def test_the_house_is_counted_from_each_rashi():
    """Shani in Meena is the twelfth house from Mesha and the first from Meena. The same sky, twelve
    different years."""
    from_mesha = {s["house"] for s in houses_for("shani", YEAR, "en")[0]["spans"]}
    from_meena = {s["house"] for s in houses_for("shani", YEAR, "en")[11]["spans"]}
    assert 12 in from_mesha and 1 in from_mesha
    assert 1 in from_meena and 2 in from_meena


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_there_are_twelve_house_meanings_and_they_are_about_houses(lang):
    assert len(HOUSE_MEANINGS[lang]) == 12
    assert all(text.strip() for text in HOUSE_MEANINGS[lang])


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_nothing_this_page_writes_would_fail_the_site_s_own_checker(lang):
    """No guarantee, nothing that happens TO the reader, no fear, no remedy anybody must buy. These
    are written once and reused on nine pages, so one bad sentence would be on all of them."""
    from app.blog import safety

    # THE PROSE, NOT THE TEMPLATES. The title and H1 carry "{native}", "{english}" and the Roman
    # word "Transit" on purpose - the dual-script decision the Marathi pages were retargeted on -
    # and a raw template is full of placeholder names that are Latin by construction. What is
    # checked is what a reader reads.
    prose = list(HOUSE_MEANINGS[lang]) + [COPY[lang]["lead"], COPY[lang]["note"],
                                          COPY[lang]["kundli_cta"]]
    for text in prose:
        assert not safety.blocking_terms(text, lang=lang), text[:160]


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_a_devanagari_page_names_the_graha_in_devanagari(lang):
    native, _english = GRAHA_LABELS["shani"][lang]
    html = client.get(i18n.url_for("gochar", lang, graha="shani", year=YEAR)).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    assert native in body


@pytest.mark.parametrize("slug", ["shani", "guru", "rahu-ketu"])
def test_the_english_title_carries_both_the_gochar_and_transit_words(slug):
    """"jupiter transit 2026" is the big term and "guru gochar" the smaller one; the page answers
    both rather than choosing."""
    html = client.get(i18n.url_for("gochar", "en", graha=slug, year=YEAR)).text
    title = html.split("<title>", 1)[1].split("</title>", 1)[0].lower()
    assert "gochar" in title and "transit" in title


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("slug", ["shani", "guru", "rahu-ketu"])
def test_no_page_promises_anything_or_sells_a_remedy(lang, slug):
    html = client.get(i18n.url_for("gochar", lang, graha=slug, year=YEAR)).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    assert "₹" not in body
    assert "data-product" not in body
