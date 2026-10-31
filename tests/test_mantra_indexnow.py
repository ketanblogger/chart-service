"""IndexNow for the mantra pages: everything live gets announced exactly once.

THE CASE THIS EXISTS FOR IS A DEPLOY THAT LANDS LATE. The timer used to submit the texts whose
release date was today, which is correct only if the pages were deployed before the first release
and the timer ran every morning after it. If the deploy slips past a release date - the deadline was
tight - that morning's pages are live by the gate and were never announced, because the machine that
would have announced them did not have them yet. The pages would sit uncrawled and nothing would
say so.
"""
import datetime as dt

import pytest

from app.mantra import submitted, texts as T
from app.web import i18n


@pytest.fixture(autouse=True)
def _own_database(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))


def urls_for(text):
    return [i18n.url_for("mantra", lang, slug=text.slug) for lang in ("hi", "en")]


def test_nothing_is_outstanding_before_the_first_release():
    assert submitted.outstanding(T.FIRST_RELEASE - dt.timedelta(days=1)) == []


def test_the_first_morning_owes_exactly_that_morning_s_urls():
    day = T.FIRST_RELEASE
    expected = sorted(url for text in T.released_on(day) for url in urls_for(text))
    assert sorted(submitted.outstanding(day)) == expected
    assert len(expected) == 4, "two texts, two languages"


def test_recording_makes_them_no_longer_outstanding():
    day = T.FIRST_RELEASE
    owed = submitted.outstanding(day)
    assert submitted.record(owed, day=day) == len(owed)
    assert submitted.outstanding(day) == []


def test_recording_twice_sends_nothing_twice():
    """The timer may run twice in a day, and a re-run must not re-announce."""
    day = T.FIRST_RELEASE
    owed = submitted.outstanding(day)
    submitted.record(owed, day=day)
    assert submitted.record(owed, day=day) == 0
    assert submitted.outstanding(day) == []


def test_a_deploy_that_lands_late_still_announces_the_pages_it_missed():
    """THE WHOLE POINT. Deploy on the 14th, four release mornings already past: all eight texts are
    live and none was announced. The old question - what was released today? - returns two texts and
    silently abandons the other six."""
    late = T.FIRST_RELEASE + dt.timedelta(days=4)
    owed = submitted.outstanding(late)
    live = T.live(late)
    assert len(live) == 10, f"{len(live)} live on the fifth morning"
    assert sorted(owed) == sorted(url for text in live for url in urls_for(text))
    assert len(owed) == 20
    # And what released_on alone would have found that morning:
    assert len(T.released_on(late)) == 2


def test_each_following_morning_owes_only_its_own_two_texts():
    day = T.FIRST_RELEASE
    submitted.record(submitted.outstanding(day), day=day)
    nxt = day + dt.timedelta(days=1)
    owed = submitted.outstanding(nxt)
    assert sorted(owed) == sorted(url for text in T.released_on(nxt) for url in urls_for(text))
    assert len(owed) == 4


def test_an_unscheduled_text_is_never_owed():
    """The two sahasranamams are re-sourced and unverified; neither may be announced on any date."""
    far = T.FIRST_RELEASE + dt.timedelta(days=400)
    owed = submitted.outstanding(far)
    for slug in ("vishnu-sahasranamam", "lalita-sahasranamam", *T.UNSOURCED):
        assert not any(slug in url for url in owed), slug


def test_a_refused_submission_is_not_recorded():
    """`submit` returns sent=0 off production and on a refusal. Recording that would mean the URLs
    were never announced and never would be - the catch-up exists to prevent exactly that."""
    from app.web import indexnow

    day = T.FIRST_RELEASE
    result = indexnow.submit_mantra_release(day)
    assert result.get("sent") == 0, "this environment is not production, so nothing is sent"
    assert "recorded" not in result
    assert submitted.outstanding(day), "still owed, because nothing went"


def test_the_hubs_are_submitted_every_time_and_never_recorded_as_done():
    """Their listing changes on every release morning, so they are never finished."""
    day = T.FIRST_RELEASE
    submitted.record(submitted.outstanding(day), day=day)
    assert i18n.url_for("mantra-hub", "hi") not in submitted.already()
    assert i18n.url_for("mantra-hub", "en") not in submitted.already()
