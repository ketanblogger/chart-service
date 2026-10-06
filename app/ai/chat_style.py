"""The language and script a conversation is written in, decided once and then kept.

WHY THIS EXISTS. The prompt used to say "reply in the language of the person's latest message". That is
right for a first message and wrong for every one after it: most people here open a chat in Devanagari and
then type the follow-up in Latin letters, because that is what a phone keyboard makes easy. Asked to change
script mid-conversation, the model changed it halfway - "Kundalit sध्या Chandra mahadasha madhe" - and the
one check that would have caught it was advisory, so the mixture was delivered.

So a chat has a STYLE: one of English, Hindi or Marathi, in Devanagari or in Latin letters. The first
message settles it; after that only an explicit request moves it. How a later message happens to be typed
is not a request.
"""
from __future__ import annotations

import re
import unicodedata

from .chat_safety import LANGUAGE_NAMES, LANGUAGES, detect_language

#: The scripts a reply may be written in. Anything else - a stray Arabic letter from the model's own
#: vocabulary, which is how "ekapaठoپाठ" happened - is a defect, not a choice.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

#: Latin that is at home inside a Devanagari reply: dates, and abbreviations with no Devanagari form.
_LATIN_AT_HOME = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov",
    "dec", "am", "pm", "ist", "pdf", "gst", "ai", "sms", "otp", "upi", "rs", "inr", "whatsapp", "google",
    # ...and the names of what the figures were computed with, which a Devanagari reply may well cite and
    # which have no Devanagari form anyone writes.
    "swiss", "ephemeris", "lahiri", "ayanamsa", "ayanamsha", "rashikundli",
}
#: How many other Latin words a Devanagari reply may carry before it stops being a Devanagari reply.
_LATIN_WORDS_ALLOWED = 2


def settle(first_message: str, default: str = "en") -> str:
    """The style of a chat, from its first message. `default` is the page's own language."""
    style = detect_language(first_message or "", default=default)
    return style if style in LANGUAGES else "en"


def name(style: str) -> str:
    return LANGUAGE_NAMES.get(style, LANGUAGE_NAMES["en"])


# ---- "say it in Devanagari" --------------------------------------------------------------------------

#: Word boundaries are not decoration here. Without them "bol" matched inside "pro-bl-em" and "use" inside
#: "ho-use" - and "house" is a word this service says in nearly every conversation, so "my 8th house in
#: English terms?" quietly switched the chat to English. Generic verbs like "use" and "talk" are gone for
#: the same reason: they carry no request on their own.
_WRITE = re.compile(
    r"\b(likh|likho|likhiye|lihi|liha|sang|sanga|bol|bolo|batao|bataiye|reply|answer|write|respond|"
    r"switch)\b|(लिह|लिख|सांग|बोल|बता|उत्तर|जवाब)", re.IGNORECASE)
#: How close the naming of a language must sit to the asking, in characters.
_NEAR = 14

_TONGUE = (
    ("en", re.compile(r"(english|इंग्रजी|इंग्लिश|अंग्रेज़ी|अंग्रेजी)", re.IGNORECASE)),
    ("hi", re.compile(r"(hindi|हिंदी|हिन्दी)", re.IGNORECASE)),
    ("mr", re.compile(r"(marathi|मराठी)", re.IGNORECASE)),
)
_SCRIPT = (
    ("Deva", re.compile(r"(devanagari|devnagari|देवनागरी|devanaagari)", re.IGNORECASE)),
    ("Latn", re.compile(r"(roman|romanised|romanized|latin|english letters|रोमन|लॅटिन|लैटिन)", re.IGNORECASE)),
)


def requested_style(text: str, current: str) -> str | None:
    """The style the person has ASKED for, or None.

    Both halves are required: a word naming a language or a script, and a word asking for it to be written
    that way. "arogyachey upay nahi mantra etc magat ahe" names neither and must not move anything - that
    message is the whole reason this function is strict.
    """
    text = text or ""
    verbs = [m.span() for m in _WRITE.finditer(text)]
    if not verbs:
        return None

    def near(pattern):
        """A naming of a language or script that is actually ATTACHED to the asking.

        "hindi film industry baddal sanga" names Hindi and asks to be told something, and means neither -
        the two are twenty-two characters apart. Every real way of asking puts them side by side:
        "hindi me likho", "reply in English", "देवनागरी मध्ये सांग".
        """
        for found in pattern.finditer(text):
            for start, end in verbs:
                if min(abs(found.start() - end), abs(start - found.end())) <= _NEAR:
                    return True
        return False

    tongue = next((code for code, pattern in _TONGUE if near(pattern)), None)
    script = next((code for code, pattern in _SCRIPT if near(pattern)), None)
    if tongue is None and script is None:
        return None

    base = (current or "en").split("-")[0]
    tongue = tongue or base
    if tongue == "en":
        return "en"                                  # English is written in Latin letters and that is all
    if script is None:
        script = "Latn" if (current or "").endswith("-Latn") else "Deva"
    return tongue if script == "Deva" else f"{tongue}-Latn"


# ---- what a reply may be made of ---------------------------------------------------------------------

def _letters(word: str) -> str:
    return "".join(ch for ch in word if unicodedata.category(ch).startswith("L"))


def script_problems(reply: str, style: str) -> list[str]:
    """Why this reply is not written in `style`. Empty means it is.

    Three faults, each seen in the one reply that prompted all this:
      - a letter from neither script (the Arabic پ in "ekapaठoپाठ");
      - one word holding both scripts ("sध्या", "8व्या", "vegळe");
      - and a reply that is simply in the other script.
    """
    reply = reply or ""
    problems: list[str] = []

    stray = {ch for ch in reply
             if unicodedata.category(ch).startswith("L")
             and not _LATIN.match(ch) and not _DEVANAGARI.match(ch)}
    if stray:
        problems.append("the reply contains letters from another script entirely (" +
                        " ".join(sorted(stray)) + ") - use only the one script this conversation is in")

    for word in re.findall(r"\S+", reply):
        letters = _letters(word)
        if _LATIN.search(letters) and _DEVANAGARI.search(letters):
            problems.append(f"the word {word!r} mixes Latin and Devanagari letters - never inside one word")
            break

    wants_latin = style.endswith("-Latn") or style == "en"
    if wants_latin:
        if _DEVANAGARI.search(reply):
            problems.append("this conversation is written in Latin letters - remove every Devanagari "
                            "character, including inside words")
    else:
        loose = [w for w in re.findall(r"[A-Za-z]{2,}", reply) if w.lower() not in _LATIN_AT_HOME]
        if len(loose) > _LATIN_WORDS_ALLOWED:
            problems.append("this conversation is written in Devanagari - write these in Devanagari: " +
                            ", ".join(loose[:6]))
    return problems


#: What the chat is labelled with on the page, per style, in the language of the page it is read on.
_LABELS = {
    "en": {"en": "English", "hi": "English", "mr": "English"},
    "hi": {"en": "Hindi · Devanagari", "hi": "हिंदी · देवनागरी", "mr": "हिंदी · देवनागरी"},
    "mr": {"en": "Marathi · Devanagari", "hi": "मराठी · देवनागरी", "mr": "मराठी · देवनागरी"},
    "hi-Latn": {"en": "Hindi · Roman", "hi": "हिंदी · रोमन", "mr": "हिंदी · रोमन"},
    "mr-Latn": {"en": "Marathi · Roman", "hi": "मराठी · रोमन", "mr": "मराठी · रोमन"},
}


def label(style: str, page_language: str = "en") -> str:
    """The style as the reader sees it beside their chat, and clicks to change."""
    page = page_language if page_language in ("en", "hi", "mr") else "en"
    return _LABELS.get(style, _LABELS["en"])[page]


def choices(page_language: str = "en") -> list[dict]:
    """Every style a person may pick, labelled for the page they are on."""
    return [{"style": style, "label": label(style, page_language)} for style in _LABELS]


__all__ = ["LANGUAGES", "choices", "label", "name", "requested_style", "script_problems", "settle"]
