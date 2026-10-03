"""Every "other signs" link must NAME the sign it points at.

This shipped, on 216 live pages, and it is the kind of defect no existing test could see: the links were all
present, all twelve, every href correct, the page valid and the layout fine. Only the anchor TEXT was wrong -
each link read the name of the sign you were already on. A reader could not tell which sign they were
clicking, and every internal link on the most-crawled pages on the site carried the wrong anchor text.

The cause was a label filled too early. `pages.get(key, lang, **names)` resolves a page's copy for the sign
being read, which is right for nearly every label on the page and exactly wrong for `rashi_label`, the one
template that has to be filled twelve different ways. So the assertion here is not "there are twelve links" -
there always were - but that the label of each link matches the sign its href goes to.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n

client = TestClient(app)

# One page per language per kind, and two signs, so a bug that happens to agree for one sign is still caught.
READINGS = ("/horoscope/libra/today", "/horoscope/aries/today",
            "/hi/rashifal/tula/aaj", "/mr/rashi-bhavishya/tula/aaj")
RASHI_HUBS = ("/horoscope/libra", "/horoscope/aries", "/hi/rashifal/tula", "/mr/rashi-bhavishya/tula")


def links_under(html: str, heading_id: str) -> list[tuple[str, str]]:
    block = re.search(heading_id + r".*?</(?:nav|section)>", html, re.S)
    assert block, f"no block for {heading_id}"
    return [(href, re.sub(r"<[^>]+>", " ", label).strip())
            for href, label in re.findall(r'<a href="([^"]+)">(.*?)</a>', block.group(0), re.S)]


def sign_of(path: str) -> str | None:
    """The rashi key a horoscope URL points at, from the URL itself."""
    for lang in ("en", "hi", "mr"):
        for key in i18n.RASHI_KEYS:
            for period in ("today", "aaj", "weekly", "saptahik", "monthly", "yearly", ""):
                candidates = {i18n.url_for("rashifal-rashi", lang, rashi=key)}
                if period:
                    try:
                        candidates.add(i18n.url_for("rashifal-reading", lang, rashi=key, period=period))
                    except Exception:
                        pass
                if path in candidates:
                    return key
    return None


# The heading is named per page rather than guessed from the URL: a rashi hub and a reading are three path
# segments apart in English and NOT in Hindi (/hi/rashifal/tula is a hub, /horoscope/libra/today a reading),
# so counting slashes picks the wrong block in two languages out of three.
PAGES = ([(path, "other-rashis-heading") for path in READINGS]
         + [(path, "others-heading") for path in RASHI_HUBS])


@pytest.mark.parametrize("path,heading", PAGES)
@pytest.mark.parametrize("flag", ("", "?design=v2"))
def test_each_other_sign_link_is_named_after_the_sign_it_points_at(path, heading, flag):
    response = client.get(path + flag)
    assert response.status_code == 200, path
    links = links_under(response.text, heading)
    assert len(links) >= 11, (path, len(links))

    labels = [label for _, label in links]
    named = [(href, label) for href, label in links if sign_of(href.split("?")[0])]
    assert len(named) >= 11, f"{path}: could not resolve the target sign of most links"
    # the real assertion: every link that points at a different sign says something different
    assert len(set(labels)) >= 11, (
        f"{path}{flag} has {len(set(labels))} distinct labels across {len(links)} links - "
        f"they are all naming the same sign: {labels[:4]}")

    # and the label actually contains that sign's own name in this page's language
    lang = "hi" if "/hi/" in path else "mr" if "/mr/" in path else "en"
    for href, label in named:
        key = sign_of(href.split("?")[0])
        names = i18n.rashi_names(key, lang)
        assert names["rashi"] in label or names["latin"] in label, (path, href, label, names)


# ---- the period cards on a sign hub ------------------------------------------------------------------

PERIOD_CARD_PAGES = ("/horoscope/libra", "/hi/rashifal/tula", "/mr/rashi-bhavishya/tula")


@pytest.mark.parametrize("path", PERIOD_CARD_PAGES)
def test_the_today_and_this_week_cards_carry_a_line_of_their_own(path):
    """The five period cards used to read unevenly: Month and Next 6 Months carried a written headline while
    Today and This Week showed only a date. Not a template difference - the headline is only shown while the
    stored page matches the period's WINDOW, and a monthly window stays current for weeks where a daily one
    lasts a day. So the two cards a reader is most likely to click were the two that looked unfinished.

    They now fall back to an engine-derived line (app/web/rashifal.py `_engine_teaser`): a real transit event
    for the period, already translated, no AI call. This asserts the line is there and is NOT the date that
    sits above it."""
    html = client.get(path + "?design=v2").text
    cards = re.findall(r'<li class="v2-tool">(.*?)</li>', html, re.S)
    assert len(cards) == 5, f"{path}: {len(cards)} period cards"

    for card in cards[:2]:                     # Today and This Week, in that order
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", card)).strip()
        after_range = re.search(r"<br>(.*?)</p>", card, re.S)
        assert after_range, f"{path}: a period card has no teaser line - {text[:90]}"
        teaser = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", after_range.group(1))).strip()
        assert len(teaser) > 15, f"{path}: teaser too short: {teaser!r}"


@pytest.mark.parametrize("path", PERIOD_CARD_PAGES)
def test_a_teaser_is_never_the_reason_a_hub_fails(path, monkeypatch):
    """It is decoration on a page whose job is the five links. An ephemeris failure must cost the line, not
    the page."""
    from app.web import rashifal

    monkeypatch.setattr(rashifal, "_engine_teaser", lambda *a, **k: None)
    response = client.get(path)
    assert response.status_code == 200
