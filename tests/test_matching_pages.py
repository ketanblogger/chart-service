"""The matching pages, which rank for the highest-value query on the site.

WHAT WAS ALREADY THERE. Matching by name works end to end - name to syllable to nakshatra to a full
Ashtakoota guna milan, with a confidence and the alternative readings of the name - and all three trees
already carried six or more sections and six or more FAQs. That was checked before anything was written,
and the by-name flow was not rebuilt.

WHAT WAS ACTUALLY WRONG. The English title was 80 characters and the Marathi 82, so both were cut off in
the search result for the query they exist to win; the metas were 212, 186 and 167 against a limit of
about 160. And the eight kootas and their thirty-six points - the thing a reader comes for - were laid out
as PROSE AND A BULLET LIST, so the points could not be counted at a glance or lifted into a search result.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n, pages

client = TestClient(app, raise_server_exceptions=False)

PATHS = [(i18n.url_for("matching", lang), lang) for lang in i18n.LANGS]


@pytest.mark.parametrize("path, lang", PATHS)
def test_the_title_fits_a_search_result(path, lang):
    title = pages.get("matching", lang).title
    assert len(title) <= 65, f"{lang}: {len(title)} chars - {title}"


@pytest.mark.parametrize("path, lang", PATHS)
def test_the_meta_description_fits_under_it(path, lang):
    meta = pages.get("matching", lang).meta_description
    assert len(meta) <= 170, f"{lang}: {len(meta)} chars"


@pytest.mark.parametrize("path, lang", PATHS)
def test_the_eight_kootas_and_their_points_are_a_table(path, lang):
    """A reader checking a guna milan score wants to count the points. Prose cannot be counted."""
    html = client.get(path).text
    table = re.search(r'<table class="copy-table">(.*?)</table>', html, re.S)
    assert table, f"{lang}: no koota table"
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(1), re.S)
    assert len(rows) == 10, f"{lang}: {len(rows)} rows - eight kootas, a header and a total"


@pytest.mark.parametrize("path, lang", PATHS)
def test_the_points_in_the_table_add_up_to_thirty_six(path, lang):
    """The whole score is 36. A table whose rows do not sum to it is wrong in the one way a reader of this
    page would notice, and it is the sort of thing that survives a translation unchecked."""
    html = client.get(path).text
    table = re.search(r'<table class="copy-table">(.*?)</table>', html, re.S).group(1)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)[1:]  # drop the header
    points = [int(m.group(1)) for row in rows
              for m in [re.search(r"<td>(\d+)</td>", row)] if m]
    assert len(points) == 9, (lang, points)       # eight kootas and the total row
    assert sum(points[:-1]) == 36 == points[-1], (lang, points, sum(points[:-1]))


@pytest.mark.parametrize("path, lang", PATHS)
def test_the_table_uses_the_styles_the_site_already_has(path, lang):
    """The stylesheet tints a header row only inside a thead, and three columns of Devanagari overflow a
    phone without .table-wrap. Reused rather than restyled."""
    html = client.get(path).text
    section = html[html.index('<table class="copy-table">') - 400:]
    assert "table-wrap" in section[:500] and "<thead>" in section[:900], lang


# ---- by name: the part that already worked, pinned so it keeps working -------------------------------

def test_matching_by_name_still_returns_a_full_guna_milan():
    """Names only - no birth date, no time, no place - through to all eight kootas and a verdict."""
    answer = client.post("/api/matching", json={"mode": "name",
                                                "boy": {"name": "Rohit"}, "girl": {"name": "Sneha"}})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert len(body["kootas"]) == 8, body["kootas"]
    assert body["max_total"] == 36 and 0 <= body["total"] <= 36
    assert body["verdict"] and body["basis"]


def test_by_name_says_what_it_read_the_name_as():
    """A name gives a syllable, a syllable gives a nakshatra, and the reader has to be able to see that
    chain - and that it is a reading, not their chart."""
    body = client.post("/api/matching", json={"mode": "name",
                                              "boy": {"name": "Rohit"},
                                              "girl": {"name": "Sneha"}}).json()
    for side in ("boy", "girl"):
        match = body[side]["name_match"]
        assert match["read_as"] and match["syllable"] and match["confidence"]


@pytest.mark.parametrize("path, lang", PATHS)
def test_the_page_offers_both_ways_in(path, lang):
    html = client.get(path).text
    assert 'id="by-name"' in html, f"{lang}: no by-name entry"
    assert 'data-endpoint="/api/matching"' in html, f"{lang}: no birth-details form"


@pytest.mark.parametrize("path, lang", PATHS)
def test_the_page_is_honest_that_a_name_is_weaker_than_a_birth_chart(path, lang):
    """By-name matching uses one syllable. Saying so is the difference between a free tool and a trick."""
    html = client.get(path).text
    assert 'id="name-note"' in html or 'id="about-by-name"' in html, lang
