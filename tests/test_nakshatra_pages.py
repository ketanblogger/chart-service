"""The twenty-seven nakshatra pages, in three trees: 81 pages, written once, no AI on the path.

The checks that matter here are the boring structural ones - that all 27 exist in all three languages,
that the facts agree with the engine rather than being retyped beside it, and that the gandmool section
appears on exactly the six nakshatras it applies to and nowhere else.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.engine.constants import nakshatra_info
from app.main import app
from app.web import i18n
from app.web.nakshatra_data import BY_KEY, GANDMOOL, NAKSHATRAS
from app.web.nakshatra_pages import FRAME

client = TestClient(app)
LANGS = ("en", "hi", "mr")


def test_there_are_exactly_twenty_seven():
    assert len(NAKSHATRAS) == 27
    assert len({n.index for n in NAKSHATRAS}) == 27
    assert [n.index for n in NAKSHATRAS] == list(range(1, 28))


def test_every_name_agrees_with_the_engine():
    """The engine owns the names. A second list that drifts from it is how a page ends up titled
    "Purva Ashadha" while the chart calls it "Purvashadha"."""
    for nakshatra in NAKSHATRAS:
        assert nakshatra_info(nakshatra.index - 1)["name"] == nakshatra.key, nakshatra.key


@pytest.mark.parametrize("lang", LANGS)
def test_all_twenty_seven_pages_serve_in_every_language(lang):
    for nakshatra in NAKSHATRAS:
        path = i18n.url_for("nakshatra", lang, nakshatra=nakshatra.key)
        response = client.get(path)
        assert response.status_code == 200, path
        body = re.sub(r"<[^>]+>", " ", response.text.split("<main", 1)[1].split("</main>", 1)[0])
        assert len(body.split()) > 150, f"{path}: {len(body.split())} words is a stub"


@pytest.mark.parametrize("lang", LANGS)
def test_the_meaning_is_present_and_specific_to_that_nakshatra(lang):
    """A page whose only specific content is its title is a doorway page."""
    from app.web.nakshatra_pages import _meaning

    seen = set()
    for nakshatra in NAKSHATRAS:
        text = _meaning(nakshatra.key, lang)
        assert len(text.split()) >= 20, (lang, nakshatra.key)
        assert text not in seen, f"{lang}: {nakshatra.key} repeats another nakshatra's paragraph"
        seen.add(text)


@pytest.mark.parametrize("lang", LANGS)
def test_gandmool_appears_on_exactly_the_six_and_nowhere_else(lang):
    """Six nakshatras sit at the elemental junctions. Showing the warning on a seventh would frighten
    somebody for no reason; omitting it on one of the six would leave out what tradition asks for."""
    assert len(GANDMOOL) == 6
    assert set(GANDMOOL) == {"Ashwini", "Ashlesha", "Magha", "Jyeshtha", "Mula", "Revati"}
    for nakshatra in NAKSHATRAS:
        html = client.get(i18n.url_for("nakshatra", lang, nakshatra=nakshatra.key)).text
        shown = 'id="gandmool"' in html
        assert shown == nakshatra.gandmool, f"{lang} {nakshatra.key}: gandmool section shown={shown}"


@pytest.mark.parametrize("lang", LANGS)
def test_the_gandmool_section_refuses_to_frighten(lang):
    """It is the most reliable way to scare a new parent, so the page says plainly that it is a
    junction rather than a defect and that anybody selling a remedy against it is selling fear."""
    html = client.get(i18n.url_for("nakshatra", lang, nakshatra="Mula")).text
    section = re.sub(r"<[^>]+>", " ", html.split('id="gandmool"', 1)[1].split("</section>", 1)[0])
    assert len(section.split()) > 50
    needles = {"en": ["junction", "not a defect", "selling fear"],
               "hi": ["संधि", "शापित नहीं", "डर बेच"],
               "mr": ["संधी", "शापित नाही", "भीती विकतो"]}[lang]
    for needle in needles:
        assert needle in section, f"{lang}: the gandmool section does not say {needle!r}"


@pytest.mark.parametrize("lang", LANGS)
def test_every_page_links_to_the_tool_that_finds_your_nakshatra(lang):
    html = client.get(i18n.url_for("nakshatra", lang, nakshatra="Rohini")).text
    assert f'href="{i18n.url_for("kundali", lang)}"' in html


@pytest.mark.parametrize("lang", LANGS)
def test_the_pages_link_to_each_other(lang):
    """81 pages that link nowhere are 81 orphans - which is exactly how the last batch's new families
    ended up in "Discovered - currently not indexed"."""
    html = client.get(i18n.url_for("nakshatra", lang, nakshatra="Ashwini")).text
    # SCOPED TO THE LIST. Searching the whole document finds 27, because the page's own canonical link
    # in <head> carries its own URL - which is not a link to itself from the body.
    listing = html.split('id="all"', 1)[1].split("</section>", 1)[0]
    links = [n for n in NAKSHATRAS
             if f'href="{i18n.url_for("nakshatra", lang, nakshatra=n.key)}"' in listing]
    assert len(links) == 26, f"{lang}: links to {len(links)} of the other 26"
    assert i18n.url_for("nakshatra", lang, nakshatra="Ashwini") not in listing, "it lists itself"


def test_the_frame_is_complete_in_every_language():
    keys = {lang: set(words) for lang, words in FRAME.items()}
    assert set(FRAME) == set(LANGS)
    assert keys["en"] == keys["hi"] == keys["mr"]
    for lang, words in FRAME.items():
        assert len(words["ordinals"]) == 27, lang
        assert set(words["ganas"]) == {"deva", "manushya", "rakshasa"}, lang


def test_the_ganas_split_nine_nine_nine():
    """Traditionally exactly nine of each. A split that is not 9/9/9 means a typo in the table."""
    counts = {gana: sum(1 for n in NAKSHATRAS if n.gana == gana)
              for gana in ("deva", "manushya", "rakshasa")}
    assert counts == {"deva": 9, "manushya": 9, "rakshasa": 9}, counts


def test_every_nakshatra_has_a_deity_and_a_symbol():
    for nakshatra in NAKSHATRAS:
        assert nakshatra.deity.strip() and nakshatra.symbol.strip(), nakshatra.key
        assert BY_KEY[nakshatra.key] is nakshatra
