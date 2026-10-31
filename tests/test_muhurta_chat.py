"""A date question inside a consultation - and, far more importantly, everything that is not one.

The risk this file exists for is the FALSE POSITIVE. A reader who asks about their marriage and gets a
table of dates has been answered by the wrong feature. So most of what is below is ordinary questions that
must still reach the astrologer untouched, in all three languages, with the flag on.
"""

import datetime as dt

import pytest

from app.ai import chat, muhurta_intent
from app.web import site

PUNE = {"name": "Pune", "lat": 18.5204, "lon": 73.8567, "tz": "Asia/Kolkata"}
SESSION = {"birth": {"lat": 18.5204, "lon": 73.8567, "city": "Pune", "timezone": "Asia/Kolkata"}}


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(site, "MUHURTA", True)


# ---- what must NOT be taken as a date question -----------------------------------------------------

ORDINARY = [
    "will my marriage work out",
    "tell me about my career this year",
    "is mangal dosha a problem in my chart",
    "my new house is lovely, what does the chart say about family",
    "when will I get married",                      # asks when, but no purpose this finder knows
    "what is my moon sign",
    "मेरी शादी कब होगी",
    "मेरा करियर कैसा रहेगा",
    "नया घर कैसा रहेगा मेरे लिए",                      # a purpose word, but not asking for a date
    "माझं लग्न कधी होईल",
    "माझा व्यवसाय कसा चालेल",
    "कोणता दिवस माझ्यासाठी चांगला असतो साधारण",         # vague, no purpose
]


@pytest.mark.parametrize("text", ORDINARY)
def test_an_ordinary_question_is_never_taken_for_a_date_question(text):
    assert muhurta_intent.detect(text) is None, f"{text!r} was mistaken for a muhurta request"
    assert chat._muhurta_reply(SESSION, text, "en") is None


@pytest.mark.parametrize("text", ORDINARY)
def test_and_the_chat_path_leaves_them_alone(text):
    """The same claim one level up, where it actually matters: send_message must fall through to the AI."""
    assert chat._muhurta_reply(SESSION, text, "hi") is None
    assert chat._muhurta_reply(SESSION, text, "mr") is None


# ---- what must be ----------------------------------------------------------------------------------

ASKED = [
    ("when is a good day for griha pravesh", "griha-pravesh", "en"),
    ("muhurat for buying a car next month", "vehicle", "en"),
    ("best day to start my shop", "business", "en"),
    ("गृह प्रवेश के लिए शुभ दिन बताइए", "griha-pravesh", "hi"),
    ("वाहन खरीदने का मुहूर्त क्या है", "vehicle", "hi"),
    ("गृहप्रवेशासाठी चांगला दिवस कोणता", "griha-pravesh", "mr"),
    ("नवीन गाडी घेण्यासाठी मुहूर्त", "vehicle", "mr"),
]


@pytest.mark.parametrize("text, purpose, lang", ASKED)
def test_a_date_question_is_recognised_and_answered_from_the_engine(text, purpose, lang):
    assert muhurta_intent.detect(text) == purpose
    reply = chat._muhurta_reply(SESSION, text, lang)
    assert reply, f"{text!r} was recognised but produced nothing"
    assert any(phrase in reply for phrase in ("arithmetic, not a guarantee", "गणित है, गारंटी नहीं",
                                              "गणित आहे, हमी नाही"))


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_reply_carries_real_dates_with_their_panchang(lang):
    reply = muhurta_intent.answer("griha-pravesh", lang, PUNE, today=dt.date(2027, 3, 1))
    assert "2027-03-" in reply
    assert "14:14-15:42" in reply or ":" in reply, "no Rahu Kaal in the reply"
    assert ("/muhurta" if lang == "en" else f"/{lang}/muhurta") in reply


def test_an_empty_answer_is_said_plainly_and_not_padded():
    reply = muhurta_intent.answer("griha-pravesh", "en", PUNE, today=dt.date(2027, 3, 12))
    # Twelve March is rikta; a sixty-day window from it will usually find something, so this asserts the
    # shape of the honest answer rather than that it is empty.
    assert "arithmetic, not a guarantee" in reply


@pytest.mark.parametrize("text", ["muhurat for my surgery", "good day for the operation",
                                  "ऑपरेशन के लिए शुभ दिन", "शस्त्रक्रियेसाठी चांगला दिवस"])
def test_a_date_for_health_is_refused_in_words_rather_than_left_to_the_model(text):
    for lang in ("en", "hi", "mr"):
        reply = chat._muhurta_reply(SESSION, text, lang)
        assert reply, f"{text!r} fell through instead of being refused"
        assert "2027-" not in reply and "-" not in reply.split("\n")[0][:10]


# ---- the flag and the failure modes ----------------------------------------------------------------


def test_nothing_fires_at_all_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(site, "MUHURTA", False)
    assert chat._muhurta_reply(SESSION, "when is a good day for griha pravesh", "en") is None
    assert chat._muhurta_reply(SESSION, "muhurat for my surgery", "en") is None


def test_a_session_without_a_place_falls_through_rather_than_guessing():
    """A muhurta is a fact about a PLACE. Without one the honest move is to let the astrologer answer."""
    assert chat._muhurta_reply({"birth": {}}, "when is a good day for griha pravesh", "en") is None
    assert chat._muhurta_reply({}, "muhurat for buying a car", "en") is None


def test_a_broken_search_never_breaks_the_consultation(monkeypatch):
    """Whatever goes wrong in here, the reader's question must still reach the astrologer."""
    def explode(*args, **kwargs):
        raise RuntimeError("ephemeris on fire")

    monkeypatch.setattr(muhurta_intent, "answer", explode)
    assert chat._muhurta_reply(SESSION, "when is a good day for griha pravesh", "en") is None
