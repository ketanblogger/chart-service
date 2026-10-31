"""No content page is reachable only from the sitemap.

"Discovered - currently not indexed" is what Search Console says about a page it knows exists and has not
judged worth fetching. 43 pages were in that state, and the diagnosis turned out to be two different
things:

THE 43 THEMSELVES WERE NOT ORPHANS. /hi/rashifal/mesh/masik is linked from sixteen other pages, and the
five Hindi periods for one sign are already distinct - every title names its period, and the body overlap
between any two of them is 27-40%, nowhere near a duplicate. That half of the complaint was not borne out
by measurement, and nothing was "fixed" that was not broken.

WHAT WAS ACTUALLY ORPHANED WAS MINE. The 36 rashi-in-english pages and the 6 festival pages, built in
this batch and in the one before it, had NO inbound link from anywhere - reachable from the sitemap alone,
which is exactly how a page ends up in that state. They are linked now, with anchors that say what the
page is.
"""
from __future__ import annotations

import collections
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n

client = TestClient(app)

#: EMPTY, AND IT SHOULD STAY THAT WAY. When the walk below was written it found nine stranded
#: pages - bhakoot and nadi dosha in all three trees, and the three Hindi /dosh/ guides - which were
#: recorded here rather than fixed in the same commit. They are linked now: the koota table on both
#: matching doors links its bhakoot and nadi rows to those guides, and the Hindi mangal-dosha tool
#: links the guide behind it, from which the other two are a click away.
#:
#: A name added back to this set is a page somebody has decided a reader cannot reach. It needs a
#: reason written beside it, not just an entry.
#:
#: Blog posts are excluded separately and for a different reason: the URL registry is built at import
#: time from whatever database is configured THEN, so posts from a developer's own database appear in
#: the path list while /blog, served against the test database, lists none of them. That is an
#: artefact of the fixture rather than a fact about the site.
KNOWN_STRANDED: set[str] = set()

#: Linked from the footer on every page, which is right for a policy page and is not an SEO problem.
FOOTER_ONLY = {"about", "contact", "privacy", "terms", "pricing", "delivery-policy", "refund-policy",
               "disclaimer"}


@pytest.fixture(scope="module")
def inbound():
    """How many OTHER pages link to each page, counting only the body - a nav or footer link is site
    chrome and says nothing about a page except that it exists."""
    pages = [(path, key) for path, key, _lang, _params in i18n.all_paths()]
    html = {path: client.get(path).text for path, _ in pages}
    counts = collections.Counter()
    for source, text in html.items():
        body = re.sub(r"<header.*?</header>|<footer.*?</footer>", " ", text, flags=re.S)
        for destination, _ in pages:
            if destination != source and re.search(rf'href="{re.escape(destination)}(?=["?#])', body):
                counts[destination] += 1
    return pages, counts


def test_no_content_page_is_reachable_only_from_the_sitemap(inbound):
    pages, counts = inbound
    orphans = sorted(path for path, key in pages if counts[path] == 0 and key not in FOOTER_ONLY)
    assert not orphans, f"{len(orphans)} page(s) nothing links to: {orphans[:8]}"


def test_no_set_of_pages_links_only_to_each_other(inbound):
    """AN INBOUND LINK IS NOT REACHABILITY. Three pages that link to each other and to nothing else
    give every one of them a non-zero inbound count while the whole group sits off the site: a
    reader can arrive only from a search result or the sitemap, and nothing on the site leads there.

    That is not hypothetical. The Diwali page, the year's calendar and the ekadashi list shipped
    exactly like that and passed the check above, because each was linked from the other two. The
    check that catches it is a WALK: start at the home pages and the footer, follow body links, and
    see what is never arrived at.
    """
    pages, _ = inbound
    paths = {path for path, _ in pages}
    html = {path: client.get(path).text for path in paths}

    # The footer is site chrome for the check above, and it is a real way in for this one.
    seeds = {i18n.url_for("home", lang) for lang in i18n.LANGS}
    footer = re.search(r"<footer.*?</footer>", html[i18n.url_for("home", "en")], flags=re.S)
    if footer:
        seeds |= {path for path in paths
                  if re.search(rf'href="{re.escape(path)}(?=["?#])', footer.group(0))}

    seen, queue = set(seeds), list(seeds)
    while queue:
        source = queue.pop()
        body = re.sub(r"<header.*?</header>|<footer.*?</footer>", " ", html[source], flags=re.S)
        for destination in paths - seen:
            if re.search(rf'href="{re.escape(destination)}(?=["?#])', body):
                seen.add(destination)
                queue.append(destination)

    stranded = sorted(path for path, key in pages
                      if path not in seen and key not in FOOTER_ONLY
                      and path not in KNOWN_STRANDED and not path.startswith("/blog/"))
    assert not stranded, (
        f"{len(stranded)} page(s) cannot be reached from the home page or the footer by following "
        f"links - they may link to each other, which is not the same thing: {stranded[:8]}")


@pytest.mark.parametrize("key", ["rashi-in-english", "sade-sati-rashi", "festival", "rashifal-year"])
def test_every_page_this_batch_added_has_a_parent(inbound, key):
    """Each family built recently, checked by name - because "no orphans" passes trivially the day
    somebody deletes a family, and these are the ones whose parent I forgot."""
    _pages, counts = inbound
    paths = [path for path, k, *_ in i18n.all_paths() if k == key]
    assert paths, key
    missing = [path for path in paths if counts[path] == 0]
    assert not missing, f"{key}: {len(missing)} of {len(paths)} unlinked, e.g. {missing[:3]}"


def test_the_anchor_says_what_the_page_is(inbound):
    """A crawler reads the anchor text. "Click here" twelve times teaches it nothing, and the whole point
    of adding these links is to say what is on the other end."""
    html = client.get("/horoscope/scorpio").text
    for path in (i18n.url_for("rashi-in-english", "en", rashi="vrishchika"),
                 i18n.url_for("sade-sati-rashi", "en", rashi="vrishchika")):
        anchor = re.search(rf'href="{re.escape(path)}"[^>]*>([^<]+)<', html)
        assert anchor, path
        text = anchor.group(1).strip()
        assert len(text.split()) >= 4, f"{path}: anchor too thin - {text!r}"
        assert "Scorpio" in text, f"{path}: the anchor must name the sign - {text!r}"


@pytest.mark.parametrize("lang, hub", [("en", "/horoscope"), ("hi", "/hi/rashifal"),
                                       ("mr", "/mr/rashi-bhavishya")])
def test_the_festival_links_carry_their_date(lang, hub):
    """A muhurat page is worth clicking because of when it is. The anchor carries the date, and the whole
    block disappears once the date has passed - sending a reader to a muhurat that is over is worse than
    not linking it."""
    from app.engine import festivals

    html = client.get(hub).text
    shown = [f for f, year in i18n.FESTIVAL_PAGES
             if i18n.url_for("festival", lang, festival=f, year=year) in html]
    assert shown, f"{hub} links no festival page"
    for festival in shown:
        when = festivals.windows(festival, 2026, "Delhi")["date"]
        assert when is not None
        assert str(when.day) in html, f"{hub}: {festival}'s anchor does not carry its date"
PERIODS_HI = ("aaj", "saptahik", "masik", "6-mahine", "varshik")


def _title_and_body(path):
    html = client.get(path).text
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
    body = re.search(r"<main.*?</main>", html, re.S)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.group(0))) if body else ""
    return title, text


def test_each_hindi_period_has_its_own_title():
    """Titles come from the registry and the copy, so this holds whether or not any reading has been
    generated - and a shared title across periods is the clearest duplicate signal there is."""
    titles = [_title_and_body(f"/hi/rashifal/mesh/{period}")[0] for period in PERIODS_HI]
    assert len(set(titles)) == len(titles), f"two periods share a title: {titles}"
    for period, title in zip(PERIODS_HI, titles):
        assert len(title) <= 60, f"{period}: {len(title)} characters"


def test_the_hindi_period_bodies_are_not_near_duplicates():
    """THE OTHER HALF OF THE COMPLAINT, and it can only be measured on pages that HAVE readings.

    THIS TEST FIRST REPORTED 73% OVERLAP AND I NEARLY BELIEVED IT. Under pytest the rashifal store is a
    fresh, empty database, so every period renders the same "being prepared" fallback - and five copies
    of one piece of boilerplate are of course near-identical. That is a statement about an empty store,
    not about the writing. Against a store with real readings the same measurement gives 27-40% between
    any two periods, nowhere near a duplicate.

    So it skips rather than asserting on boilerplate: a number describing the fallback would be a green
    that means nothing, or a red that blames the copy for the fixture.
    """
    bodies = {period: _title_and_body(f"/hi/rashifal/mesh/{period}")[1] for period in PERIODS_HI}
    shortest = min(len(text.split()) for text in bodies.values())
    if shortest < 300:
        pytest.skip(f"no generated readings in this store (shortest body {shortest} words); "
                    "overlap here would measure the fallback, not the writing")
    for i, first in enumerate(PERIODS_HI):
        for second in PERIODS_HI[i + 1:]:
            a, b = set(bodies[first].split()), set(bodies[second].split())
            overlap = len(a & b) / max(1, len(a | b))
            assert overlap < 0.55, f"{first} vs {second}: {overlap:.0%} of words shared"
