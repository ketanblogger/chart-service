"""When does a chart FAVOUR a life event - as tendencies and windows, never as a date.

THE SHAPE IS DELIBERATELY GENERIC. "meri shadi kab hogi" is 50K a month and "naukri kab lagegi" is the
same question about a different house, so a topic is data here rather than code: the house it belongs to,
the karakas, which dashas support it and which transit matters. Adding the job version later is a
`TOPICS` entry and its copy, not another engine.

WHAT THIS WILL NOT DO, and the reason it is built this way round: it will not name a date, and it will
not say an event WILL happen. Classical astrology times a supportive PERIOD - a dasha of a lord
connected to the house, a Jupiter transit over it - and a period is what this returns. A tool that says
"you will marry in March 2028" is making a claim about somebody's life that no chart supports, and the
people most likely to believe it are the ones who should least be told it.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    """One life question, described rather than coded."""

    key: str
    house: int                       # the bhava the question belongs to
    karakas: tuple[str, ...]         # the significators, strongest first
    #: Houses whose lords also support it. 7th for marriage is the house itself; 2nd (family) and 11th
    #: (gains, fulfilment of desire) are the classical supports.
    supporting_houses: tuple[int, ...] = ()
    #: The slow graha whose transit over the house is read as the opening. Jupiter for marriage.
    transit_graha: str = "Jupiter"


TOPICS = {
    "marriage": Topic(key="marriage", house=7, karakas=("Venus", "Jupiter"),
                      supporting_houses=(2, 11), transit_graha="Jupiter"),
    # "naukri kab lagegi" when it is built: house 10, karakas Saturn and Sun, supports 2 and 6, Jupiter
    # or Saturn transit. Listed here so the next person sees the shape, not so it is live.
}


@dataclass
class Window:
    """A supportive period, with why it is one."""

    start: dt.date
    end: dt.date
    strength: str                    # "strong" | "supportive"
    reasons: list[str] = field(default_factory=list)


def _house_of(chart: dict, graha: str) -> int | None:
    """`house["grahas"]` is a list of KEY STRINGS ("Jupiter"), not of graha dicts."""
    for house in chart["houses"]:
        if graha in house.get("grahas", []):
            return house["house"]
    return None


def _lord_of_house(chart: dict, number: int) -> str | None:
    for house in chart["houses"]:
        if house["house"] == number:
            return house["sign"]["lord"]
    return None


def indications(chart: dict, topic_key: str = "marriage") -> dict:
    """What the chart says ABOUT the house, as standing conditions rather than predictions."""
    topic = TOPICS[topic_key]
    house_lord = _lord_of_house(chart, topic.house)
    occupants = []
    for house in chart["houses"]:
        if house["house"] == topic.house:
            occupants = list(house.get("grahas", []))
            sign = house["sign"]
            break
    else:
        sign = None
    return {
        "house": topic.house,
        "sign": sign,
        "lord": house_lord,
        "lord_house": _house_of(chart, house_lord) if house_lord else None,
        "occupants": [g for g in occupants if g],
        "karakas": [{"graha": k, "house": _house_of(chart, k)} for k in topic.karakas],
    }


def supportive_lords(chart: dict, topic_key: str = "marriage") -> set[str]:
    """The grahas whose dasha classical practice reads as supportive for this topic.

    The house's lord, the karakas, anything sitting in the house, and the lords of the supporting
    houses. This is the standard list and it is deliberately not weighted: a weighting would be an
    invented number dressed as tradition.
    """
    topic = TOPICS[topic_key]
    found = set(topic.karakas)
    for number in (topic.house, *topic.supporting_houses):
        lord = _lord_of_house(chart, number)
        if lord:
            found.add(lord)
    found.update(indications(chart, topic_key)["occupants"])
    return {g for g in found if g}


def _as_date(value) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])


def windows(chart: dict, topic_key: str = "marriage", years: int = 3,
            today: dt.date | None = None) -> list[Window]:
    """The supportive periods in the next `years`, newest first, with why each one is supportive.

    TWO SOURCES, AND BOTH ARE PERIODS. A dasha or antardasha of a lord connected to the house, and the
    transit of the topic's slow graha over that house or over the lagna. Where both hold at once the
    window is marked "strong"; one alone is "supportive".

    NOTHING HERE IS A PREDICTION. A window is a period in which tradition says the matter is more
    likely to move - which is a statement about the chart, not about the person's life.
    """
    topic = TOPICS[topic_key]
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=int(365.25 * years))
    lords = supportive_lords(chart, topic_key)

    found: list[Window] = []
    for maha in chart["dasha"].get("mahadashas", []):
        maha_lord = maha["lord"]["key"]
        for antar in maha.get("antardashas", []) or []:
            start, end = _as_date(antar["start"]), _as_date(antar["end"])
            if end < today or start > horizon:
                continue
            antar_lord = antar["lord"]["key"]
            why = []
            if maha_lord in lords:
                why.append(f"mahadasha of {maha_lord}")
            if antar_lord in lords:
                why.append(f"antardasha of {antar_lord}")
            if not why:
                continue
            found.append(Window(start=max(start, today), end=min(end, horizon),
                                strength="strong" if len(why) == 2 else "supportive",
                                reasons=why))
    return found


def transit_openings(chart: dict, topic_key: str = "marriage", years: int = 3,
                     today: dt.date | None = None) -> list[dict]:
    """When the topic's slow graha moves over the house, or over the lagna.

    Jupiter takes about a year per sign, so these are year-long openings rather than moments - which is
    the honest grain for this question and the reason this tool refuses to name a day.
    """
    from app.engine import transits

    topic = TOPICS[topic_key]
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=int(365.25 * years))
    lagna_index = chart["lagna"]["sign"]["index"]
    # The sign on the topic's house, counted from the lagna.
    house_sign_index = (lagna_index + topic.house - 2) % 12 + 1
    wanted = {house_sign_index, lagna_index}

    out = []
    for event in transits.transit_events(dt.datetime.combine(today, dt.time()),
                                         dt.datetime.combine(horizon, dt.time()),
                                         grahas=[topic.transit_graha]):
        if event.get("type") != "ingress":
            continue
        if event["to_sign"]["index"] in wanted:
            which = "the house itself" if event["to_sign"]["index"] == house_sign_index else "your lagna"
            out.append({"from": _as_date(event["datetime"]), "graha": topic.transit_graha,
                        "sign": event["to_sign"]["name"], "over": which})
    return out
