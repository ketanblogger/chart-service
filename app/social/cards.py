"""What goes on a daily social card, and which rashi gets the "today's one to watch" card.

EVERY WORD ON A CARD IS THE ENGINE'S. The graha, the sign, the house counted from the rashi, the nakshatra,
the tithi, the date - all of it comes from app/rashifal/brief.py and is phrased by the same
`describe_event` / name helpers the site itself uses. No AI call is made building these, and no interpretive
sentence is written here: a card says WHERE a graha is, never what it means for you. That is the only claim
this project is willing to make in a format nobody can click through from to see the calculation behind it.

It is also why the forbidden-topic list below is short and absolute. A card is seen out of context, by people
who did not ask for it, and it is not the place for anything about death, illness or accidents - the site
does not say those things anywhere, and a card is the last place to start.
"""

import datetime as dt
import re

from app.rashifal import i18n as words
from app.rashifal.brief import build_brief
from app.web import i18n

LANGS = ("en", "hi", "mr")

# Slower grahas make the bigger news: Saturn moves once in two and a half years, the Moon every two days.
GRAHA_WEIGHT = {"Saturn": 9, "Rahu": 8, "Ketu": 8, "Jupiter": 7, "Mars": 5,
                "Venus": 4, "Mercury": 3, "Sun": 2, "Moon": 1}
# A station (turning retrograde or direct) is rarer than an ingress and is what people notice.
TYPE_WEIGHT = {"station": 3, "ingress": 2}
# Which house the event lands in, from the rashi being considered. The angles first, then the trines.
HOUSE_WEIGHT = {1: 9, 7: 7, 10: 6, 4: 5, 5: 4, 9: 4, 11: 3, 2: 2, 3: 1, 6: 1, 8: 1, 12: 1}

# Never on a card, in any language. Checked against the rendered text, not trusted to the source.
# NOT "cancer": it is the English name of a rashi, and every English Cancer card carries it. The filter
# refused all 26 English cards over it, which is the filter working - it checks the RENDERED text and writes
# nothing when it objects - but the word is a sign here and the disease sense can only arise in interpretive
# prose, which these cards never contain. The rest stay absolute.
FORBIDDEN = re.compile(
    r"death|dying|dead|die\b|illness|disease|accident|suicide|divorce|lawsuit"
    r"|मृत्यु|मौत|बीमारी|रोग|दुर्घटना|तलाक|आत्महत्या"
    r"|मृत्यू|आजार|आजारपण|अपघात|घटस्फोट|आत्महत्या",
    re.IGNORECASE)

HASHTAGS = {
    "en": "#vedicastrology #jyotish #horoscope #astrology #rashifal #swissephemeris",
    "hi": "#राशिफल #ज्योतिष #वैदिकज्योतिष #कुंडली #horoscope #jyotish",
    "mr": "#राशिभविष्य #ज्योतिष #वैदिकज्योतिष #पत्रिका #horoscope #jyotish",
}
CARD_LABELS = {
    "en": {"today": "Today", "moon": "Moon", "nakshatra": "Nakshatra", "tithi": "Tithi",
           "house_from": "from your rashi", "watch": "Today's one to watch", "calc": "Swiss Ephemeris · sidereal · Lahiri",
           "house": "house", "moon_at": "Moon (sunrise)"},
    "hi": {"today": "आज", "moon": "चंद्र", "nakshatra": "नक्षत्र", "tithi": "तिथि",
           "house_from": "आपकी राशि से", "watch": "आज की सबसे बड़ी बात", "calc": "स्विस एफेमेरिस · निरयन · लाहिरी",
           "house": "भाव", "moon_at": "चंद्र (सूर्योदय)"},
    "mr": {"today": "आज", "moon": "चंद्र", "nakshatra": "नक्षत्र", "tithi": "तिथी",
           "house_from": "तुमच्या राशीपासून", "watch": "आजची सर्वात मोठी गोष्ट", "calc": "स्विस एफेमेरिस · निरयन · लाहिरी",
           "house": "स्थान", "moon_at": "चंद्र (सूर्योदय)"},
}


# English ordinals, which `rashifal.i18n.ordinal` deliberately does not produce - it returns a bare number
# because the English rashifal copy writes the suffix itself. A card has no sentence around the number, so
# it has to carry its own: the card read "12 house from your rashi", which is not a thing anybody writes.
_EN_SUFFIX = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}


def _house_phrase(house: int, lang: str, labels: dict) -> str:
    """"12th house from your rashi" / "बारहवाँ भाव आपकी राशि से" / "बारावे स्थान तुमच्या राशीपासून"."""
    if lang == "en":
        return f"{house}{_EN_SUFFIX.get(house, 'th')} {labels['house']} {labels['house_from']}"
    return f"{words.ordinal(house, lang)} {labels['house']} {labels['house_from']}"


def utm_link(rashi: str, lang: str, date: str, base_url: str) -> str:
    """The rashi's own daily page, tagged so the traffic is attributable to the card that carried it."""
    path = i18n.url_for("rashifal-reading", lang, rashi=rashi, period="today")
    return (f"{base_url.rstrip('/')}{path}?utm_source=instagram&utm_medium=social"
            f"&utm_campaign=daily-card&utm_content={date}-{rashi}")


def _event_line(event: dt, lang: str) -> str:  # noqa: ARG001 - typed loosely, it is a brief dict
    return words.describe_event(event, lang)


def score(event: dict) -> int:
    return GRAHA_WEIGHT.get(event["graha"]["key"], 1) * 100 + TYPE_WEIGHT.get(event.get("type"), 1) * 10


def card_for(rashi: str, lang: str, now: dt.datetime) -> dict:
    """One rashi's card content for one language. Engine facts only."""
    brief = build_brief(rashi, "today", now)
    labels = CARD_LABELS[lang]
    names = i18n.rashi_names(rashi, lang)
    moon = brief.get("moon_at_sunrise") or brief.get("moon_at_start") or {}
    panchang = brief.get("panchang") or {}
    events = sorted(brief.get("events") or [], key=lambda e: (-score(e), e.get("time_ist") or ""))

    facts = []
    if moon.get("sign"):
        # LABELLED "at sunrise", because the headline above it may be the Moon CHANGING sign later the same
        # day. Both are true and the card showed them side by side - "the Moon enters Cancer" over "Moon:
        # Gemini" - which reads as a mistake even though neither figure is wrong. The brief itself states
        # this convention ("values current at sunrise"); the card now says so too.
        facts.append((labels["moon_at"], f"{words.sign_name(moon['sign'], lang)} · "
                                         f"{_house_phrase(moon['house'], lang, labels)}"))
    nakshatra = panchang.get("nakshatra") or moon.get("nakshatra")
    if nakshatra:
        facts.append((labels["nakshatra"], words.nakshatra_name(nakshatra, lang)))
    if panchang.get("tithi"):
        facts.append((labels["tithi"], words.tithi_name(panchang["tithi"], lang)))

    return {
        "rashi": rashi, "lang": lang,
        "title": names["rashi"], "latin": names["latin"],
        "date": words.format_date(brief["period"]["start_date"], lang),
        "labels": labels,
        "facts": facts,
        # At most two lines, because a card is read in a second and a half.
        "lines": [_event_line(event, lang) for event in events[:2]],
        "calc": labels["calc"],
    }


def pick_highlight(now: dt.datetime) -> tuple[str, dict] | None:
    """The one rashi whose day has the biggest transit, and the event itself.

    Today's events are usually the SAME transit seen from twelve rashis - one graha turning retrograde is one
    sky - so the choice is not which event but which rashi it lands on hardest: the house it falls in from
    that rashi. Venus turning retrograde in Libra is Libra's news, not Pisces'.

    Deterministic: ties break on the zodiac order, so running this twice on one day gives one answer.
    """
    best = None
    for index, rashi in enumerate(i18n.RASHI_KEYS):
        for event in build_brief(rashi, "today", now).get("events") or []:
            weight = score(event) + HOUSE_WEIGHT.get(event.get("house"), 0)
            if best is None or weight > best[0] or (weight == best[0] and index < best[1]):
                best = (weight, index, rashi, event)
    return (best[2], best[3]) if best else None


def highlight_card(lang: str, now: dt.datetime) -> dict | None:
    chosen = pick_highlight(now)
    if not chosen:
        return None
    rashi, event = chosen
    card = card_for(rashi, lang, now)
    card["kind"] = "highlight"
    card["headline"] = card["labels"]["watch"]
    card["lines"] = [words.describe_event(event, lang)]
    return card


def caption(card: dict, link: str) -> str:
    """The post text: the same facts, the link, the hashtags. Nothing interpretive."""
    head = f"{card['title']} · {card['date']}"
    body = "\n".join(f"• {line}" for line in card["lines"])
    facts = "\n".join(f"• {name}: {value}" for name, value in card["facts"])
    return f"{head}\n\n{body}\n{facts}\n\n{card['calc']}\n{link}\n\n{HASHTAGS[card['lang']]}\n"


def unsafe(text: str) -> list[str]:
    """Anything on this card that must never be on one. Empty is the only acceptable answer."""
    return sorted({match.group(0) for match in FORBIDDEN.finditer(text)})
