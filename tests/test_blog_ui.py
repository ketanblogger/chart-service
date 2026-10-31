"""The blog's reading page: what it shows, and the two claims it refuses to make.

A POST IS READ BY THOUSANDS OF PEOPLE AND WRITTEN ABOUT NONE OF THEM. That shapes this page more than
any layout decision: the "Key points" box exists only where an author actually wrote takeaways, and
where they did not, the box below it is labelled "What this post covers" and built from the post's own
headings. A heading says what a section is about; a takeaway says what to conclude. Deriving the
second from the first would be the site writing claims nobody wrote.

NOTHING IS COLLAPSED, here as everywhere else on this site - the FAQ in a post body is headings and
paragraphs rendered by app/blog/markdown.py, which is already plain headed Q&A.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.blog import pages, paths, publishing, store
from app.main import app

client = TestClient(app)
POST_TPL = Path("app/web/templates/blog_post.html").read_text(encoding="utf-8")
LIST_TPL = Path("app/web/templates/blog_list.html").read_text(encoding="utf-8")
OK = {"blocking": [], "warnings": []}

BODY = ("An opening paragraph with enough words in it to pass the checks and give the reader "
        "something to read before the first heading arrives.\n\n"
        "## Where the number comes from\n\nText under the first heading, long enough to be a section "
        "rather than a caption, explaining the thing the heading promises.\n\n"
        "## Why two charts disagree\n\nMore text, again long enough to read as a section of a real "
        "post rather than a placeholder standing in for one.\n")


def make(slug: str, *, points=None, categories=("basics",), lang="en") -> dict:
    post = {"slug": slug, "title": f"A post called {slug}", "summary": "s" * 90, "body_md": BODY,
            "tool": "sidereal", "categories": list(categories), "hero_image": None,
            "author": "RashiKundli", "language": lang, "translation_of": None,
            "key_points": list(points or [])}
    store.save(post, publishing.recheck(post))
    store.publish(slug, OK)
    return store.get(slug)


def test_the_body_is_rendered_markup_and_not_escaped_text():
    """THE DEFECT THAT REACHED A SCREENSHOT. Adding ids to the headings ran re.sub over the Markup
    that markdown.render() returns, and re.sub gives back a plain str - so Jinja escaped it and every
    <p> and <h2> appeared on the page as visible text. No unit test of that function would have caught
    it: the string was right, only the template's treatment of it changed."""
    make("markup-check")
    html = client.get("/blog/markup-check").text
    assert "&lt;p&gt;" not in html and "&lt;h2" not in html
    assert '<h2 id="where-the-number-comes-from">' in html


def test_the_contents_links_land_on_real_headings():
    """A contents list whose links go nowhere looks like a broken page rather than a broken slug. The
    id and the link come from one function for exactly that reason."""
    make("contents-check")
    html = client.get("/blog/contents-check").text
    targets = re.findall(r'<a href="#([^"]+)">', html)
    for target in targets:
        if target in ("key-points", "contents-heading"):
            continue
        assert f'id="{target}"' in html, f"#{target} links nowhere"


def test_key_points_appear_only_when_an_author_wrote_them():
    with_points = make("with-points", points=["One thing", "Another thing", "A third thing"])
    without = make("without-points")

    shown = client.get(f"/blog/{with_points['slug']}").text
    assert "Key points" in shown and "One thing" in shown

    plain = client.get(f"/blog/{without['slug']}").text
    assert "Key points" not in plain, "a box of takeaways appeared for a post with none"
    assert "What this post covers" in plain, "the contents box is missing"


def test_the_contents_box_is_labelled_as_contents_and_not_as_takeaways():
    """The honest label. It is built from headings, and a heading is not a conclusion."""
    assert "words.contents" in POST_TPL
    for lang in ("en", "hi", "mr"):
        words = pages.copy_for(lang)
        assert words["contents"] and words["key_points"]
        assert words["contents"] != words["key_points"]


def test_reading_time_is_slower_for_devanagari():
    """The same word count takes longer to read in a denser script. Both are estimates, and the page
    says "min read" rather than promising anything."""
    words = "शब्द " * 400
    assert pages.reading_minutes(words, "hi") > pages.reading_minutes("word " * 400, "en")
    assert pages.reading_minutes("a b", "en") == 1, "a short post must not read as zero minutes"


def test_nothing_on_the_page_is_collapsed():
    """The rule this site holds everywhere: no accordions, no <details>, nothing hidden behind a
    control. The only `hidden` is the share button, which script reveals, and it is not part of the
    reading."""
    for marker in ("<details", "<summary"):
        assert marker not in POST_TPL, f"{marker} in the post template"
        assert marker not in LIST_TPL, f"{marker} in the list template"


def test_every_image_reserves_its_space():
    """Both templates. A card image that decodes late pushes everything under it down, which is the
    layout shift this batch has spent its time removing."""
    for template in (POST_TPL, LIST_TPL):
        for tag in re.findall(r"<img [^>]+>", template):
            assert 'width="' in tag and 'height="' in tag, tag


def test_the_tool_appears_after_the_opening_and_at_the_end():
    """A post that answers a question and then lets the reader leave has done half its job - and a
    reader who already knows what they want should not have to scroll a thousand words to act."""
    assert POST_TPL.count("post.tool") >= 2
    assert POST_TPL.index("post__tool-inline") < POST_TPL.index('class="card post__tool"')


def test_related_posts_prefer_a_shared_category_over_recency():
    """A "related" list that is simply the newest three is a recency list with another label."""
    make("rel-basics-old", categories=("basics",))
    make("rel-kundli-new", categories=("kundli",))
    subject = make("rel-subject", categories=("basics",))
    related = pages._related(subject, "en", limit=3)
    assert related, "no related posts at all"
    assert "basics" in (related[0].get("categories") or []), \
        "the first related post shares no category with the one being read"


def test_the_filter_only_offers_categories_that_have_a_post():
    """A chip that filters to nothing looks broken, and the reader cannot tell it was always empty."""
    make("filter-basics", categories=("basics",))
    shown = [item["key"] for item in pages._filters(store.published("en"))]
    assert "basics" in shown
    assert all(any(key in (post.get("categories") or []) for post in store.published("en"))
               for key in shown)


def test_the_filter_script_is_a_file_and_the_list_works_without_it():
    """`script-src 'self'` blocks inline scripts. And without the file every post is listed and
    nothing is hidden, which is the honest state rather than a control that cannot work."""
    assert "/static/js/blog-filter.js?v=" in LIST_TPL
    assert "<script>" not in LIST_TPL
    # The bare `hidden` ATTRIBUTE, not the substring - `aria-hidden="true"` on the card's image link
    # is a different thing entirely and the first version of this test failed on it.
    cards = LIST_TPL.split('id="blog-cards"')[1].split("</ul>")[0]
    assert not re.search(r"(?<!aria-)\bhidden\b(?!=)", cards), \
        "cards start hidden, so a reader without scripting sees nothing"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_language_has_the_new_copy(lang):
    words = pages.copy_for(lang)
    for key in ("reading_time", "key_points", "contents", "read_next", "tool_text",
                "filter_label", "filter_all", "filter_none"):
        assert words.get(key, "").strip(), f"{lang} is missing {key}"
    assert "{minutes}" in words["reading_time"]


def test_a_post_with_a_translation_offers_it_and_one_without_offers_the_index():
    """THE POPULATION, NOT THE ASSERTION. The site-wide hreflang and switcher guards were green for
    months against a blog table with nothing in it; the first published post broke three of them at
    once, and one of those breaks was a real defect - every post offered /hi/<slug> and /mr/<slug>
    whether or not anybody had written them.

    So this exercises both shapes deliberately: a post that HAS a Hindi translation must offer it, and
    a post that has none must offer the Hindi index rather than a URL that 404s.
    """
    english = make("pair-en", categories=("basics",))
    hindi = {"slug": "pair-hi", "title": "वही लेख, हिन्दी में", "summary": "स" * 90,
             "body_md": BODY, "tool": "sidereal", "categories": ["basics"], "hero_image": None,
             "author": "RashiKundli", "language": "hi", "translation_of": english["slug"],
             "key_points": []}
    store.save(hindi, publishing.recheck(hindi))
    store.publish("pair-hi", OK)
    lonely = make("lonely-en", categories=("basics",))

    paired = client.get("/blog/pair-en").text
    assert '/hi/blog/pair-hi' in paired, "the Hindi translation is not offered anywhere"
    assert re.search(r'<link rel="alternate" hreflang="hi" href="[^"]+/hi/blog/pair-hi">', paired), \
        "the translation is not declared as an alternate"
    assert re.search(r'hreflang="x-default" href="[^"]+/blog/pair-en">', paired), \
        "x-default must name the English member of the group"

    alone = client.get(f"/blog/{lonely['slug']}").text
    assert f'/hi/blog/{lonely["slug"]}' not in alone, "offered a Hindi post nobody wrote"
    assert '<a href="/hi/blog"' in alone, "no Hindi link at all - the switcher must still lead somewhere"
    assert 'rel="alternate"' not in alone, "a post with no translations must claim no alternates"


@pytest.mark.parametrize("lang,prefix", [("en", "/blog/"), ("hi", "/hi/blog/"), ("mr", "/mr/blog/")])
def test_the_article_schema_declares_the_language_the_post_is_written_in(lang, prefix):
    """IT SAID "en" FOR EVERY POST, in every tree. The blog gained Hindi and Marathi trees and this
    line did not move with them, so a Marathi article told Google it was English - and inLanguage is
    one of the few things in a schema block a search engine acts on directly.

    Nothing on the page looked wrong, which is why it survived: the markup is invisible, the <html
    lang> beside it was correct, and only a crawler would ever have noticed the disagreement.
    """
    import json

    slug = f"lang-{lang}"
    post = {"slug": slug, "title": f"A post in {lang}", "summary": "s" * 90, "body_md": BODY,
            "tool": "sidereal", "categories": ["basics"], "hero_image": None,
            "author": "RashiKundli", "language": lang, "translation_of": None, "key_points": []}
    store.save(post, publishing.recheck(post))
    store.publish(slug, OK)

    html = client.get(f"{prefix}{slug}").text
    blocks = [json.loads(m) for m in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    articles = [b for b in blocks if b.get("@type") == "Article"]
    assert articles, "no Article schema on a blog post"
    assert articles[0]["inLanguage"] == lang
    assert f'<html lang="{lang}">' in html, "the page and its schema must agree"


# ---- item 9b: the refinements ----------------------------------------------------------------------

LIST_NOW = Path("app/web/templates/blog_list.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("lang,path", [("en", "/blog"), ("hi", "/hi/blog"), ("mr", "/mr/blog")])
def test_the_index_opens_on_one_paragraph_and_keeps_its_promise_at_the_foot(lang, path):
    """The promise about what this blog will not do is the most important thing on the page, and it
    was the SECOND PARAGRAPH somebody had to get past before reaching a single post. Moved, not
    dropped: at the foot it reads as a standing commitment instead of a hurdle."""
    words = pages.copy_for(lang)
    assert len(words["intro"]) == 1, f"{lang} index still opens on more than one paragraph"
    html = client.get(path).text
    assert words["about_heading"] in html
    assert words["about"][:40] in html, "the promise did not survive the move"


@pytest.mark.parametrize("lang,path", [("en", "/blog"), ("hi", "/hi/blog"), ("mr", "/mr/blog")])
def test_the_tool_cards_are_in_the_readers_own_language(lang, path):
    """THE WHOLE BLOG LISTED ENGLISH TOOL NAMES TO EVERY TREE. "Free birth chart (kundli)
    calculator" was shown to readers who had chosen Hindi or Marathi, because the blog kept its own
    English-only table instead of reading the name the site already holds per language."""
    html = client.get(path).text
    for tool in [paths.tool_link(key, lang) for key in pages.FEATURED_TOOLS]:
        assert tool["label"] in html, (lang, tool["key"])
        if lang != "en":
            assert tool["label"] != pages.paths.TOOLS.get(tool["key"]), \
                f"{tool['key']} is still showing its English name on the {lang} tree"


def test_no_tool_card_shows_an_unfilled_placeholder():
    """The AI astrologer's blurb names the number of free messages, and `raw` copy is raw on purpose.
    Printed unfilled, the index showed a literal "{free_messages}" to every reader."""
    for path in ("/blog", "/hi/blog", "/mr/blog"):
        main = client.get(path).text.split("<main", 1)[-1]
        assert not re.search(r"\{[a-z_]+\}", main), path


def test_the_latest_post_is_featured_once_and_not_repeated_below():
    """A post in both the featured slot and the grid is the same post twice, which reads as a bug."""
    make("feat-newest", categories=("basics",))
    html = client.get("/blog").text
    body = html.split("<main", 1)[-1]
    featured = body.split('class="card featured"', 1)
    assert len(featured) > 1, "no featured post on an index that has posts"
    slug_links = re.findall(r'href="(/blog/[a-z0-9-]+)"', body)
    top = re.search(r'href="(/blog/[a-z0-9-]+)"', featured[1]).group(1)
    assert slug_links.count(top) == 1, f"{top} appears {slug_links.count(top)} times"


def test_every_card_has_a_picture_and_reserves_its_space():
    """A list where some cards have a hero and others do not comes out half-illustrated. The stand-in
    is the same shape as a real hero, so dropping one in later moves nothing on the page."""
    make("no-hero-post")
    body = client.get("/blog").text.split("<main", 1)[-1]
    cards = re.findall(r'<img [^>]*>', body)
    assert cards, "no images on the index at all"
    for tag in cards:
        assert 'width="1200" height="630"' in tag, tag
    assert "blog-placeholder.svg" in body, "a post with no hero got no picture"


def test_the_placeholder_carries_no_text():
    """It is used through <img>, which cannot reach the site's webfont - any text in it would be drawn
    with whatever face the device has, and for Devanagari that is often nothing."""
    svg = Path("app/static/img/blog-placeholder.svg").read_text(encoding="utf-8")
    assert "<text" not in svg and "font-family" not in svg


@pytest.mark.parametrize("lang,prefix", [("en", "/blog/"), ("hi", "/hi/blog/"), ("mr", "/mr/blog/")])
def test_the_post_carries_a_byline_that_names_the_publication_and_the_engine(lang, prefix):
    """NEVER A PERSON'S NAME - the house rule everywhere here. And a post explaining a calculation
    says what did the calculating in the same breath as who published it."""
    slug = f"byline-{lang}"
    post = {"slug": slug, "title": f"Byline post {lang}", "summary": "s" * 90, "body_md": BODY,
            "tool": "sidereal", "categories": ["basics"], "hero_image": None,
            "author": "RashiKundli", "language": lang, "translation_of": None, "key_points": []}
    store.save(post, publishing.recheck(post))
    store.publish(slug, OK)

    words = pages.copy_for(lang)
    html = client.get(f"{prefix}{slug}").text
    assert words["byline"] in html
    assert words["byline_source"] in html
    assert "post__byline" in html

    import json
    blocks = [json.loads(m) for m in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    article = next(b for b in blocks if b.get("@type") == "Article")
    assert article.get("author"), "the Article schema names no author"


def test_the_tool_call_to_action_says_what_the_reader_gets():
    """"Sidereal birth chart calculator" is what the page is CALLED. "Find your Vedic sun sign" is
    what you get for tapping it, and only one of those is a reason to tap."""
    make("cta-post")
    html = client.get("/blog/cta-post").text
    words = pages.copy_for("en")
    assert words["cta"]["sidereal"] in html
    assert "btn--small" in html, "the inline link is not a button"


@pytest.mark.parametrize("lang,prefix", [("en", "/blog/"), ("hi", "/hi/blog/"), ("mr", "/mr/blog/")])
def test_every_tool_a_post_can_name_has_a_call_to_action_in_every_language(lang, prefix):
    """A missing one falls back to a generic phrase rather than printing a key, but a tool a post can
    actually be about should have its own."""
    words = pages.copy_for(lang)
    assert words["cta_fallback"]
    for key in pages.FEATURED_TOOLS:
        assert words["cta"].get(key), f"{lang} has no call to action for {key}"


def test_the_way_back_says_where_it_goes():
    """It used to repeat the blog's own title, which tells a reader what the page is called rather
    than that this link leaves the post."""
    # BOTH POSTS ARE CREATED HERE. The first version asserted "Read next" on a page whose related
    # list depended on whatever other tests had left in the table - a claim about a population it did
    # not establish, which is the mistake this file exists to stop repeating.
    make("back-link-sibling", categories=("basics",))
    make("back-link-post", categories=("basics",))
    html = client.get("/blog/back-link-post").text
    words = pages.copy_for("en")
    assert words["all_posts"] in html, "the way back does not say where it goes"
    assert words["read_next"] in html, "no related posts, though a sibling was published"


def test_the_sitemap_and_the_page_declare_the_same_alternates():
    """GOOGLE READS THE SITEMAP. The page has always got this right - a post's alternates are its
    translation group - but the sitemap built them from the registry, which answers "every language
    this KEY is published in" and so declared /hi/blog/<slug> and /mr/blog/<slug> as alternates of
    posts nobody had translated.

    The two disagreeing is what the smoke check caught, and it is the reason `sitemap_alternates`
    delegates to the same function the page uses instead of reading the group a second time.
    """
    from app.web import seo

    lonely = make("sitemap-lonely", categories=("basics",))
    entries = {item["loc"]: item.get("alternates") or {} for item in seo.sitemap_entries()}
    loc = next(url for url in entries if url.endswith(lonely["path"]))
    assert entries[loc] == {}, f"the sitemap invents alternates for a post with none: {entries[loc]}"

    html = client.get(lonely["path"]).text
    page_links = dict(re.findall(
        r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">', html))
    assert page_links == entries[loc], "page and sitemap disagree about this post's alternates"
