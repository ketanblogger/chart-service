from datetime import date, timedelta

import pytest

from app.engine.constants import DASHA_SEQUENCE
from tests.reference_charts import KALAM, NEHRU


@pytest.fixture(scope="module")
def dasha():
    return KALAM.chart()["dasha"]


def test_sequence_follows_vimshottari_order_from_nakshatra_lord(dasha):
    order = [lord for lord, _ in DASHA_SEQUENCE]
    lords = [m["lord"]["key"] for m in dasha["mahadashas"]]
    assert lords[0] == "Saturn"  # Anuradha is ruled by Saturn
    start = order.index("Saturn")
    assert lords == order[start:] + order[:start]
    assert sum(m["years"] for m in dasha["mahadashas"]) == 120


def test_periods_are_contiguous_and_span_120_years(dasha):
    mahadashas = dasha["mahadashas"]
    for previous, following in zip(mahadashas, mahadashas[1:]):
        assert previous["end"] == following["start"]
    first, last = date.fromisoformat(mahadashas[0]["start"]), date.fromisoformat(mahadashas[-1]["end"])
    assert abs((last - first) - timedelta(days=120 * 365.25)) <= timedelta(days=1)


def test_antardashas_tile_each_mahadasha(dasha):
    for index, maha in enumerate(dasha["mahadashas"]):
        subs = maha["antardashas"]
        assert subs[-1]["end"] == maha["end"]
        for previous, following in zip(subs, subs[1:]):
            assert previous["end"] == following["start"]
        if index > 0:
            assert len(subs) == 9
            assert subs[0]["start"] == maha["start"]
            assert subs[0]["lord"] == maha["lord"]  # each mahadasha opens with its own antardasha


def test_birth_falls_in_first_mahadasha_with_matching_balance(dasha):
    first = dasha["mahadashas"][0]
    born = KALAM.born.isoformat()
    assert first["start"] < born < first["end"]
    assert first["antardashas"][0]["end"] > born  # sub-periods finished before birth are dropped
    balance = dasha["balance_at_birth"]
    assert balance["lord"]["key"] == "Saturn"
    remaining = (date.fromisoformat(first["end"]) - KALAM.born).days / 365.25
    assert balance["decimal_years"] == pytest.approx(remaining, abs=0.01)


def test_current_period_contains_as_of(dasha):
    current = dasha["current"]
    assert current["mahadasha"]["lord"]["key"] == "Jupiter"
    assert current["mahadasha"]["start"] <= dasha["as_of"] < current["mahadasha"]["end"]
    assert current["antardasha"]["start"] <= dasha["as_of"] < current["antardasha"]["end"]
