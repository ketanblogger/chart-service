"""The mantra pages: the release gate, the SEO contract, and the PDF.

THE GATE IS THE MOST IMPORTANT THING HERE. A text goes live on its release date and not before, so
these tests stand on both sides of that date rather than on whatever today happens to be - a suite
that only ever ran after every release date would pass without testing the gate at all.
"""
import datetime as dt
import html
import io
import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app
from app.mantra import texts as T
from app.web import i18n, mantra_copy

BEFORE = T.FIRST_RELEASE - dt.timedelta(days=1)
AFTER = T.FIRST_RELEASE + dt.timedelta(days=60)
EXPLAINERS = pathlib.Path(__file__).resolve().parents[1] / "app/mantra/explainers"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture
def released(monkeypatch):
    """Stand on a morning after every release date."""
    monkeypatch.setattr(T, "today", lambda: AFTER)
    return AFTER


@pytest.fixture
def unreleased(monkeypatch):
    monkeypatch.setattr(T, "today", lambda: BEFORE)
    return BEFORE


def dev_paths(lang="hi"):
    return [(text, i18n.url_for("mantra", lang, slug=text.slug))
            for text in T.PHASE_1 if text.release]


# --------------------------------------------------------------------------- the gate

@pytest.mark.parametrize("text, path", dev_paths())
def test_a_page_404s_before_its_release_date(client, unreleased, text, path):
    assert client.get(path).status_code == 404
    assert client.get(f"{path}.pdf").status_code == 404


@pytest.mark.parametrize("text, path", dev_paths())
def test_a_page_answers_on_and_after_its_release_date(client, released, text, path):
    assert client.get(path).status_code == 200


def test_an_unverified_text_never_goes_live(client, released):
    """Vishnu and Lalita Sahasranamam were rejected on review and re-sourced; neither has been read
    since, so neither may answer - on any date."""
    for slug in ("vishnu-sahasranamam", "lalita-sahasranamam"):
        assert T.BY_SLUG[slug].release is None
        assert client.get(i18n.url_for("mantra", "hi", slug=slug)).status_code == 404


def test_an_unsourced_text_has_no_page_at_all(client, released):
    for slug in T.UNSOURCED:
        assert client.get(f"/hi/mantra/{slug}").status_code == 404


def test_the_sitemap_lists_exactly_what_is_live(monkeypatch):
    """Counted at both levels, because they are different numbers.

    A PageRef is one text; the sitemap expands it into one URL per language. Asserting only the
    refs would miss a tree going missing, and asserting only the URLs would hide which.
    """
    from app.web import seo

    for day, texts in ((BEFORE, 0), (T.FIRST_RELEASE, 2), (AFTER, 20)):
        monkeypatch.setattr(T, "today", lambda day=day: day)
        refs = [r for r in i18n.all_pages() if r.key == "mantra"]
        assert len(refs) == texts, f"{day}: {len(refs)} refs, expected {texts}"
        urls = [e for e in seo.sitemap_entries() if "/mantra/" in e["loc"]]
        assert len(urls) == texts * 2, f"{day}: {len(urls)} urls for {texts} texts in 2 languages"


def test_the_hub_lists_only_released_texts(client, monkeypatch):
    monkeypatch.setattr(T, "today", lambda: BEFORE)
    assert 'href="/hi/mantra/' not in client.get("/hi/mantra").text
    monkeypatch.setattr(T, "today", lambda: AFTER)
    body = client.get("/hi/mantra").text
    assert body.count('href="/hi/mantra/') == len(T.live())


def test_a_related_link_never_points_at_an_unreleased_page(client, monkeypatch):
    """A link to a 404 is worse than no link, and the related lists were written before the
    release order was."""
    monkeypatch.setattr(T, "today", lambda: T.FIRST_RELEASE)
    for text in T.live():
        body = client.get(i18n.url_for("mantra", "hi", slug=text.slug)).text
        for href in re.findall(r'href="(/hi/mantra/[a-z-]+)"', body):
            assert client.get(href).status_code == 200, f"{text.slug} -> {href}"


# --------------------------------------------------------------------------- the SEO contract

@pytest.mark.parametrize("lang", ["hi", "en"])
@pytest.mark.parametrize("slug", [t.slug for t in T.PHASE_1 if t.release])
def test_the_primary_keyword_is_in_all_six_places(client, released, lang, slug):
    """Title, H1, URL slug, first hundred words, at least one H2, meta description - the brief's
    six, checked as six rather than assumed from one."""
    text = T.BY_SLUG[slug]
    name = text.names[lang]
    body = client.get(i18n.url_for("mantra", lang, slug=slug)).text
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S).group(1)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S).group(1)
    meta = re.search(r'<meta name="description" content="(.*?)"', body, re.S).group(1)
    h2s = " ".join(re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S))
    prose = re.sub(r"<[^>]+>", " ", body[body.index("<h1"):])
    first_hundred = " ".join(prose.split()[:100])
    assert name in title, f"title: {title}"
    assert name in h1, f"h1: {h1}"
    assert name in h2s, "no H2 carries the name"
    assert name in meta, f"meta: {meta}"
    assert name in first_hundred, "not in the first hundred words"
    # The slug is the name's own words in Latin, which is what makes it the keyword's URL.
    assert slug in i18n.url_for("mantra", lang, slug=slug)
    # IMAGE ALT, THE SEVENTH PLACEMENT - conditional, because these pages carry no content image.
    # The only <img> is the site's brand emblem, whose alt is deliberately empty: it is decorative
    # and site-wide, and writing a text's name into it would describe the wrong thing to a screen
    # reader. So the rule is asserted for content images if any appear, and the assertion below
    # fails the day one is added without an alt that names the text.
    content_images = [tag for tag in re.findall(r"<img[^>]*>", body)
                      if "brand__mark" not in tag]
    for tag in content_images:
        alt = re.search(r'alt="([^"]*)"', tag)
        assert alt and name in alt.group(1), f"content image without the keyword in alt: {tag}"


@pytest.mark.parametrize("lang", ["hi", "en"])
@pytest.mark.parametrize("slug", [t.slug for t in T.PHASE_1 if t.release])
def test_keyword_density_stays_under_the_ceiling(client, released, lang, slug):
    """A CEILING, NOT A BAND, and measured over OUR OWN WRITTEN TEXT rather than the page.

    The verses are the bulk of the page and are not ours to pad or trim, so a density over
    everything would be a property of the scripture's length.

    There used to be a 1% floor as well, and it was the wrong rule. Forcing a one-word Hindi name to
    1% means repeating it 15 to 30 times in 1,500 words, which is the repetition rate search engines
    now read as a signal against a page - so the floor was pushing the prose in the direction the
    ceiling exists to prevent. The proprietor dropped it. What remains is the thing worth asserting:
    the keyword appears where it belongs (the test below) and nowhere near often enough to look
    stuffed.
    """
    from app.mantra import originality

    name = T.BY_SLUG[slug].names[lang]
    data = json.loads((EXPLAINERS / f"{slug}.{lang}.json").read_text(encoding="utf-8"))
    ours = " ".join([data["intro"], data["recitation"], data["tradition"]]
                    + [g["heading"] + " " + g["body"] for g in data["groups"]]
                    + [f["q"] + " " + f["a"] for f in data["faq"]])
    words = originality.words(ours)
    phrase = originality.words(name)
    hits = sum(1 for i in range(len(words) - len(phrase) + 1)
               if words[i:i + len(phrase)] == phrase)
    density = 100.0 * hits * len(phrase) / max(len(words), 1)
    assert density <= 2.0, (
        f"{slug}.{lang}: {density:.2f}% ({hits} mentions of {name!r} in {len(words)} words)")


@pytest.mark.parametrize("lang", ["hi", "en"])
@pytest.mark.parametrize("slug", [t.slug for t in T.PHASE_1 if t.release])
def test_every_page_carries_the_three_schemas(client, released, lang, slug):
    body = client.get(i18n.url_for("mantra", lang, slug=slug)).text
    for schema in ('"Article"', '"BreadcrumbList"', '"FAQPage"'):
        assert schema in body, schema


def test_meta_descriptions_and_intros_are_unique(client, released):
    metas, intros = {}, {}
    for lang in ("hi", "en"):
        for text in T.live():
            body = client.get(i18n.url_for("mantra", lang, slug=text.slug)).text
            meta = re.search(r'<meta name="description" content="(.*?)"', body, re.S).group(1)
            lede = re.search(r'class="hero__sub">(.*?)</p>', body, re.S).group(1)
            assert meta not in metas, f"{text.slug}.{lang} repeats {metas.get(meta)}'s meta"
            assert lede not in intros, f"{text.slug}.{lang} repeats {intros.get(lede)}'s intro"
            metas[meta] = intros[lede] = f"{text.slug}.{lang}"


@pytest.mark.parametrize("lang", ["hi", "en"])
def test_the_eeat_block_credits_the_sources_and_claims_nothing_false(client, released, lang):
    body = client.get(i18n.url_for("mantra", lang, slug="hanuman-chalisa")).text
    text = T.BY_SLUG["hanuman-chalisa"]
    assert mantra_copy.BYLINE[lang] in body
    for source in text.sources:
        assert source.url in body, source.url
    assert text.author in body
    assert i18n.url_for("about", "en") in body
    assert i18n.url_for("disclaimer", "en") in body
    # NEVER A CREDENTIAL WE DO NOT HAVE.
    for invented in ("scholar", "PhD", "Dr.", "acharya", "pandit", "शास्त्री", "आचार्य"):
        assert invented.lower() not in mantra_copy.BYLINE[lang].lower()


# --------------------------------------------------------------------------- the text and the PDF

@pytest.mark.parametrize("slug", [t.slug for t in T.PHASE_1 if t.release])
def test_the_whole_verse_is_on_the_page(client, released, slug):
    """Every pada, in order, not a sample - this is the one thing the reader came for."""
    # UNESCAPED FIRST. One aarti signs itself 'सूर' with ASCII apostrophes, which Jinja renders as
    # &#39; - correct on the page and invisible to a reader, but not the same bytes as the verse.
    # Searching the raw HTML reported the line as missing from a page that displays it perfectly.
    body = html.unescape(client.get(i18n.url_for("mantra", "hi", slug=slug)).text)
    at = 0
    for verse in T.verses(slug):
        found = body.find(verse["text"], at)
        assert found >= 0, f"{slug}: missing or out of order: {verse['text'][:40]}"
        at = found


def test_the_pdf_is_a_pdf_with_real_devanagari(client, released):
    from app.pdf import browser

    response = client.get("/hi/mantra/hanuman-chalisa.pdf")
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    fonts = browser.embedded_fonts(response.content)
    # A PDF WITH NO DEVANAGARI FONT STILL OPENS - every character draws as an empty box. The
    # quoted font families in a <style> block were autoescaped once, which looked like a font
    # problem and was an escaping problem, so the check is on the embedded font and not on
    # whether the file parses.
    assert any("Devanagari" in font for font in fonts), sorted(fonts)
    assert len(PdfReader(io.BytesIO(response.content)).pages) >= 2


@pytest.mark.parametrize("slug", [t.slug for t in T.PHASE_1 if t.release])
def test_no_text_has_a_character_the_fonts_cannot_draw(slug):
    from app.pdf import browser

    body = " ".join(verse["text"] for verse in T.verses(slug))
    assert not browser.uncovered(body), browser.describe_uncovered(body)


@pytest.mark.parametrize("lang", ["hi", "en"])
@pytest.mark.parametrize("slug", [t.slug for t in T.PHASE_1])
def test_every_title_fits_and_carries_a_roman_phrase(lang, slug):
    """Two site-wide rules at once, asserted for texts that are not released yet as well.

    A title must be at most 60 characters, and a Devanagari title must hold a Roman phrase of four
    or more letters so a reader skimming results can tell what the page is. "PDF" does not satisfy
    the second - three letters - which is how the first version of these titles was caught. The
    English name does, and "hanuman chalisa lyrics" in Latin letters is the larger query anyway.

    Checked for all 22 texts and not only the released ones: the two sahasranamams have the longest
    names in the set, and their titles would otherwise first be built on the morning they go live.
    """
    text = T.BY_SLUG[slug]
    name = text.names[lang]
    title = mantra_copy.title(name, text.names["en"], lang)
    assert len(title) <= mantra_copy.TITLE_LIMIT, f"{len(title)}: {title}"
    assert re.search(r"[A-Za-z]{4,}", title), title
    assert name in title, title


@pytest.mark.parametrize("lang", ["hi", "en"])
def test_the_hub_title_follows_the_same_two_rules(lang):
    title = mantra_copy.WORDS[lang]["hub_title"]
    assert len(title) <= mantra_copy.TITLE_LIMIT, f"{len(title)}: {title}"
    assert re.search(r"[A-Za-z]{4,}", title), title
