"""The two doshas a matching result reports, as guides of their own.

WHY THEY EXIST. Nadi carries 8 of the 36 gunas and bhakoot 7, so between them they are where a score
collapses - which is exactly why they are the two a frightened couple is most often sold something
about. "nadi dosh" alone is 50,000 searches a month. These pages say what the configuration is, how
it is identified, where astrologers disagree, and what the tradition actually prescribes, and they
sell nothing, which is the rule the three guides beside them already keep.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n
from app.web.dosha_guides import MATCH_COPY, MATCH_DOSHAS, MATCH_GUIDES

client = TestClient(app)
RENDER_JS = Path("app/static/js/render.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("dosha", MATCH_DOSHAS)
def test_each_guide_exists_in_each_tree(lang, dosha):
    """Unlike the three fear-sold guides beside them, these are in every tree - because a matching
    result exists in every tree, and that is where a reader meets the word."""
    response = client.get(i18n.url_for("match-dosha", lang, dosha=dosha))
    assert response.status_code == 200
    assert MATCH_COPY[lang][dosha]["h1"] in response.text


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("dosha", MATCH_DOSHAS)
def test_the_body_is_paragraphs_and_the_description_is_a_sentence(lang, dosha):
    """THE TEMPLATE TAKES what_body[0] AS THE META DESCRIPTION. The existing guides store a tuple of
    paragraphs, so [0] is the first paragraph; the first version of these stored one string, so [0]
    was the first CHARACTER - and every page shipped a one-letter meta description, two of which
    were then duplicates of each other."""
    words = MATCH_COPY[lang][dosha]
    for key in ("what_body", "how_body", "remedies_body"):
        assert isinstance(words[key], tuple), (lang, dosha, key)
        assert all(isinstance(para, str) and len(para) > 40 for para in words[key]), (lang, dosha, key)
    assert 50 <= len(words["what_body"][0]) <= 230, len(words["what_body"][0])


def test_no_two_guides_share_a_title_or_an_h1():
    """Hindi and Marathi write "भकूट दोष" identically, so the two pages collided site-wide until each
    H1 said which kind of matching it is about."""
    seen: dict[str, str] = {}
    for lang in ("en", "hi", "mr"):
        for dosha in MATCH_DOSHAS:
            for field in ("title", "h1"):
                value = MATCH_COPY[lang][dosha][field]
                assert value not in seen, f"{lang}/{dosha} {field} duplicates {seen.get(value)}"
                seen[value] = f"{lang}/{dosha}"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("dosha", MATCH_DOSHAS)
def test_a_guide_sells_nothing(lang, dosha):
    """The rule the guides beside these already keep: no product, no price, no paid ritual. The
    people most likely to pay for a remedy are the ones least able to afford it."""
    html = client.get(i18n.url_for("match-dosha", lang, dosha=dosha)).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    assert "data-product" not in body, "a buy button on a dosha guide"
    assert "₹" not in body and "Rs " not in body, "a price on a dosha guide"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("dosha", MATCH_DOSHAS)
def test_each_guide_points_at_the_free_check(lang, dosha):
    assert MATCH_GUIDES[dosha].tool == "matching"
    html = client.get(i18n.url_for("match-dosha", lang, dosha=dosha)).text
    assert i18n.url_for("matching", lang) in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_matching_form_carries_the_guide_paths(lang):
    """The result links them, and the paths come from the registry through the FORM - never spelled
    in the script, because each tree spells them differently."""
    html = client.get(i18n.url_for("matching", lang)).text
    assert f'data-dosha-nadi="{i18n.url_for("match-dosha", lang, dosha="nadi")}"' in html
    assert f'data-dosha-bhakoot="{i18n.url_for("match-dosha", lang, dosha="bhakoot")}"' in html


def test_the_result_links_a_guide_only_when_the_dosha_is_present():
    """A link to "what nadi dosha means" under a result that does NOT have one invites a reader to
    worry about something that did not happen to them, which is the trade these pages exist against."""
    import re

    body = RENDER_JS[RENDER_JS.index("function doshaLine"):]
    body = body[:body.index("\n  }")]
    assert "dosha.present && guideHref" in body, body[:300]


def test_the_renderer_does_not_touch_the_dom_where_there_is_none():
    """render.js is executed by py_mini_racer so the PDF and the page can be compared against one
    string of truth, and `document` is undefined there. A bare reference took 50 tests with it once
    before; this one did it again."""
    from py_mini_racer import MiniRacer

    ctx = MiniRacer()
    ctx.eval("var window = this; var document = undefined;")
    ctx.eval(RENDER_JS)
    assert ctx.eval("typeof AstroRender.renderers.matching") == "function"


def test_no_page_path_is_spelled_in_the_script_not_even_in_a_comment():
    """The guard reads this file as TEXT. The comment explaining why paths do not belong here quoted
    one, and failed on itself - the same way a template comment naming the brand did an hour earlier.
    A rule about where a string may live is not suspended for the sentence explaining the rule."""
    for lang in ("en", "hi", "mr"):
        for dosha in MATCH_DOSHAS:
            path = i18n.url_for("match-dosha", lang, dosha=dosha)
            assert path not in RENDER_JS, path


def test_the_koota_table_links_bhakoot_and_nadi_to_their_guides():
    """The two kootas that carry fifteen of the thirty-six points between them are where a score
    collapses, and so are what a frightened couple is most often sold something about. The guide has
    to be a click from the TABLE, not only from a result that happens to report a dosha - until it
    was, six pages were reachable from nothing on the site, "nadi dosh" among them at fifty thousand
    searches a month.

    BY ROW INDEX, because the row is called "Nadi", "नाड़ी" and "नाडी" in the three trees and matching
    on the word would work in exactly one of them.
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n, pages

    client = TestClient(app)
    for lang in i18n.LANGS:
        table = pages.content(lang).KOOT_TABLE
        assert len(table) == 8
        # The order is the contract this link rides on.
        assert table[6][1] == 7 and table[7][1] == 8, f"{lang}: koota order moved"
        for key in ("matching", "gun-milan-name"):
            html = client.get(i18n.url_for(key, lang)).text
            for dosha, index in (("bhakoot", 6), ("nadi", 7)):
                href = i18n.url_for("match-dosha", lang, dosha=dosha)
                assert f'<a href="{href}">{table[index][0]}</a>' in html, (lang, key, dosha)


def test_the_mangal_tool_links_the_long_guide_behind_it():
    """The guides link to the tool and to each other; nothing linked INTO the group, so all three
    Hindi /dosh/ pages were reachable from the sitemap and nowhere else."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    client = TestClient(app)
    guide = i18n.url_for("dosha-guide", "hi", dosha="mangal")
    for query in ("", "?design=v1"):
        # BOTH designs: a rollback that silently drops a section changes the site rather than
        # restoring it, which is what the comment in tool.html says and why both carry the link.
        assert guide in client.get(i18n.url_for("mangal-dosha", "hi") + query).text, query
