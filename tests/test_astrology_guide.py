"""The pillar pages: /astrology, /hi/jyotish, /mr/jyotish.

"ज्योतिष" is 50K a month and the query behind it is not transactional - somebody wants to understand the
thing. The test of a pillar is whether a reader comes away knowing how a chart is put together, so these
check that every major topic is present, that each section is addressable, and that the page links to
the tool that does the thing it just described rather than describing a tool we do not have.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n
from app.web.astrology_guide import GUIDES

client = TestClient(app)
PAGES = [("en", "/astrology"), ("hi", "/hi/jyotish"), ("mr", "/mr/jyotish")]
#: The topics a guide that claims to be complete has to cover.
REQUIRED = ("what-it-is", "sidereal", "grahas", "houses", "nakshatras", "dasha", "doshas",
            "matching", "panchang", "honest")


@pytest.mark.parametrize("lang, path", PAGES)
def test_every_required_topic_is_present_and_addressable(lang, path):
    html = client.get(path).text
    anchors = {part.anchor for part in GUIDES[lang]["parts"]}
    missing = set(REQUIRED) - anchors
    assert not missing, f"{path} does not cover: {sorted(missing)}"
    for anchor in REQUIRED:
        assert f'id="{anchor}"' in html, f"{path}: #{anchor} is not addressable"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_table_of_contents_reaches_every_section(lang, path):
    """A long page with no way into the middle of it is a long page nobody reads the middle of."""
    html = client.get(path).text
    toc = html.split('class="card guide__toc"', 1)[1].split("</nav>", 1)[0]
    for part in GUIDES[lang]["parts"]:
        assert f'href="#{part.anchor}"' in toc, f"{path}: {part.anchor} missing from the contents"
    assert 'href="#faq"' in toc


@pytest.mark.parametrize("lang, path", PAGES)
def test_each_section_has_its_own_h2(lang, path):
    html = client.get(path).text
    for part in GUIDES[lang]["parts"]:
        section = html.split(f'id="{part.anchor}"', 1)[1].split("</section>", 1)[0]
        assert "<h2>" in section, f"{path}: #{part.anchor} has no h2"


@pytest.mark.parametrize("lang, path", PAGES)
def test_it_links_only_to_tools_that_exist_in_this_tree(lang, path):
    """A pillar that links to a page the tree does not have sends readers to a 404 - and the Marathi and
    Hindi trees do not have every English page."""
    html = client.get(path).text
    for part in GUIDES[lang]["parts"]:
        if not part.tool:
            continue
        assert lang in i18n.page_langs(part.tool), f"{path}: links to {part.tool}, absent in {lang}"
        assert f'href="{i18n.url_for(part.tool, lang)}"' in html


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_page_says_what_astrology_is_not(lang, path):
    """The honesty section is the one that must never be quietly dropped for being off-message."""
    html = client.get(path).text
    assert 'id="honest"' in html
    section = html.split('id="honest"', 1)[1].split("</section>", 1)[0]
    assert len(re.sub(r"<[^>]+>", " ", section).split()) > 60


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_sidereal_difference_is_explained_with_the_actual_number(lang, path):
    """"Your Indian sign is different" without "because the zodiacs have drifted about 24 degrees" is
    the half-answer every other site gives."""
    html = client.get(path).text
    section = html.split('id="sidereal"', 1)[1].split("</section>", 1)[0]
    assert "24" in section, f"{path}: the sidereal section does not give the size of the difference"


def test_the_guides_cover_the_same_ground_in_every_language():
    base = {part.anchor for part in GUIDES["en"]["parts"]}
    for lang in ("hi", "mr"):
        anchors = {part.anchor for part in GUIDES[lang]["parts"]}
        assert set(REQUIRED) <= anchors, (lang, set(REQUIRED) - anchors)
        assert anchors <= base, (lang, anchors - base)


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_faq_is_real_and_structured(lang, path):
    html = client.get(path).text
    assert len(GUIDES[lang]["faqs"]) >= 5
    assert "FAQPage" in html, f"{path}: the FAQ is not in the structured data"
