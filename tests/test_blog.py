"""The blog's public pages, its Markdown subset and its publication checks.

Three things this file is mostly about, and the first two are the reason it exists:

1. **The Markdown renderer is a security boundary.** A post body arrives over an HTTP API from a
   separate codebase, and app/blog/blog_post.html is the only template on this site that prints markup
   built from text we did not write. So the escaping, the link allowlist and the image allowlist are
   each asserted by feeding the renderer the attack and checking what comes out - never by reading the
   code and agreeing with it.
2. **Every check fails when its subject is broken.** Each test below takes the one clean post in
   tests/blog_fixture.py, breaks exactly one thing, and asserts the single problem that follows. A
   checker nobody has watched fail is a checker that may not be running.
3. The pages themselves: a draft is a 404, a published post carries its Article data and its visible
   date, and the one link that must never be missing - to the tool the post is about - is there.

Invented content only. The fixture post is about the ayanamsa, which belongs to nobody.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.blog import markdown, paths, publishing, safety, store
from app.main import app
from app.web import i18n
from tests import blog_fixture as fixture

client = TestClient(app)


def _publish(**overrides) -> dict:
    """Store the fixture post and put it live, the way /admin/blog would."""
    post = fixture.post(**overrides)
    store.save(post, publishing.recheck(post))
    return publishing.go_live(post["slug"], actor="test")["post"]


# ---- 1. the deliberate decisions ---------------------------------------------------------------------


def test_the_blog_exists_in_three_trees_and_english_is_the_default():
    """IT WAS ENGLISH-ONLY, and that was a decision rather than an omission - app/blog/__init__.py
    argued it at length and named exactly what would change the answer: "the day there is Hindi demand
    and a Hindi writer the registry entry gains 'hi' and this module follows."

    Both halves happened, so the decision is reversed here rather than the assertion deleted. What has
    NOT changed is that a post lives in one tree: these are the trees a post MAY be written in, never a
    promise that any post exists in all of them.
    """
    assert paths.LANGS == ("en", "hi", "mr")
    assert paths.LANG == "en", "English is still the default for a post that does not say"
    if paths.registered():
        assert set(i18n.page_langs(paths.LIST_KEY)) == {"en", "hi", "mr"}
        assert set(i18n.page_langs(paths.POST_KEY)) == {"en", "hi", "mr"}


def test_every_tool_a_post_may_link_to_has_an_english_page():
    """`paths.TOOLS` names registry keys, and a key that stops resolving would render a post with a
    broken link to a tool - which tests/test_seo.py would then fail on, two files away from the cause."""
    missing = [key for key in paths.TOOLS if paths._tool_path(key) is None]
    assert not missing, f"these tool keys have no English path in the URL registry: {missing}"
    assert set(paths.tool_keys()) == set(paths.TOOLS)
    for key in paths.tool_keys():
        link = paths.tool_link(key)
        assert link["path"] == i18n.url_for(key, "en") and link["label"]


def test_the_registry_entries_are_wired_completely_if_they_are_wired_at_all():
    """A HALF-WIRED REGISTRY MUST FAIL HERE, not in the sitemap.

    `app/blog/paths.py` reads `i18n.PAGES` directly, so the pages serve whether or not the registry
    carries them. The sitemap and the language switcher go through `url_for`, which has to learn to fill
    a `{slug}` before it can answer for a post - so a registry entry added WITHOUT that line would leave
    /blog serving happily while tests/test_seo.py broke. This is where that is noticed.
    """
    if paths.LIST_KEY in i18n.PAGES:
        assert i18n.url_for(paths.LIST_KEY, "en") == paths.list_path()
    if paths.POST_KEY in i18n.PAGES:
        slug = "a-post-that-does-not-exist"
        assert i18n.url_for(paths.POST_KEY, "en", slug=slug) == paths.post_path(slug), (
            "the blog-post registry entry is present but url_for cannot fill its {slug}: add "
            '`_PARAMS["blog-post"] = ("slug",)` and the slug line in url_for (app/blog/paths.py)')
        # NOT asserted: that `i18n.resolve()` knows a post's path. `_REVERSE` is built once, at import,
        # so a post published afterwards is in `all_paths()` and not in the reverse table. Nothing here
        # depends on it - the post routes are registered explicitly, and `resolve()` is used for legacy
        # redirects and for an error page's language, where "en" is already the right answer.


def test_media_can_never_be_read_as_a_post_slug():
    """Two guards on one collision, from both directions: the route order and the reserved list."""
    assert not paths.is_slug("media")
    assert "media" in paths.RESERVED_SLUGS
    # The ORDER inside the blog's own router is what decides, because FastAPI matches in registration
    # order. (`app.routes` holds included routers rather than flattened routes in this FastAPI version,
    # so asking the router itself is both simpler and the thing that actually matters.)
    from app.blog import pages as blog_pages

    # One media route, and a post route PER TREE - so the media route must come before the first of
    # them, not before a single one named "blog-post".
    names = [route.name for route in blog_pages.router.routes]
    first_post = min(index for index, name in enumerate(names) if name.startswith("blog-post"))
    assert names.index("blog-media") < first_post, (
        "the media route must be registered before the post route, or /blog/media/<id> is a slug")
    assert client.get(paths.post_path("media")).status_code == 404      # and the live app agrees


# ---- 2. the Markdown subset, fed the attacks ---------------------------------------------------------


@pytest.mark.parametrize("body", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    'Text with <a href="x" onmouseover="alert(1)">a tag</a>',
    "<style>body{display:none}</style>",
    "<!-- a comment --> and text",
    '<iframe src="https://evil.invalid"></iframe>',
    "<svg><use href='#x'/></svg>",
])
def test_the_renderer_never_emits_a_tag_it_did_not_write(body):
    """ESCAPED FIRST, in full, before a single construct is recognised - so no character from the body
    can become part of a tag name or an attribute name.

    The assertion is about TAGS and not about substrings: `onerror=alert(1)` survives inside
    `&lt;img src=x onerror=alert(1)&gt;` as the visible text the writer typed, which is exactly right.
    What must never survive is a `<` that opens an element, so every tag in the output has to be one of
    the handful this renderer writes itself.
    """
    html = str(markdown.render(body)[0])
    assert "&lt;" in html                                   # the writer's own angle brackets, inert
    emitted = set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", html))
    assert emitted <= {"p", "h2", "h3", "ul", "ol", "li", "blockquote", "hr", "strong", "em", "code",
                       "a", "img"}, emitted


@pytest.mark.parametrize("href, expected", [
    ("javascript:alert%281%29", "not allowed"),
    ("JaVaScRiPt:void0", "not allowed"),
    ("data:text/html;base64,PHNjcmlwdD4=", "not allowed"),
    ("mailto:someone@example.invalid", "not allowed"),
    ("vbscript:msgbox", "not allowed"),
    # A PROTOCOL-RELATIVE URL. It starts with a slash and is another site entirely; the first version of
    # this renderer read it as a path and let it straight through, which is why it has its own message.
    ("//evil.invalid/path", "starts with //"),
])
def test_a_link_target_outside_the_allowlist_is_refused_and_rendered_as_text(href, expected):
    html, problems = markdown.render(f"Read [this thing]({href}) now.")
    assert problems and expected in problems[0], problems
    assert href not in str(html) and "<a " not in str(html)
    assert "this thing" in str(html)            # the words survive; only the link is gone


def test_a_target_the_link_pattern_cannot_even_match_is_inert():
    """`javascript:alert(1)` has brackets in it, so it is not a link to this renderer at all and the
    whole construct stays as text. Asserted rather than assumed: "it does not match the pattern" is only
    a defence if what is left over is harmless."""
    html = str(markdown.render("Read [this thing](javascript:alert(1)) now.")[0])
    assert "<a " not in html and "javascript" in html


def test_a_link_inside_the_allowlist_is_a_link():
    html, problems = markdown.render(
        "A path [here](/birth-chart), an anchor [there](#section) and an [outside page](https://example.org).")
    assert not problems
    assert '<a href="/birth-chart">here</a>' in str(html)
    assert '<a href="#section">there</a>' in str(html)
    # An outbound link the writer chose carries no endorsement and no handle on our window.
    assert 'rel="nofollow ugc noopener"' in str(html) and 'target="_blank"' in str(html)


def test_only_an_image_we_host_may_appear_in_a_post():
    """The site's own Content-Security-Policy allows `img-src 'self'`, so a remote image would render as
    a broken box. Refusing it when the post arrives tells the writer; allowing it shows the reader a hole."""
    html, problems = markdown.render("![A chart](https://cdn.example.invalid/chart.png)")
    assert problems and "not hosted here" in problems[0]
    assert "cdn.example.invalid" not in str(html)

    ours = paths.media_path("a" * 32)
    html, problems = markdown.render(f"![A chart wheel]({ours})")
    assert not problems and f'<img src="{ours}" alt="A chart wheel"' in str(html)


def test_an_image_without_alt_text_is_reported():
    _, problems = markdown.render(f"![]({paths.media_path('b' * 32)})")
    assert problems and "no alt text" in problems[0]


def test_a_second_h1_in_the_body_is_refused():
    """tests/test_pages_i18n.py asserts exactly one H1 on every indexable page, and the post's one H1 is
    its title. Demoting a stray one silently would publish a heading the writer did not ask for."""
    _, problems = markdown.render("# Another title\n\nSome prose.")
    assert problems and "one H1 is its title" in problems[0]


def test_the_supported_constructs_all_render():
    html, problems = markdown.render(
        "## A heading\n\n### Under it\n\nA **bold** word, an *italic* one and `some code`.\n\n"
        "- first\n- second\n\n1. one\n2. two\n\n> a quotation\n\n---\n\nA final paragraph.")
    text = str(html)
    assert not problems
    for fragment in ("<h2>A heading</h2>", "<h3>Under it</h3>", "<strong>bold</strong>",
                     "<em>italic</em>", "<code>some code</code>", "<ul>", "<li>first</li>",
                     "<ol>", "<li>one</li>", "<blockquote><p>a quotation</p></blockquote>", "<hr>"):
        assert fragment in text, fragment
    assert text.count("<ul>") == 1 and text.count("<ol>") == 1   # consecutive bullets are ONE list


def test_inline_markup_inside_a_code_span_is_left_alone():
    html, _ = markdown.render("Write `**not bold**` like this.")
    assert "<code>**not bold**</code>" in str(html) and "<strong>" not in str(html)


def test_plain_text_is_what_the_reader_sees():
    """The safety screens run on this, not on the raw body: `app/ai/safety.py` measures how close two
    words sit within one sentence, and a URL between them would push them apart in the raw Markdown."""
    assert markdown.plain_text("A [linked phrase](/x) and **bold**.") == "A linked phrase and bold."
    assert markdown.plain_text("## Heading\n\n- a point") == "Heading\n\na point"


# ---- 3. the checks, each one broken on purpose -------------------------------------------------------


def test_the_fixture_post_passes_every_check():
    """The control. Without this, every test below could be passing for the wrong reason."""
    report = safety.check(fixture.post())
    assert report["blocking"] == [] and report["warnings"] == []


@pytest.mark.parametrize("overrides, expected", [
    # THE SUMMARY'S LENGTH IS HERE AND THE TITLE'S IS NOT, which looks arbitrary until you look at
    # what each feeds: tests/test_pages_i18n.py asserts every page on this site has a meta
    # description between 50 and 230 characters, so a short summary is a red suite and a published
    # page breaking a site-wide invariant. Nothing asserts a title length.
    ({"summary": "Too short to be a meta description."}, "the summary is 35 characters"),
    ({"body_md": "Only a handful of words in this body."}, "words; a post needs at least"),
    ({"slug": "Not A Slug"}, "is not a usable slug"),
    ({"slug": "media"}, "is not a usable slug"),
])
def test_a_structural_problem_blocks_the_post(overrides, expected):
    blocking = safety.check(fixture.post(**overrides))["blocking"]
    assert any(expected in problem for problem in blocking), (expected, blocking)


@pytest.mark.parametrize("overrides, expected", [
    ({"title": "Short"}, "the title is 5 characters"),
    ({"tool": "not-a-tool"}, "`tool` is 'not-a-tool'"),
    ({"tool": "dosha-guide"}, "`tool` is 'dosha-guide'"),          # Hindi-only: no English path
    ({"categories": ["astrology-stuff"]}, "unknown category"),
])
def test_a_structural_problem_that_only_degrades_the_page_is_recorded(overrides, expected):
    """A short title is a worse page in a search result; an unknown tool key means the post renders
    without its call to action. Neither is a broken page, so neither holds the post back - but both
    are written down, because somebody reading /admin/blog should see them."""
    report = safety.check(fixture.post(**overrides))
    assert not any(expected in problem for problem in report["blocking"]), report["blocking"]
    assert any(expected in problem for problem in report["warnings"]), report["warnings"]


#: WHAT STILL STOPS A POST. Only what breaks the site or the law - the proprietor's rule, written
#: down here because this list IS the policy and a reader of this file should not have to infer it.
STOPS_A_POST = [
    ("You will suffer a serious illness after March.", "a prediction that the reader will come to harm"),
    # Harm predicted WITHOUT naming the reader - for a family, or for people with a placement.
    ("This period can bring a serious illness to the family.", "brings harm to people"),
    ("People with this placement often face a serious illness.", "brings harm to people"),
    ("Your father may face a heart attack this year.", "a prediction that the reader will come to harm"),
    ("Without this stone the transit is harsher.", "forbidden topic (gem_fear)"),
    ("The result is guaranteed for every chart.", "a guarantee"),
    ("This transit will definitely improve matters.", "certainty about the future"),
    ("This mantra cures the problem at its root.", "is a medical claim"),
    ("It can heal a chronic condition over time.", "a promise to heal or treat a condition"),
    ("Try this instead of a doctor when it flares up.", "go without medical care"),
    ("You must perform a puja before the transit ends.", "a remedy is offered, never required"),
    ("You must book a puja with a priest or the dosha will ruin the marriage.",
     "a remedy is offered, never required"),
    ("The price is {price_kundali} for the full report.", "unfilled template placeholder"),
    ("Here is some <b>markup</b> in the prose.", "is HTML, and HTML is not accepted"),
]

#: RECORDED AND PUBLISHED. Each of these used to stop a post. They are warnings now: a post held
#: back for a phrasing nobody would notice costs a person's evening, and an astrology blog that
#: cannot use the word divorce is not an astrology blog. Where a repair rule exists the phrasing is
#: rewritten before anybody sees it; what reaches the check is what no rule matched.
RECORDED_ONLY = [
    ("A divorce is common under this transit.", "forbidden topic (catastrophe)"),
    ("Wear a blue sapphire for this placement.", "forbidden topic (gemstone)"),
    ("You will get married once Jupiter moves.", "it cannot predict one reader's life"),
    ("Your chart shows Saturn in the seventh house.", "this post has not seen anybody's chart"),
    ("You will win your case in the second hearing.", "a legal outcome"),
    ("These are guaranteed returns from the period.", "a financial promise"),
]


@pytest.mark.parametrize("sentence, expected", STOPS_A_POST)
def test_a_sentence_that_breaks_the_site_or_the_law_blocks_the_post(sentence, expected):
    """One sentence added to an otherwise clean post, and the one problem that follows. Added to the
    BODY, so the body's own word count and the rest of the post stay valid."""
    broken = fixture.post(body_md=fixture.BODY + "\n\n" + sentence)
    blocking = safety.check(broken)["blocking"]
    assert any(expected in problem for problem in blocking), (expected, blocking)
    # and the clean post does NOT produce it, so the rule is firing on the sentence and not the post
    assert not any(expected in problem for problem in safety.check(fixture.post())["blocking"])


@pytest.mark.parametrize("sentence, expected", RECORDED_ONLY)
def test_a_sentence_that_is_merely_wrong_is_recorded_and_published(sentence, expected):
    """It must be WRITTEN DOWN, which is the half of this that still matters. A warning nobody
    records is the same as no rule at all, and these are the sentences somebody will want to find
    later when a post reads oddly."""
    post = fixture.post(body_md=fixture.BODY + "\n\n" + sentence)
    report = safety.check(post)
    assert not any(expected in problem for problem in report["blocking"]), \
        f"{expected!r} should no longer stop a post"
    assert any(expected in problem for problem in report["warnings"]), \
        f"{expected!r} is not even recorded"


def test_a_dated_promise_about_the_reader_is_blocked_although_neither_half_is():
    """The check is per SENTENCE: a "will" about the reader TOGETHER WITH a date. Each half alone is
    ordinary writing, which is why the rule is written this way rather than as two word lists."""
    halves = ("You will find the dates in the table below.", "Saturn enters Pisces in 2027.")
    for half in halves:
        clean = safety.check(fixture.post(body_md=fixture.BODY + "\n\n" + half))
        assert not any("dates the reader's future" in problem for problem in clean["blocking"]), half
    together = fixture.post(body_md=fixture.BODY + "\n\nYou will see the change by March 2027.")
    assert any("dates the reader's future" in problem
               for problem in safety.check(together)["blocking"])


def test_a_devanagari_body_is_blocked_because_the_blog_is_english():
    """A Hindi post is not a defect in the writing; it is a post for a tree that does not exist yet.
    Publishing it would put Devanagari under an English canonical with no hreflang to anywhere."""
    hindi = "यह पूरा लेख हिंदी में लिखा गया है और इसका अंग्रेज़ी पेड़ पर कोई स्थान नहीं है। " * 40
    blocking = safety.check(fixture.post(body_md=hindi))["blocking"]
    assert any("not in English" in problem for problem in blocking), blocking


def test_a_broken_internal_link_is_repaired_rather_than_blocking():
    """THE INVARIANT IS THE SAME; WHAT KEEPS IT CHANGED. tests/test_seo.py crawls every internal href
    on an indexed page and asserts a direct 200, so a typo'd path in a published post fails the suite
    after a merge. That used to be held by refusing the post.

    It is held by the REPAIR now: the link is dropped and its words are kept, so a published post
    cannot carry one. The check still reports it, as a warning, because what reaches the check after
    the repair is worth knowing about.
    """
    from app.blog import autofix

    text = fixture.BODY + "\n\nSee the [chart tool](/birth-charts) for this."
    report = safety.check(fixture.post(body_md=text), known_slugs={})
    assert not report["blocking"], "a broken link should no longer stop a post"
    assert any("/birth-charts" in problem for problem in report["warnings"]), report["warnings"]

    # and the repair is what makes that safe: the path goes, the sentence stays.
    repaired, fixes = autofix.deterministic(text)
    assert "/birth-charts" not in repaired
    assert "chart tool" in repaired, "the writer's words went with the link"
    assert fixes
    assert not safety.check(fixture.post(body_md=repaired), known_slugs={})["warnings"]

    good = fixture.post(body_md=fixture.BODY + "\n\nSee the [chart tool](/birth-chart) for this.")
    assert safety.check(good, known_slugs={})["blocking"] == []

    to_draft = fixture.post(body_md=fixture.BODY + f"\n\nAlso [this]({paths.post_path('other-post')}).")
    report = safety.check(to_draft, known_slugs={"other-post": "draft"})
    assert report["blocking"] == []
    assert any("still a draft" in problem for problem in report["warnings"])


def test_a_duplicate_title_or_description_is_blocking():
    """Every page on this site has its own title and its own description - tests/test_pages_i18n.py
    asserts it site-wide, and two the same is also a duplicate in a search result."""
    taken = {safety._normalise(fixture.TITLE): "an-earlier-post"}
    report = safety.check(fixture.post(slug="a-later-post"), taken_titles=taken)
    assert any("already used by the post 'an-earlier-post'" in problem for problem in report["blocking"])
    # and not against itself
    assert safety.check(fixture.post(), taken_titles={safety._normalise(fixture.TITLE): fixture.SLUG})[
        "blocking"] == []


# ---- 4. the pages ------------------------------------------------------------------------------------


def test_the_list_page_stands_up_with_no_posts_at_all():
    """An index with nothing in it still has to be a page: tests/test_seo.py asserts at least 80 words
    of body text on anything indexed, and a blank page under a heading sends the reader nowhere."""
    response = client.get(paths.list_path())
    assert response.status_code == 200
    main = response.text.split("<main", 1)[1].split("</main>", 1)[0]
    assert len(re.sub(r"<[^>]+>", " ", main).split()) >= 80
    for tool in paths.tool_keys():
        assert f'href="{i18n.url_for(tool, "en")}"' in main, tool


def test_a_draft_is_a_404_and_not_a_hidden_page():
    post = fixture.post()
    store.save(post, publishing.recheck(post))
    assert store.get(post["slug"])["status"] == "draft"
    assert client.get(paths.post_path(post["slug"])).status_code == 404
    # and no preview query string opens it either
    assert client.get(paths.post_path(post["slug"]) + "?draft=1").status_code == 404
    assert post["title"] not in client.get(paths.list_path()).text


def test_a_published_post_carries_its_article_data_its_date_and_its_tool_link():
    import json

    live = _publish()
    response = client.get(live["path"])
    assert response.status_code == 200
    html = response.text

    blocks = [json.loads(block) for block in
              re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]
    article = next(block for block in blocks if block.get("@type") == "Article")
    assert article["headline"] == fixture.TITLE
    assert article["description"] == fixture.SUMMARY
    assert article["inLanguage"] == "en"
    assert article["datePublished"].startswith(live["published_on"])
    assert article["dateModified"]
    assert article["articleSection"] == ["Astrology basics", "Kundli and birth charts"]
    assert any(block.get("@type") == "BreadcrumbList" for block in blocks)

    # the date, visibly - not only in the structured data
    assert "Published" in html and re.search(r"Published \d+ \w+ \d{4}", html)
    # the one link that must never be missing
    assert f'href="{i18n.url_for(fixture.TOOL, "en")}"' in html
    assert 'content="article"' in html                      # og:type
    assert f'<h1>{fixture.TITLE}</h1>' in html
    assert html.count("<h1") == 1


def test_a_published_post_is_canonical_at_its_own_path_and_has_no_hreflang():
    live = _publish()
    html = client.get(live["path"]).text
    assert f'<link rel="canonical" href="{i18n.absolute(live["path"])}">' in html
    assert 'rel="alternate" hreflang' not in html       # English only: a single-language page has no set


def test_the_list_page_shows_a_published_post_and_links_to_it():
    live = _publish()
    html = client.get(paths.list_path()).text
    assert fixture.TITLE in html and f'href="{live["path"]}"' in html
    assert fixture.SUMMARY in html


def test_a_post_whose_tool_key_leaves_the_registry_still_renders():
    """A post is stored with a registry KEY, so if that key ever disappears the page must degrade to no
    link rather than to a 500. Written against a stored row rather than a submission, because the check
    on the way in would have refused this one."""
    live = _publish()
    with __import__("app").db.transaction() as conn:
        conn.execute("UPDATE blog_posts SET tool = ? WHERE slug = ?", ("gone-away", live["slug"]))
    response = client.get(live["path"])
    assert response.status_code == 200
    assert "gone-away" not in response.text


# ---- 5. images ---------------------------------------------------------------------------------------


def test_an_image_is_served_with_the_type_its_bytes_actually_are():
    from app.blog import images

    row = images.save(fixture.PNG_1PX, sent_as="hero.png")
    response = client.get(row["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]
    assert row["id"] in response.headers["content-disposition"]
    assert "hero.png" in store.image(row["id"])["sent_as"]      # recorded for the admin page only


def test_an_unknown_or_malformed_image_id_is_a_404():
    for image_id in ("f" * 32, "not-hex", "../../etc/passwd", "", "a" * 31):
        assert client.get(paths.media_path(image_id)).status_code == 404, image_id


def test_the_same_bytes_twice_are_the_same_image():
    from app.blog import images

    first = images.save(fixture.PNG_1PX)
    second = images.save(fixture.PNG_1PX)
    assert first["id"] == second["id"] and store.image_count() == 1


@pytest.mark.parametrize("data", [
    b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
    b"GIF89a" + b"\x00" * 20,
    b"%PDF-1.4\n%%EOF",
    b"RIFF\x00\x00\x00\x00WAVEfmt ",       # RIFF, but not a WebP
    b"not an image at all",
])
def test_a_file_that_is_not_a_raster_we_accept_is_refused(data):
    """SVG is refused on purpose: it is a document that can carry a script, and served from our own
    origin it would run inside a policy that allows 'self'."""
    from app.blog import images

    with pytest.raises(images.UploadRefused) as refused:
        images.save(data)
    assert refused.value.status == 415


# ---- 6. the sitemap helper, which may run at import time ---------------------------------------------


def test_published_slugs_never_creates_a_database(tmp_path, monkeypatch):
    """`app/web/i18n.py` builds its reverse table at import, so the moment the blog joins that walk this
    function runs during `import app.main` - before any test has pointed APP_DB anywhere. It must answer
    "no posts" for a database that is not there rather than create one."""
    missing = tmp_path / "not-created" / "app.db"
    monkeypatch.setenv("APP_DB", str(missing))
    assert store.published_slugs() == ()
    assert not missing.exists() and not missing.parent.exists()


def test_published_slugs_lists_what_is_live_and_nothing_else():
    draft = fixture.post(slug="a-draft-post", title="A draft post about houses",
                         summary=fixture.SUMMARY.replace("one number", "first number"))
    store.save(draft, publishing.recheck(draft))
    live = _publish()
    # (slug, language) now: the sitemap lists a post in the tree it was WRITTEN in, so the language
    # has to travel with the slug or every post would be listed under all three.
    assert store.published_slugs() == ((live["slug"], "en"),)
