"""A chat keeps the language AND SCRIPT it started in, until the person asks for another.

THE BUG THIS IS FOR, live on 7ffdc3d. A Marathi chat opened in Devanagari and the first answer was right.
The follow-up was typed in ROMAN Marathi - which is how most people actually type - and the reply came back
as neither script and both: "Kundalit sध्या Chandra mahadasha madhe Ketu antardasha", with an Arabic-script
letter inside one word, repeating remedies the first answer had already given.

Three separate faults produced it, and each is pinned here:

  1. the prompt said to answer in the language of the LATEST message, so a romanised follow-up asked for a
     change of script mid-conversation and got one halfway;
  2. the only check that would have caught the mixture - Devanagari inside a romanised reply - was SOFT, so
     the second draft was delivered whether it was clean or not;
  3. nothing told the model that a follow-up refining a request is not a request to say everything again.

What can and cannot be asserted here: these tests do not prove the model obeys. They prove the chat STORES
one style, that every turn carries it as an instruction, and that a reply which breaks it is caught and
never delivered. That last one is the part that does not depend on a model behaving.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import accounts

BIRTH = {"name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
         "timezone": "Asia/Kolkata", "city": "Pune", "language": "mr"}

# Her actual follow-up and the reply it produced, verbatim: every property asserted below is a property of
# THIS text, and a paraphrase would quietly stop testing what happened.
ROMAN_FOLLOWUP = "arogyachey upay nahi mantra etc magat ahe dr kadey tar jotoch amhi"
GARBLED = (
    "Barobar ahe, doctor kadun treatment ghetach ahat he changla aahe. Kundalit sध्या Chandra mahadasha "
    "madhe Ketu antardasha chalu aahe (3 September 2026 te 4 April 2027), ani Ketu tumchya 8व्या sthanat "
    "Shani sobat aahe, त्यामुळे असे lahan-lahan vegळe trouble ekapaठoپाठ yet asल्यासारखे vatते."
)
CLEAN_ROMAN = "Upay mhanun Ketu cha mantra japa, shanivari daan kara ani routine saral theva."
CLEAN_DEVA = "उपाय म्हणून केतूचा मंत्रजप करा, शनिवारी दान करा आणि दिनक्रम साधा ठेवा."


class Recorder:
    """Answers with whatever is queued, and keeps every prompt it was handed."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate_chat(self, *, system, messages, **kwargs):
        self.calls.append({"system": system, "messages": messages})
        text = self.replies.pop(0) if self.replies else "Theek aahe."

        class Result:
            pass

        Result.text = text
        Result.usage, Result.model, Result.request_id, Result.data = {}, "fake", None, None
        return Result()


def drive(monkeypatch, turns, *, language="mr", email="style.lock@gmail.com", session_id=None):
    """Run a real chat with a scripted model. `turns` is [(what the person typed, what the model returns)].

    A reply may be a LIST, which queues several drafts for one turn - that is how a regeneration is tested.
    """
    import app.ai.chat as chat

    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(email))
    if session_id is None:
        session_id = client.post("/api/consultation/start",
                                 json={**BIRTH, "language": language}).json()["session_id"]
    queued = []
    for _, reply in turns:
        queued.extend(reply if isinstance(reply, list) else [reply])
    recorder = Recorder(queued)
    monkeypatch.setattr(chat, "get_chat_client", lambda: recorder)
    delivered = [chat.send_message(session_id, text, unlimited=True)["reply"]["content"]
                 for text, _ in turns]
    return {"session_id": session_id, "recorder": recorder, "replies": delivered, "client": client}


def flatten(value) -> list[str]:
    """The text of a prompt, whether it arrives as a string or as a list of content blocks."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [block.get("text", "") if isinstance(block, dict) else str(block) for block in value]
    return [str(value)]


def told(call) -> str:
    """Everything the model was given on one turn: the system blocks and every rendered turn."""
    parts = flatten(call["system"])
    for message in call["messages"]:
        content = message["content"]
        if isinstance(content, list):
            parts.extend(block.get("text", "") for block in content)
        else:
            parts.append(str(content))
    return "\n".join(parts)


def style_of(session_id: str) -> str:
    from app.ai import chat_store as store

    return (store.get_session(session_id) or {}).get("style") or ""


# ---- (a) to (e): the style belongs to the chat, and only the person changes it ----------------------

def test_a_devanagari_start_then_roman_followup_stays_devanagari(monkeypatch):
    """Samprita's case. How the follow-up is TYPED must not move the conversation's script."""
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA),
                              (ROMAN_FOLLOWUP, CLEAN_DEVA)])
    assert style_of(run["session_id"]) == "mr", "the chat did not keep the style it opened in"
    assert "Marathi (Devanagari)" in told(run["recorder"].calls[-1])


def test_b_roman_start_then_devanagari_followup_stays_roman(monkeypatch):
    run = drive(monkeypatch, [("mala arogya baddal sanga", CLEAN_ROMAN),
                              ("माझ्या कुंडलीत काय आहे?", CLEAN_ROMAN)],
                email="style.roman@gmail.com")
    assert style_of(run["session_id"]) == "mr-Latn"
    assert "romanised" in told(run["recorder"].calls[-1]).lower()


def test_c_an_explicit_request_changes_the_style_and_it_stays_changed(monkeypatch):
    """The one thing that MAY change it - and it must stick for the turns after, not just that one."""
    run = drive(monkeypatch, [("mala arogya baddal sanga", CLEAN_ROMAN),
                              ("Devanagari madhe sang", CLEAN_DEVA),
                              ("ani upay?", CLEAN_DEVA)],
                email="style.switch@gmail.com")
    assert style_of(run["session_id"]) == "mr", "an explicit request did not change the style"
    assert "Marathi (Devanagari)" in told(run["recorder"].calls[-1]), "the change did not stick"


@pytest.mark.parametrize("phrase, expected", [
    ("reply in English", "en"),
    ("English mein likho", "en"),
    ("देवनागरी मध्ये सांग", "mr"),
    ("hindi me likho", "hi"),
    ("roman madhe lihi", "mr-Latn"),
])
def test_c2_the_ways_people_ask_for_another_style(phrase, expected):
    from app.ai.chat_style import requested_style

    assert requested_style(phrase, current="mr") == expected


@pytest.mark.parametrize("text", [
    "my 8th house in english terms?",       # "house" contains "use", which used to count as asking
    "hindi film industry baddal sanga",     # names a language and asks to be told something, means neither
    "mala english madhe problem ahe",       # "problem" contains "bol"
    "arogyachey upay nahi mantra etc magat ahe",
    "maza lagna kadhi hoil?",
])
def test_c4_an_ordinary_question_never_changes_the_style(text):
    """FALSE POSITIVES ARE THE DANGEROUS DIRECTION HERE. Missing a request costs one more message; acting
    on one that was never made rewrites the rest of somebody's conversation into a script they did not ask
    for - which is the fault this whole file exists to stop, arriving by the other door."""
    from app.ai.chat_style import requested_style

    assert requested_style(text, current="mr") is None


def test_c3_merely_writing_in_another_script_is_not_a_request(monkeypatch):
    """The whole point: typing a romanised sentence is not asking for romanised replies."""
    from app.ai.chat_style import requested_style

    assert requested_style(ROMAN_FOLLOWUP, current="mr") is None
    assert requested_style("माझ्या कुंडलीत काय आहे?", current="mr-Latn") is None


def test_d_a_mixed_first_message_settles_on_one_style_and_keeps_it(monkeypatch):
    """A first message in two scripts must still produce ONE answer about what this chat is."""
    run = drive(monkeypatch, [("mala health issues yet ahet, ग्रह कसे आहेत?", CLEAN_DEVA),
                              ("ani upay?", CLEAN_DEVA)],
                email="style.mixed@gmail.com")
    settled = style_of(run["session_id"])
    assert settled in ("mr", "mr-Latn"), f"no style was settled on: {settled!r}"
    assert settled in told(run["recorder"].calls[-1]) or \
        {"mr": "Marathi (Devanagari)", "mr-Latn": "romanised"}[settled].lower() in told(run["recorder"].calls[-1]).lower()


def test_e_two_chats_of_one_person_keep_their_own_styles(monkeypatch):
    """The style is the CHAT's, not the account's - one person may ask about two people two ways."""
    first = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA)], email="style.two@gmail.com")
    second = drive(monkeypatch, [("mala arogya baddal sanga", CLEAN_ROMAN)], email="style.two@gmail.com")
    assert first["session_id"] != second["session_id"]
    assert style_of(first["session_id"]) == "mr"
    assert style_of(second["session_id"]) == "mr-Latn"


# ---- (f) the reply that was actually delivered ------------------------------------------------------

def test_f_the_garbled_reply_is_caught_and_regenerated(monkeypatch):
    """The exact text she received. A second, clean draft is what reaches her."""
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA),
                              (ROMAN_FOLLOWUP, [GARBLED, CLEAN_DEVA])],
                email="style.garbled@gmail.com")
    assert run["replies"][-1] == CLEAN_DEVA, "the garbled reply was delivered"
    assert len(run["recorder"].calls) == 3, "the garbled reply was not regenerated"


def test_f2_a_reply_that_stays_garbled_is_replaced_not_shown(monkeypatch):
    """Twice bad means the person gets a clean sentence, never the mixture."""
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA),
                              (ROMAN_FOLLOWUP, [GARBLED, GARBLED])],
                email="style.twice@gmail.com")
    delivered = run["replies"][-1]
    assert delivered != GARBLED
    assert "sध्या" not in delivered and "ekapa" not in delivered


#: Mixed script and NOTHING ELSE: no dates, no placements, nothing the fact checker could object to. The
#: live reply has both faults, so a test built only on it passes even with the script check deleted - which
#: is what deleting the check proved. This one fails the moment the check stops being enforced.
ONLY_MIXED = "Barobar ahe, sध्या theek aahe ani upay kara."


def test_f2b_a_mixed_reply_with_no_other_fault_is_still_refused(monkeypatch):
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA),
                              ("ani upay?", [ONLY_MIXED, ONLY_MIXED])],
                email="style.onlymixed@gmail.com")
    assert run["replies"][-1] != ONLY_MIXED, "a reply whose only fault is mixed script was delivered"
    assert "sध्या" not in run["replies"][-1]


def test_f2c_the_regeneration_is_asked_for_the_right_reason(monkeypatch):
    """Not just that it retried - that the note it retried on NAMES the script fault."""
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA),
                              ("ani upay?", [ONLY_MIXED, CLEAN_DEVA])],
                email="style.reason@gmail.com")
    retry = told(run["recorder"].calls[-1])
    assert "mixes Latin and Devanagari" in retry or "Devanagari" in retry
    assert "Marathi (Devanagari)" in retry, "the retry does not restate the style it must be written in"


@pytest.mark.parametrize("bad, why", [
    (GARBLED, "the live reply"),
    ("Chandra mahadasha madhe Ketu antardasha chalu aahe ani ग्रह theek aahet.", "Devanagari in a Latin reply"),
    ("तुमच्या कुंडलीत Chandra mahadasha chalu aahe.", "Latin sentences in a Devanagari reply"),
    ("उपाय ekapaठoپाठ करा", "a letter from a third script"),
    ("ekapaठoپाठ", "Latin, Devanagari and Arabic inside one word"),
])
def test_f3_every_shape_of_the_mixture_is_refused(bad, why):
    from app.ai.chat_style import script_problems

    assert script_problems(bad, "mr"), f"not caught: {why}"


@pytest.mark.parametrize("good, style", [
    (CLEAN_DEVA, "mr"),
    (CLEAN_ROMAN, "mr-Latn"),
    ("Your Moon is in Kanya, and Guru runs until 20 Jul 2030.", "en"),
    ("Chandra mahadasha 4 April 2027 paryant aahe; mantra japa.", "mr-Latn"),
    ("तुमच्या कुंडलीत चंद्र महादशा 4 April 2027 पर्यंत आहे.", "mr"),
    ("Shani is vakri; 11 December 2026 la margi hoil.", "mr-Latn"),
])
def test_f4_a_clean_reply_in_its_own_style_is_not_refused(good, style):
    """The check must not fire on dates, numbers, or the English words people really do use."""
    from app.ai.chat_style import script_problems

    assert not script_problems(good, style), f"wrongly refused: {good!r}"


def test_f5_the_model_is_told_not_to_repeat_an_earlier_answer(monkeypatch):
    """Her follow-up asked for MORE remedies and got the first answer back."""
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA),
                              (ROMAN_FOLLOWUP, CLEAN_DEVA)],
                email="style.repeat@gmail.com")
    second = told(run["recorder"].calls[-1])
    # The exact rule, not a phrase that happens to appear elsewhere. The first version of this assertion
    # looked for "not repeat" and passed on the disclaimer's own "do NOT repeat it here" - it would have
    # gone on passing with the whole no-repeat instruction deleted.
    assert "do not restate what an" in second, "the no-repeat rule is not being sent"
    assert "give NEW material" in second


# ---- (g) the disclaimer ------------------------------------------------------------------------------

def test_g_the_long_disclaimer_is_asked_for_once_per_chat(monkeypatch):
    """It was on every reply because every one of her messages was about health."""
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA),
                              (ROMAN_FOLLOWUP, CLEAN_DEVA),
                              ("ani aarogya?", CLEAN_DEVA)],
                email="style.disclaimer@gmail.com")
    calls = run["recorder"].calls
    sentence = "traditional faith-based practice"
    assert sentence in told(calls[0]), "the first reply was not asked for the disclaimer"
    for later in calls[1:]:
        assert "first reply of a conversation" in told(later) or sentence not in told(later), \
            "a follow-up is still being asked for the full disclaimer"


# ---- the label the person can see and change --------------------------------------------------------

def test_the_chat_list_shows_the_style_and_offers_to_change_it(monkeypatch):
    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA)], email="style.label@gmail.com")
    rows = run["client"].get("/api/consultation/mine").json()["sessions"]
    row = next(r for r in rows if r["session_id"] == run["session_id"])
    assert row.get("style") == "mr"
    assert row.get("style_label"), "the person is shown no style to click"


# ---- the conversations that already exist ------------------------------------------------------------

def test_a_chat_from_before_this_column_keeps_the_style_it_has_been_speaking(monkeypatch):
    """SAMPRITA'S OWN CHAT. Every conversation on the live site has no stored style, and hers was four
    Devanagari turns old when she typed a romanised follow-up. Settling the style from the message in hand
    would have locked her Devanagari chat to Latin letters - the exact failure this work exists to stop,
    reintroduced by the migration. The style of an old chat is its FIRST message, not its latest.
    """
    from app.ai import chat_store as store

    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA)], email="style.old@gmail.com")
    session_id = run["session_id"]
    store.set_style(session_id, "")                      # as every chat on the live site looks today

    again = drive(monkeypatch, [(ROMAN_FOLLOWUP, CLEAN_DEVA)], session_id=session_id,
                  email="style.old@gmail.com")
    assert style_of(session_id) == "mr", "an existing Devanagari chat was switched to Latin letters"
    assert "Marathi (Devanagari)" in told(again["recorder"].calls[-1])


def test_an_old_chat_still_hears_an_explicit_request_on_the_settling_turn(monkeypatch):
    """The migration must not swallow the one message that is allowed to change the style."""
    from app.ai import chat_store as store

    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA)], email="style.oldask@gmail.com")
    store.set_style(run["session_id"], "")
    drive(monkeypatch, [("reply in English please", "Your Moon is in Tula.")],
          session_id=run["session_id"], email="style.oldask@gmail.com")
    assert style_of(run["session_id"]) == "en"


def test_an_old_chat_is_not_asked_for_the_opening_disclaimer_again(monkeypatch):
    """`first_reply` means "this conversation has no history", not "no style is stored yet"."""
    from app.ai import chat_store as store

    run = drive(monkeypatch, [("माझ्या आरोग्याबद्दल सांगा", CLEAN_DEVA)], email="style.olddisc@gmail.com")
    store.set_style(run["session_id"], "")
    again = drive(monkeypatch, [("ani upay?", CLEAN_DEVA)], session_id=run["session_id"],
                  email="style.olddisc@gmail.com")
    assert "traditional faith-based practice" not in told(again["recorder"].calls[-1]), \
        "an old conversation was treated as a new one and asked for the opening sentence again"
