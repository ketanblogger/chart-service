"""When Hindu wedding muhurats pause, computed - and the matching offer that rides on it.

THE ONE CLAIM THIS MAKES is the one our own engine can settle exactly: the Sun's sidereal ingress into
Dhanu, which begins Dhanurmas (Kharmas), and its ingress into Makara at Makar Sankranti, which ends it.
Weddings are not solemnised in between. Both are transits - a degree crossing, computed with the same
Swiss Ephemeris and Lahiri ayanamsa as everything else on this site - so the dates are arithmetic rather
than opinion, and they move correctly every year without anybody editing a list.

WHAT IT DELIBERATELY DOES NOT CLAIM. The wedding season also pauses through Chaturmas, which runs from
Devshayani Ekadashi to Prabodhini Ekadashi. Those are TITHI dates, and in 2026 the Kartika shukla
Ekadashi is kshaya - it is never the tithi at sunrise (20 Nov is Dashami, 21 Nov is Dwadashi) - so which
day the vrata falls on is a question of observance, and different panchangs answer it differently. This
module says nothing about it rather than picking one and printing it as a fact.

Adding it is about fifteen lines, and the thing to settle first is which convention to follow when a
tithi is kshaya - that is a decision about doctrine, not about code.

So the block says: muhurats pause on <date>, or they resume on <date>. Nothing about auspiciousness,
nothing about anybody's chart, and no claim that a wedding outside the window is forbidden.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

#: Sidereal longitudes: Dhanu begins at 240 degrees, Makara at 270.
DHANU_START = 240.0
MAKARA_START = 270.0

#: How far ahead the block starts mentioning the pause. Six weeks is about as long as a wedding is
#: realistically being arranged in, and far enough out that matching is still worth doing first.
NOTICE_DAYS = 42


def _crossing(degrees: float, after: dt.datetime, before: dt.datetime) -> dt.datetime | None:
    from app.engine import transits
    from app.engine.core import julian_day

    hits = transits.degree_crossings("Sun", degrees, julian_day(after), julian_day(before))
    return transits.from_julian_day(hits[0]).astimezone(IST) if hits else None


@lru_cache(maxsize=8)
def _boundaries(year: int) -> tuple[dt.datetime | None, dt.datetime | None]:
    """(Sun into Dhanu this December, Sun into Makara next January), both IST.

    Cached per year because a degree crossing is a bisection over the ephemeris and this is read on
    every matching page view; the answer changes once a year.
    """
    pause = _crossing(DHANU_START, dt.datetime(year, 11, 20, tzinfo=dt.timezone.utc),
                      dt.datetime(year, 12, 31, tzinfo=dt.timezone.utc))
    resume = _crossing(MAKARA_START, dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc),
                       dt.datetime(year + 1, 2, 10, tzinfo=dt.timezone.utc))
    return pause, resume


def state(today: dt.date | None = None) -> dict | None:
    """What to say today, or None when there is nothing worth saying.

    Three answers: the pause is coming and is close enough to matter ("closing"), the Sun is in Dhanu
    now ("paused"), or neither - in which case this returns None and the page shows nothing. A seasonal
    block that is always on the page is not seasonal, it is furniture.
    """
    today = today or dt.datetime.now(IST).date()
    pause, resume = _boundaries(today.year if today.month > 2 else today.year - 1)
    if pause is None or resume is None:
        return None                      # the ephemeris could not answer: say nothing at all
    pause_day, resume_day = pause.date(), resume.date()
    if pause_day <= today < resume_day:
        return {"phase": "paused", "pause_on": pause_day, "resume_on": resume_day,
                "days": (resume_day - today).days}
    days = (pause_day - today).days
    if 0 < days <= NOTICE_DAYS:
        return {"phase": "closing", "pause_on": pause_day, "resume_on": resume_day, "days": days}
    return None


#: What the block says, per language and per phase. {date} is the ingress date in the reader's language
#: and {days} the count to it. The wording states a TRANSIT and a consequence people already know - it
#: does not tell anybody their wedding is auspicious, which is not a thing a transit can say.
COPY = {
    "en": {
        "closing_heading": "Wedding muhurats pause on {date}",
        "closing_text": "{days} days from today. The Sun enters Dhanu then and weddings are not "
                        "solemnised until it reaches Makara on {resume}. If a match is still to be "
                        "checked, it is worth doing before the dates are set.",
        "paused_heading": "Wedding muhurats resume on {resume}",
        "paused_text": "The Sun is in Dhanu until then - {days} days - so this is the month families "
                       "use to settle the match itself.",
        "cta": "Check kundli matching free",
    },
    "hi": {
        "closing_heading": "विवाह मुहूर्त {date} को थम जाएंगे",
        "closing_text": "आज से {days} दिन। उस दिन सूर्य धनु में प्रवेश करता है और {resume} को मकर में "
                        "पहुंचने तक विवाह नहीं होते। मिलान अभी बाकी है तो तारीख़ तय होने से पहले कर लेना "
                        "ठीक रहता है।",
        "paused_heading": "विवाह मुहूर्त {resume} से फिर शुरू",
        "paused_text": "तब तक सूर्य धनु में है - {days} दिन - इसलिए यही महीना परिवार मिलान तय करने में "
                       "लगाते हैं।",
        "cta": "कुंडली मिलान मुफ़्त देखें",
    },
    "mr": {
        "closing_heading": "विवाह मुहूर्त {date} रोजी थांबतात",
        "closing_text": "आजपासून {days} दिवस. त्या दिवशी सूर्य धनु राशीत जातो आणि {resume} रोजी मकरेत "
                        "येईपर्यंत विवाह होत नाहीत. पत्रिका जुळवायची असेल तर तारखा ठरण्याआधी करून घेणे "
                        "बरे.",
        "paused_heading": "विवाह मुहूर्त {resume} पासून पुन्हा सुरू",
        "paused_text": "तोपर्यंत सूर्य धनु राशीत आहे - {days} दिवस - म्हणून हाच महिना कुटुंबे पत्रिका "
                       "जुळवण्यात घालवतात.",
        "cta": "मोफत पत्रिका जुळवणी पाहा",
    },
}


def block(lang: str, today: dt.date | None = None) -> dict | None:
    """The block a template renders, or None when there is nothing to say today."""
    from app.rashifal import i18n as date_words

    now = state(today)
    if now is None:
        return None
    text = COPY.get(lang, COPY["en"])
    phase = now["phase"]
    values = {"date": date_words.format_date(now["pause_on"].isoformat(), lang),
              "resume": date_words.format_date(now["resume_on"].isoformat(), lang),
              "days": now["days"]}
    return {"phase": phase,
            "heading": text[f"{phase}_heading"].format(**values),
            "text": text[f"{phase}_text"].format(**values),
            "cta": text["cta"]}
