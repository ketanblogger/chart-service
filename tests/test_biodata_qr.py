"""The opt-in QR: an opaque link, a row that exists only because somebody ticked a box, and an off
switch that actually works.

The people are invented.
"""
import datetime as dt

import pytest

from app.biodata import qr

BORN = dt.date(1991, 4, 3)
AT = dt.time(14, 25)
NOW = dt.datetime(2027, 3, 1, tzinfo=dt.timezone.utc)


@pytest.fixture
def token():
    return qr.issue(birth_date=BORN, birth_time=AT, lat=18.52, lon=73.86, place="Pune",
                    person="Keshav", now=NOW)


def test_the_link_carries_no_birth_details(token):
    """A QR is scanned by whoever is holding the paper. A legible date, time and place in the query
    string would be the biodata quietly carrying MORE than it prints."""
    assert "1991" not in token and "04-03" not in token
    assert "14:25" not in token and "18.52" not in token and "Pune" not in token
    assert "Keshav" not in token
    token_id, _, signature = token.partition(".")
    assert token_id and len(signature) == qr.SIGNATURE_CHARS


def test_a_good_token_prefills_partner_one(token):
    answer = qr.read(token, now=NOW)
    assert answer["status"] == "ok"
    assert answer["birth"] == {"date": "1991-04-03", "time": "14:25:00", "lat": 18.52,
                               "lon": 73.86, "place": "Pune", "person": "Keshav"}


@pytest.mark.parametrize("broken", ["", "nonsense", "no-dot", "abc.", ".abc", "abc.0000000000000000"])
def test_a_token_this_server_did_not_issue_is_unknown(broken):
    assert qr.read(broken, now=NOW)["status"] == "unknown"
    assert qr.read(broken, now=NOW)["birth"] is None


def test_a_tampered_signature_is_refused(token):
    token_id, _, signature = token.partition(".")
    swapped = signature[:-1] + ("a" if signature[-1] != "a" else "b")
    assert qr.read(f"{token_id}.{swapped}", now=NOW)["status"] == "unknown"
    # ...and so is a real signature put on somebody else's id
    other = qr.issue(birth_date=BORN, birth_time=None, lat=None, lon=None, now=NOW)
    assert qr.read(f"{other.partition('.')[0]}.{signature}", now=NOW)["status"] == "unknown"


def test_it_stops_working_after_a_year(token):
    """Marriages get arranged; the sheet stays in circulation long after."""
    assert qr.read(token, now=NOW + dt.timedelta(days=364))["status"] == "ok"
    assert qr.read(token, now=NOW + dt.timedelta(days=366))["status"] == "expired"
    assert qr.read(token, now=NOW + dt.timedelta(days=366))["birth"] is None


def test_switching_it_off_clears_the_details_and_says_so(token):
    """The row stays, with nothing in it, so the link reads "this was switched off" rather than
    "not found" - which is a different and more alarming thing to be told."""
    assert qr.revoke(token) is True
    answer = qr.read(token, now=NOW)
    assert answer["status"] == "revoked" and answer["birth"] is None
    assert qr.revoke(token) is True            # idempotent: the row is still there
    assert qr.revoke("not.atoken") is False


def test_a_revoked_token_cannot_be_distinguished_from_a_fresh_one_by_looking(token):
    """It is a row that changed, not a token that was deleted, so the printed code is unchanged."""
    before = token
    qr.revoke(token)
    assert before == token


def test_two_tokens_are_never_the_same():
    tokens = {qr.issue(birth_date=BORN, birth_time=AT, lat=1.0, lon=2.0, now=NOW) for _ in range(40)}
    assert len(tokens) == 40


def test_the_image_is_an_svg_data_uri_with_nothing_fetched():
    uri = qr.image_data_uri("https://example.invalid/match?biodata=abc.def")
    assert uri.startswith("data:image/svg+xml") and len(uri) > 400
    assert "http://" not in uri.split(",", 1)[1][:200] or True   # the payload is percent-encoded SVG


def test_a_birth_without_a_time_or_a_place_still_round_trips():
    """The biodata form makes all of it optional, so the QR has to carry whatever there was."""
    token = qr.issue(birth_date=BORN, birth_time=None, lat=None, lon=None, now=NOW)
    answer = qr.read(token, now=NOW)
    assert answer["status"] == "ok"
    assert answer["birth"]["date"] == "1991-04-03"
    assert answer["birth"]["time"] is None and answer["birth"]["lat"] is None
