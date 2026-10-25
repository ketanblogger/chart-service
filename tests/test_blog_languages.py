"""The blog in three trees, and what makes two posts translations of each other.

A POST LIVES IN ONE TREE - the language it was written in. It is not an English page awaiting
translation, so it is never listed on another tree's index and never served at another tree's URL.
app/blog/__init__.py argued for English only and named what would change the answer: "the day there is
Hindi demand and a Hindi writer the registry entry gains 'hi' and this module follows". That is this.

TWO POSTS ARE ALTERNATES BECAUSE THEY SAY SO, through `translation_of`, never because they sit in
different trees with similar titles. A translation keeps its own slug - a Hindi URL spelled like an
English one helps nobody who types it.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.blog import paths, store
from app.main import app

client = TestClient(app)
BODY = ("# Heading\n\nA paragraph long enough to pass the checks, saying something plain about how a "
        "chart is calculated and what the reader can do with it.\n")
OK = {"blocking": [], "warnings": []}


def make(slug: str, language: str, translation_of: str | None = None) -> dict:
    post = store.save({"slug": slug, "title": f"Title for {slug}", "summary": "s" * 80,
                       "body_md": BODY, "tool": "kundali", "categories": [], "hero_image": None,
                       "author": "RashiKundli", "language": language,
                       "translation_of": translation_of}, OK)
    store.publish(slug, OK)
    return post


@pytest.fixture()
def pair():
    make("alternates-en", "en")
    make("alternates-hi", "hi", translation_of="alternates-en")
    return "alternates-en", "alternates-hi"


@pytest.mark.parametrize("lang, path", [("en", "/blog"), ("hi", "/hi/blog"), ("mr", "/mr/blog")])
def test_every_tree_has_an_index(lang, path):
    assert paths.list_path(lang) == path
    assert client.get(path).status_code == 200


def test_a_post_is_served_only_in_its_own_tree(pair):
    english, hindi = pair
    assert client.get(f"/blog/{english}").status_code == 200
    assert client.get(f"/hi/blog/{hindi}").status_code == 200
    # THE WRONG TREE IS A 404, not a redirect: a Hindi page with an English canonical is the one thing
    # hreflang cannot survive.
    assert client.get(f"/blog/{hindi}").status_code == 404
    assert client.get(f"/hi/blog/{english}").status_code == 404


def test_an_index_lists_only_its_own_tree(pair):
    english, hindi = pair
    assert hindi not in client.get("/blog").text, "the English index lists a Hindi post"
    assert english not in client.get("/hi/blog").text, "the Hindi index lists an English post"


def test_translations_link_each_other_in_both_directions(pair):
    english, hindi = pair
    assert [row["slug"] for row in store.translations_of(store.get(english))] == [hindi]
    assert [row["slug"] for row in store.translations_of(store.get(hindi))] == [english]


def test_the_pages_carry_reciprocal_hreflang(pair):
    english, hindi = pair
    english_page = client.get(f"/blog/{english}").text
    hindi_page = client.get(f"/hi/blog/{hindi}").text
    assert f'hreflang="hi" href="' in english_page and f"/hi/blog/{hindi}" in english_page
    assert f'hreflang="en" href="' in hindi_page and f"/blog/{english}" in hindi_page


def test_a_draft_translation_is_never_an_alternate():
    """An hreflang pointing at a 404 is worse than no hreflang."""
    make("draft-group-en", "en")
    store.save({"slug": "draft-group-hi", "title": "Draft title", "summary": "s" * 80,
                "body_md": BODY, "tool": "kundali", "categories": [], "hero_image": None,
                "author": "RashiKundli", "language": "hi",
                "translation_of": "draft-group-en"}, OK)   # saved, never published
    assert store.translations_of(store.get("draft-group-en")) == []


def test_a_post_with_no_language_is_english():
    """Every post written before the column existed, and any caller that never sends the field."""
    post = make("defaults-to-english", "en")
    assert (post.get("language") or "en") == "en"
    assert client.get("/blog/defaults-to-english").status_code == 200


def test_an_unknown_tree_is_refused_by_the_api():
    """A post written into a tree nothing serves would be live and invisible - which reads as a
    publishing bug rather than a typo."""
    from app.blog import api

    with pytest.raises(Exception) as raised:
        api._check_language("de")
    assert "422" in str(raised.value) or "unknown_language" in str(raised.value)


def test_the_media_route_has_no_language():
    """An image is bytes with an id. Three URLs for one file would be three cache entries and three
    ways to write the same link in a post body."""
    assert paths.media_path("abc") == "/blog/media/abc"


def test_the_api_documents_the_field():
    from pathlib import Path

    doc = Path("docs/BLOG_API.md").read_text(encoding="utf-8")
    assert "`language`" in doc and "`translation_of`" in doc
    assert "/hi/blog/{slug}" in doc and "/mr/blog" in doc
