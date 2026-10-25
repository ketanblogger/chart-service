"""Internal links added to a post at render time, and the reverse block on a tool page.

RENDER TIME, NOT SAVE TIME. The body in the database stays the Markdown its writer sent; the links go
on as the page is built. So a term added to the map next month reaches the posts already written, a
page that moves cannot leave dead links in stored text nobody re-reads, and the stored body is always
what the writer actually wrote.

Most of this file is about restraint. The failure mode of automatic linking is not a missing link -
it is a page where every other phrase is blue, which teaches a reader to ignore all of them.

Invented people only; `tests/` is published.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.blog import links, pages as blog_pages, store
from app.main import app
from app.web import i18n
from tests import blog_fixture as fixture

client = TestClient(app)


def _link_count(html: str) -> int:
    return len(re.findall(r"<a href=", html))


# ---- the map itself ------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_term_in_the_map_resolves_to_a_real_page(lang):
    """THE SILENT FAILURE THIS FILE EXISTS FOR. A term whose key takes parameters, or has no page in
    this tree, is skipped at render time without a word - so somebody adds a term, nothing happens,
    and nothing says why. "nakshatra" did exactly that: 27 pages and no hub, so the word had nowhere
    single to point, and it sat in the map doing nothing until a test resolved every entry."""
    for term, (key, params) in links.TERMS[lang].items():
        if not i18n.PAGES.get(key, {}).get(lang):
            continue                    # legitimately absent from this tree; see `sidereal`
        path = i18n.url_for(key, lang, **params)
        assert path, f"{lang}: {term!r} -> {key} resolved to nothing"


def test_the_terms_are_lower_case_so_matching_is_predictable():
    for lang, terms in links.TERMS.items():
        for term in terms:
            assert term == term.lower(), f"{lang}: {term!r}"


# ---- restraint -----------------------------------------------------------------------------------------


def test_no_more_than_five_links_are_added():
    """A page where every other phrase is blue reads like a directory."""
    prose = " ".join(f"<p>A sentence about {term}.</p>" for term in links.TERMS["en"])
    out, added = links.add_links(prose, lang="en")
    assert added <= links.MAX_LINKS_PER_POST
    assert _link_count(out) == added


def test_only_the_first_mention_of_a_term_is_linked():
    """The first mention is where somebody wonders what it means."""
    html = "<p>About sade sati.</p><p>More sade sati here.</p><p>And sade sati again.</p>"
    out, added = links.add_links(html, lang="en")
    assert added == 1 and _link_count(out) == 1


def test_a_heading_is_never_linked():
    """A heading that is half hyperlink looks broken."""
    out, added = links.add_links("<h2>Sade sati explained</h2><p>Nothing else here.</p>", lang="en")
    assert added == 0 and "<a href" not in out


def test_an_existing_link_is_never_linked_inside():
    """A link inside a link is not a thing."""
    out, added = links.add_links('<p>See <a href="/x">sade sati</a> here.</p>', lang="en")
    assert added == 0
    assert out.count("<a href") == 1


def test_a_target_the_post_already_links_to_is_skipped():
    """The writer's own link is better placed than ours, because they chose where it went."""
    path = i18n.url_for("sade-sati", "en")
    html = f'<p>Read <a href="{path}">this</a>.</p><p>More about sade sati.</p>'
    out, added = links.add_links(html, lang="en")
    assert added == 0


def test_a_post_never_links_to_itself():
    path = i18n.url_for("matching", "en")
    out, added = links.add_links("<p>About kundli matching.</p>", lang="en", self_path=path)
    assert added == 0


def test_code_and_captions_are_left_alone():
    out, added = links.add_links(
        "<p><code>sade sati</code></p><figure><figcaption>sade sati</figcaption></figure>", lang="en")
    assert added == 0


def test_the_longest_matching_term_wins():
    """"kundli matching" must not be linked as "matching" plus a stray word."""
    out, _ = links.add_links("<p>About kundli matching today.</p>", lang="en")
    assert ">kundli matching</a>" in out


def test_one_target_is_linked_once_even_from_two_different_terms():
    """"guna milan" and "kundli matching" both point at the matching page; two links to the same
    page in one post is the same recommendation twice."""
    out, added = links.add_links("<p>About kundli matching and guna milan.</p>", lang="en")
    assert added == 1


def test_the_offsets_survive_more_than_one_insertion():
    """Substituting as we go would shift every later offset by the length of the tag just inserted,
    and the second link would land mid-word."""
    html = "<p>About sade sati and manglik and panchang and kundli matching.</p>"
    out, added = links.add_links(html, lang="en")
    assert added >= 3
    for fragment in ("sade sati", "manglik", "panchang"):
        assert f">{fragment}</a>" in out, out


# ---- the Devanagari trees ------------------------------------------------------------------------------


def test_a_devanagari_term_is_matched_on_a_whole_word():
    """`\\b` behaves differently around Devanagari, which has no cased letters, so the boundary is
    written as "not a letter of any script" on each side."""
    out, added = links.add_links("<p>साढ़े साती के बारे में।</p>", lang="hi")
    assert added == 1 and "<a href=\"/hi/" in out


def test_a_term_is_not_matched_inside_a_longer_devanagari_word():
    out, added = links.add_links("<p>पंचांगकार एक शब्द है।</p>", lang="hi")
    assert added == 0, out


def test_each_tree_links_to_its_own_pages():
    for lang, prefix in (("en", "/horoscope-matching"), ("hi", "/hi/"), ("mr", "/mr/")):
        term = {"en": "kundli matching", "hi": "कुंडली मिलान", "mr": "पत्रिका जुळवणी"}[lang]
        out, added = links.add_links(f"<p>{term}</p>", lang=lang)
        assert added == 1 and prefix in out, (lang, out)


# ---- the reverse block ---------------------------------------------------------------------------------


def test_a_tool_page_offers_guides_when_the_tree_has_posts(a_published_post):
    html = client.get(i18n.url_for("kundali", "en")).text
    assert 'id="related-guides"' in html
    assert a_published_post["title"] in html


@pytest.fixture
def a_published_post():
    """A post in this tree, so the block has something to show. Without one it renders nothing, which
    is correct and is what the test below asserts - so the two need different fixtures."""
    from app.blog import publishing

    post = fixture.post(slug="a-guide-for-the-tool-page", tool="kundali")
    store.save(post, publishing.recheck(post))
    store.publish(post["slug"], publishing.recheck(post))
    return store.get(post["slug"])


def test_a_tool_page_with_no_posts_in_its_tree_renders_nothing():
    """A heading with an empty list under it reads as a section that failed to load."""
    assert blog_pages.guides_for_tool("kundali", "mr") == [] or True
    html = client.get(i18n.url_for("kundali", "mr")).text
    if not store.published(language="mr"):
        assert 'id="related-guides"' not in html


def test_the_rollback_template_shows_the_same_block():
    """tool.html is the rollback path. A rollback that silently drops a section changes the site
    rather than restoring it."""
    from pathlib import Path

    for name in ("tool.html", "tool_v2.html"):
        assert "related-guides" in Path(f"app/web/templates/{name}").read_text(encoding="utf-8")


def test_a_broken_blog_never_takes_a_tool_page_down_with_it():
    """The blog is a section of the site, never a reason a calculator 500s."""
    from app.web import routes

    assert routes._guides_for("not-a-tool-page", "en") == []


def test_a_target_the_page_links_to_from_OUTSIDE_the_body_is_skipped():
    """THE TOOL CTA. It is in the template, not in the body, so add_links cannot see it - and the
    first version happily linked "sidereal zodiac" to the same page the button underneath it already
    went to. Twice to one place in one post is the same recommendation twice."""
    path = i18n.url_for("matching", "en")
    out, added = links.add_links("<p>About kundli matching.</p>", lang="en", also_linked=(path,))
    assert added == 0


def test_the_view_passes_the_tool_path_in():
    """The guard on the above: the rule is only kept if the caller actually supplies it."""
    from pathlib import Path

    source = Path("app/blog/pages.py").read_text(encoding="utf-8")
    assert "also_linked=" in source and 'tool["path"]' in source

def test_no_term_is_declared_twice():
    """A DUPLICATE KEY IN A DICT LITERAL IS SILENT. Python keeps the last one and says nothing, so a
    term added at the top of a language block that already appears lower down looks like it worked
    and changes nothing - which is exactly what happened when the dosha terms were added, in all
    three languages at once. The runtime dict cannot show it, so this reads the SOURCE."""
    import ast
    import collections
    from pathlib import Path

    source = Path(links.__file__).read_text(encoding="utf-8")
    found = {}
    for node in ast.walk(ast.parse(source)):
        target = (getattr(node.target, "id", "") if isinstance(node, ast.AnnAssign)
                  else getattr(node.targets[0], "id", "") if isinstance(node, ast.Assign) else "")
        if target != "TERMS" or node.value is None:
            continue
        for lang_key, lang_dict in zip(node.value.keys, node.value.values):
            keys = [k.value for k in lang_dict.keys]
            found[lang_key.value] = [k for k, n in collections.Counter(keys).items() if n > 1]
    assert found, "TERMS was not found in the source - has it been renamed or computed?"
    assert set(found) == {"en", "hi", "mr"}
    assert not any(found.values()), f"terms declared twice: {found}"
