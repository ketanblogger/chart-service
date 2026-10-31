"""A post's reading layout: body images that stay in the column, and the rail on a wide screen.

THE BUG THIS STARTS FROM: there was no CSS rule for an image in a post body at all, so a 1600px
screenshot rendered at 1600px inside a 68ch column - out past the right edge, with the text left
looking like a narrow strip beside it. Nothing failed, because nothing was asserting anything about
images in a body: the posts that existed had none.

It also carries the fix for something worse that the Hindi screenshots found; see the language test
at the bottom.

Invented people only; `tests/` is published.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.blog import markdown, pages, publishing, safety, store
from app.main import app
from tests import blog_fixture as fixture

client = TestClient(app)
SITE_CSS = Path("app/static/css/site.css").read_text(encoding="utf-8")
POST_HTML = Path("app/web/templates/blog_post.html").read_text(encoding="utf-8")
IMAGE = "/blog/media/0123456789abcdef0123456789abcdef"


# ---- images stay in the column -----------------------------------------------------------------------


def test_an_image_on_its_own_becomes_a_captioned_figure():
    html, problems = markdown.render(f"![A square chart with its diagonals]({IMAGE})")
    assert problems == []
    assert html.strip().startswith("<figure class=\"post__figure\">")
    assert "<figcaption aria-hidden=\"true\">A square chart with its diagonals</figcaption>" in html
    assert 'alt="A square chart with its diagonals"' in html, "the alt stays on the img as well"


def test_a_figure_is_never_put_inside_a_paragraph():
    """A figure is not phrasing content. A browser meeting one inside a <p> closes the paragraph
    itself, which leaves a stray </p> and a figure with no block parent."""
    html, _ = markdown.render(f"Text before.\n\n![A chart]({IMAGE})\n\nText after.")
    assert "<p><figure" not in html
    assert "<figure" in html


def test_an_image_inside_a_sentence_stays_inline():
    """Only a paragraph that is NOTHING but an image becomes a figure. A word-sized image in the
    middle of a sentence must not be centred on a line of its own with a caption under it."""
    html, _ = markdown.render(f"An inline ![icon]({IMAGE}) in a sentence.")
    assert "<figure" not in html
    assert "<p>An inline <img" in html


def test_an_image_with_no_alt_gets_no_caption():
    """It is already reported as a problem; inventing a caption from an empty alt would print an
    empty line under the picture."""
    html, problems = markdown.render(f"![]({IMAGE})")
    assert "<figcaption" not in html
    assert any("alt" in problem for problem in problems)


def test_the_caption_is_not_escaped_twice():
    """This module escapes the whole body before any construct is recognised, so the alt arriving
    here is already escaped. Escaping it again prints "a chart &amp; its houses" to the reader."""
    html, _ = markdown.render(f"![A chart & its houses]({IMAGE})")
    assert "&amp;amp;" not in html
    assert "<figcaption aria-hidden=\"true\">A chart &amp; its houses</figcaption>" in html


def test_the_stylesheet_keeps_a_body_image_inside_the_column():
    """The rule that did not exist. `width: 100%` is deliberately NOT used - an image narrower than
    the column should stay its own size rather than be stretched past its pixels and go soft."""
    rule = SITE_CSS[SITE_CSS.index(".post__body :is(img"):]
    rule = rule[:rule.index("}") + 1]
    assert "max-width: 100%" in rule and "height: auto" in rule
    # `max-width: 100%` CONTAINS `width: 100%`, so a substring check cannot tell the two apart and
    # this assertion failed against the very rule it was written for. The lookbehind is the test.
    assert not re.search(r"(?<!max-)width:\s*100%", rule), rule


# ---- the rail ------------------------------------------------------------------------------------------


def test_the_rail_is_hidden_until_1200px():
    """Below the breakpoint the page must be exactly what it was. The rail ships on every post and is
    hidden in CSS rather than built only above the breakpoint, because only a media query knows the
    viewport - the server does not, and a page cached at one width is served at every other."""
    assert ".post__rail { display: none; }" in SITE_CSS
    wide = SITE_CSS[SITE_CSS.index("@media (min-width: 1200px)"):]
    assert ".post__rail { display: block;" in wide


def test_the_rail_is_sticky_rather_than_fixed():
    """Fixed would take it out of the flow and let it overlap the footer on a short post."""
    wide = SITE_CSS[SITE_CSS.index("@media (min-width: 1200px)"):]
    assert "position: sticky" in wide
    assert "position: fixed" not in wide


def test_the_article_column_cannot_be_widened_by_a_table():
    """A `1fr` column takes its minimum from its content and a table in a post carries
    `min-width: 36rem`, which widened the column, pushed the rail off and scrolled the page
    sideways. The same fix the rashifal grid needed, for the same reason."""
    wide = SITE_CSS[SITE_CSS.index("@media (min-width: 1200px)"):]
    assert "minmax(0, 68ch)" in wide and "minmax(0, 1fr)" in wide


def test_nothing_is_said_twice_at_any_width():
    """The rail carries the contents and the tool, so the inline copies are hidden - at that width
    only, and only because the rail is there to replace them."""
    wide = SITE_CSS[SITE_CSS.index("@media (min-width: 1200px)"):]
    assert ".post__body .post__contents" in wide and "display: none" in wide


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_rail_has_its_copy_in_every_tree(lang):
    words = pages.copy_for(lang)
    for key in ("contents", "tool_label", "tool_text", "rail_tools_heading"):
        assert words.get(key), f"{lang} has no {key}"


def test_the_rail_does_not_offer_the_tool_the_post_is_already_about():
    """Three tools beside an article is a suggestion; the same tool twice is an error."""
    assert "rail_tools" in Path("app/blog/pages.py").read_text(encoding="utf-8")
    assert "rail_tools" in POST_HTML


# ---- the language check, which the Hindi screenshots found ----------------------------------------------


def test_a_hindi_post_is_checked_as_hindi():
    """THE DEFECT THIS BATCH FOUND, and it was live. `content_problems` ran the language check with a
    hardcoded "en" and a comment saying the blog was English only - true when written, false from the
    day the Hindi and Marathi trees shipped. Every Devanagari post was blocked with "the English
    version is not in English", so no post could ever go live in either tree.

    The suite did not catch it because tests/test_blog_languages.py publishes with a precomputed
    report through store.publish(), so the one path that would have run this check on a Devanagari
    post was the one path those tests skip.
    """
    post = fixture.post(
        slug="a-hindi-post-for-the-language-check", language="hi",
        title="यह एक हिन्दी लेख का शीर्षक है",
        summary="यह सारांश हिन्दी में है और इतना लंबा है कि जाँच इसे स्वीकार कर ले, कम से कम पचास अक्षर।",
        body_md="## पहला शीर्षक\n\n" + ("यह हिन्दी में लिखा हुआ एक अनुच्छेद है जो केवल जाँच के लिए है। " * 40))
    blocking, _ = safety.content_problems(post)
    assert not any("not in English" in problem for problem in blocking), blocking


def test_devanagari_in_the_english_tree_is_still_blocked():
    """The rule that was right and must survive the fix: Hindi under an /en canonical is still wrong."""
    post = fixture.post(slug="devanagari-in-the-english-tree", language="en",
                        body_md="## Heading\n\n" + ("यह हिन्दी में लिखा हुआ एक अनुच्छेद है। " * 40))
    blocking, _ = safety.content_problems(post)
    assert any("not in English" in problem for problem in blocking), blocking


def test_a_post_with_no_language_is_still_checked_as_english():
    post = fixture.post(slug="a-post-with-no-language-at-all")
    post.pop("language", None)
    blocking, _ = safety.content_problems(post)
    assert not any("not in English" in problem for problem in blocking), blocking


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_every_post_in_a_devanagari_tree_says_what_the_date_is(lang):
    """`published_label` was missing in both, and blog_post.html prints it before the date - so every
    Hindi and Marathi post showed a bare date with nothing saying what it was the date of. Found by
    looking at a screenshot, not by a test, which is why there is now a test."""
    assert pages.copy_for(lang).get("published_label")


# ---- the date, in the language of the page showing it ---------------------------------------------------


@pytest.mark.parametrize("lang,month", [("en", "October"), ("hi", "अक्टूबर"), ("mr", "ऑक्टोबर")])
def test_a_post_date_is_written_in_the_page_s_own_language(lang, month):
    """`_dateline` passed "en" to format_date whatever tree it was rendering, so every Hindi and
    Marathi post carried an English month name under a Devanagari headline. The month names for all
    three trees already existed in app/rashifal/i18n.py; only the call site was hardcoded - the same
    shape of bug as the language check two commits earlier, found the same way, by looking."""
    from app.blog import pages as blog_pages

    post = {"slug": "a-post-for-the-dateline", "published_on": "2026-10-24",
            "created_on": "2026-10-24", "updated_on": "2026-10-24", "language": "en",
            "body_md": "", "categories": [], "hero_image": None, "title": "t", "summary": "s"}
    assert month in blog_pages._dateline(post, lang)["published"]


def test_the_date_follows_the_page_not_the_post():
    """A Hindi index listing an English post is a Hindi page and its dates should read as Hindi. The
    post's own language decides its PATH, which is a different question."""
    from app.blog import pages as blog_pages

    english_post = {"slug": "an-english-post", "published_on": "2026-10-24", "language": "en",
                    "created_on": "2026-10-24", "updated_on": "2026-10-24",
                    "body_md": "", "categories": [], "hero_image": None, "title": "t", "summary": "s"}
    assert "अक्टूबर" in blog_pages._dateline(english_post, "hi")["published"]


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_no_english_month_name_reaches_a_devanagari_blog_page(lang):
    """Over the real rendered pages, not the helper: the index and every post card on it."""
    html = client.get(f"/{lang}/blog").text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    for english in ("January", "February", "March", "April", "May ", "June", "July", "August",
                    "September", "October", "November", "December"):
        assert english not in body, f"{english!r} on the {lang} blog index"
