"""A birth known to within a window: what that settles, and what it still refuses.

"SOME TIME IN THE MORNING" AND "ABOUT 7:30" ARE DIFFERENT KINDS OF NOT-KNOWING. The no-time module
treats both the same - it checks the whole day and reports only what holds at both ends - and for
somebody who knows the hour to within forty minutes that throws away almost everything, because the
lagna very often does not move at all inside a window that short.

EVERY ANSWER HERE IS CHECKED AGAINST compute_chart(), not against itself. The first version of this
engine reported Karka for a birth whose chart says Vrishabha: sign_info() takes a 0-BASED ordinal and
returns a 1-BASED `index` field, so feeding one back into the other shifts every answer by a sign.
Nothing in the module's own output would have shown that.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.engine import compute_chart
from app.engine.core import parse_tz
from app.engine.time_window import DASHA_MINUTES, MAX_HOURS, lagna_in_window
from app.main import app

PUNE = (18.5204, 73.8567)
DAY = dt.date(1990, 5, 14)
IST = parse_tz("Asia/Kolkata")
client = TestClient(app)


def chart_lagna(moment: dt.datetime) -> str:
    return compute_chart(moment.date(), moment.time(), *PUNE, "Asia/Kolkata")["lagna"]["sign"]["name"]


def test_a_window_inside_one_sign_settles_the_lagna():
    answer = lagna_in_window(DAY, dt.time(7, 0), dt.time(7, 40), *PUNE)
    assert answer["settled"] is True and answer["houses_known"] is True
    assert answer["lagna"]["name"] == chart_lagna(dt.datetime.combine(DAY, dt.time(7, 20), tzinfo=IST))


def test_every_slice_matches_the_real_chart_at_its_midpoint():
    """THE CLAIM EACH SLICE MAKES: a birth anywhere inside it has this lagna. Checked against the
    engine that draws real charts, which is the only thing that can catch an off-by-one in the signs."""
    answer = lagna_in_window(DAY, dt.time(6, 0), dt.time(9, 0), *PUNE)
    assert len(answer["possibilities"]) >= 2, "this window is known to cross a boundary"
    for slice_ in answer["possibilities"]:
        start = dt.datetime.combine(DAY, dt.time.fromisoformat(slice_["from"]), tzinfo=IST)
        end = dt.datetime.combine(DAY, dt.time.fromisoformat(slice_["to"]), tzinfo=IST)
        assert chart_lagna(start + (end - start) / 2) == slice_["sign"]["name"]


def test_the_slices_cover_the_window_and_do_not_overlap():
    answer = lagna_in_window(DAY, dt.time(6, 0), dt.time(9, 0), *PUNE)
    parts = answer["possibilities"]
    assert parts[0]["from"] == "06:00" and parts[-1]["to"] == "09:00"
    for earlier, later in zip(parts, parts[1:]):
        assert earlier["to"] == later["from"], "a gap or an overlap between slices"
    assert sum(part["minutes"] for part in parts) == pytest.approx(180, abs=2)


def test_a_crossing_window_settles_nothing_and_says_so():
    answer = lagna_in_window(DAY, dt.time(6, 0), dt.time(9, 0), *PUNE)
    assert answer["settled"] is False
    assert answer["lagna"] is None, "a lagna was offered for a window that crosses a boundary"
    assert answer["houses_known"] is False, "houses follow the lagna and cannot be more certain than it"


def test_the_dasha_is_refused_until_the_window_is_tight():
    """The Moon moves about a degree every two hours, and the balance at birth sets every date in the
    sequence for a lifetime - minutes at the start become months by the third mahadasha."""
    wide = lagna_in_window(DAY, dt.time(7, 0), dt.time(7, 40), *PUNE)
    assert wide["dasha"]["available"] is False
    assert wide["dasha"]["needs_minutes"] == DASHA_MINUTES
    assert wide["dasha"]["why"], "a refusal with no reason is just a no"

    tight = lagna_in_window(DAY, dt.time(7, 25), dt.time(7, 33), *PUNE)
    assert tight["dasha"]["available"] is True


def test_a_window_too_wide_to_be_useful_is_refused():
    """Past six hours the lagna has crossed three or four signs, and "it is one of these four" is the
    answer the no-time page already gives, with more words."""
    answer = lagna_in_window(DAY, dt.time(1, 0), dt.time(8, 30), *PUNE)
    assert answer.get("error") == "window_too_wide" and answer["max_hours"] == MAX_HOURS


def test_an_end_before_its_start_is_refused():
    assert lagna_in_window(DAY, dt.time(9, 0), dt.time(7, 0), *PUNE).get("error") == "end_before_start"


# ---- through the endpoint -------------------------------------------------------------------------


def test_the_endpoint_answers_exactly_as_before_without_a_window():
    """The window is optional and nothing about the old answer may move."""
    answer = client.post("/api/chart/without-time", json={"date": "1990-05-14", "city": "Pune"}).json()
    assert answer["needs_birth_time"] == ["lagna", "houses", "dasha", "bhava_positions", "mangal_dosha"]
    assert "window" not in answer


@pytest.mark.parametrize("window, still_refused", [
    (("07:00", "07:40"), ["dasha", "mangal_dosha"]),          # settled: lagna and houses are known
    (("07:25", "07:33"), ["mangal_dosha"]),                   # tight: the dasha too
    (("06:00", "09:00"),                                       # crossing: nothing is settled
     ["lagna", "houses", "dasha", "bhava_positions", "mangal_dosha"]),
])
def test_the_refusals_shrink_only_as_far_as_the_window_earns(window, still_refused):
    answer = client.post("/api/chart/without-time", json={
        "date": "1990-05-14", "city": "Pune", "from_time": window[0], "to_time": window[1]}).json()
    assert answer["needs_birth_time"] == still_refused


def test_mangal_dosha_is_never_offered_by_a_window():
    """It needs the houses AND Mars to the degree. A window that settles the lagna does not settle it,
    and the one refusal that must survive every widening of this feature is this one."""
    for window in (("07:00", "07:40"), ("07:25", "07:33")):
        answer = client.post("/api/chart/without-time", json={
            "date": "1990-05-14", "city": "Pune", "from_time": window[0], "to_time": window[1]}).json()
        assert "mangal_dosha" in answer["needs_birth_time"]


def test_half_a_window_is_refused():
    """One end alone is not a window, and guessing the other is the failure this whole module avoids."""
    response = client.post("/api/chart/without-time",
                           json={"date": "1990-05-14", "city": "Pune", "from_time": "07:00"})
    assert response.status_code == 422
