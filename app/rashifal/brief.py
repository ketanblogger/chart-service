"""The "transit brief": every fact a rashifal may state, computed by the engine for one (rashi, period).

The AI interprets this JSON and nothing else - it never calculates - and the fallback page prints it as
tables, so it
must already contain whatever a writer would be tempted to work out: the whole-sign house of every graha
counted from the rashi, dated sign changes and retrograde stations inside the window, how long each slow
graha stays where, the Moon's course for short periods, Saturn's sade-sati / dhaiya status, and for the
daily page the panchang basics and the day's colour and number.

This module only SELECTS and ARRANGES engine output. The single rule it adds is the "lucky" pair, which is
deterministic and stated on the page (see `_lucky`). No swisseph access here - that stays in app/engine.
"""

import datetime as dt
import hashlib
import json
from functools import lru_cache

from app import engine
from app.engine.constants import graha_name, sign_info
from .i18n import graha_name as _mr_graha, rashi_name as _mr_rashi

from .periods import PERIOD_SLUGS, Window, rashi_index, window_for

BRIEF_VERSION = 2  # bump when the shape changes; part of the hash, so stored pages regenerate

_SLOW = ("Jupiter", "Saturn", "Rahu", "Ketu")
# 6-month / yearly windows list every ingress of these; Mercury / Venus sign changes are kept only in the monthly
# brief (their stations are always kept), which keeps the yearly brief readable and cheap.
_LONG_INGRESS = ("Sun", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu")
_CHANDRA_BALA_GOOD = {1, 3, 6, 7, 10, 11}  # Moon's transit house from the janma rashi: classical favourable set

# Traditional graha colour / number pairs (only the seven sign- and day-lords are needed).
_GRAHA_COLOUR = {
    "Sun": ("orange", 1), "Moon": ("white", 2), "Mars": ("red", 9), "Mercury": ("green", 5),
    "Jupiter": ("yellow", 3), "Venus": ("cream", 6), "Saturn": ("dark-blue", 8),
}
COLOUR_NAMES = {
    "orange": {"en": "Orange", "mr": "केशरी", "hi": "केसरिया"},
    "white": {"en": "White", "mr": "पांढरा", "hi": "सफ़ेद"},
    "red": {"en": "Red", "mr": "लाल", "hi": "लाल"},
    "green": {"en": "Green", "mr": "हिरवा", "hi": "हरा"},
    "yellow": {"en": "Yellow", "mr": "पिवळा", "hi": "पीला"},
    "cream": {"en": "Cream", "mr": "क्रीम", "hi": "क्रीम"},
    "dark-blue": {"en": "Dark blue", "mr": "गडद निळा", "hi": "गहरा नीला"},
}


_GRAHA_KEYS = {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"}
_SIGN_KEYS = {sign_info(i)["key"] for i in range(12)}


def _with_marathi(node):
    """Add `devanagari_mr` to every graha and sign in the brief whose Marathi spelling differs from the one
    the engine carries.

    The engine stores ONE Devanagari spelling and it is the Hindi one - मंगल, शनि, गुरु, राहु, केतु, तुला -
    where Marathi writes मंगळ, शनी, गुरू, राहू, केतू, तूळ. The web pages and the PDF have always gone through
    i18n.graha_name / rashi_name for this; the AI brief did not. So the prompt told the model to take graha
    and sign names from the brief's `devanagari` fields, and the brief handed it Hindi - which is where the
    मंगल and गुरु in the live Marathi readings came from. The model was obeying us.

    Done as a walk of the finished brief rather than at each site that carries a graha, so a fact added
    later cannot quietly miss it. Nakshatras and tithis are left alone: Marathi spells those as Hindi does.
    """
    if isinstance(node, list):
        return [_with_marathi(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: _with_marathi(value) for key, value in node.items()}
    devanagari = out.get("devanagari")
    if isinstance(devanagari, str):
        if out.get("key") in _SIGN_KEYS and isinstance(out.get("index"), int):
            marathi = _mr_rashi(out["index"], "mr")
        elif out.get("key") in _GRAHA_KEYS:
            marathi = _mr_graha(node, "mr")
        else:
            marathi = devanagari
        if marathi != devanagari:
            out["devanagari_mr"] = marathi
    return out


def _sign(sign: dict) -> dict:
    return {k: sign[k] for k in ("index", "key", "name", "devanagari", "lord")}


def _nakshatra(nakshatra: dict) -> dict:
    return {k: nakshatra[k] for k in ("name", "devanagari", "lord")}


def _chandra_bala(house: int) -> dict:
    return {"moon_house_from_rashi": house, "favourable": house in _CHANDRA_BALA_GOOD}


def _position(entry: dict) -> dict:
    return {
        "graha": entry["graha"],
        "sign": _sign(entry["sign"]),
        "nakshatra": _nakshatra(entry["nakshatra"]),
        "house": entry["house"],
        "retrograde": entry["retrograde"],
    }


def _event(number: int, raw: dict, rashi_name: str) -> dict:
    moment = raw["datetime"]  # IST, minutes precision: 2026-09-22T07:07+05:30
    event = {"id": f"e{number}", "date": moment[:10], "time_ist": moment[11:16], "type": raw["type"], "graha": raw["graha"]}
    if raw["type"] == "ingress":
        event.update(from_sign=_sign(raw["from_sign"]), to_sign=_sign(raw["to_sign"]), house=raw["house"],
                     retrograde_entry=raw["retrograde"])
        if raw["graha"]["key"] == "Moon":
            event["chandra_bala"] = _chandra_bala(raw["house"])
        # Said once more in plain words: models otherwise slip into the natural zodiac (Tula = "7th") instead of
        # the house counted from this rashi. Seen live with two different models on the same page.
        event["in_words"] = (f"{raw['graha']['name']} enters {raw['to_sign']['name']} ({raw['to_sign']['key']}), which is house "
                             f"{raw['house']} counted from {rashi_name} - not house {raw['to_sign']['index']}"
                             if raw["house"] != raw["to_sign"]["index"] else
                             f"{raw['graha']['name']} enters {raw['to_sign']['name']} ({raw['to_sign']['key']}), house {raw['house']} from {rashi_name}")
    else:
        event.update(direction=raw["direction"], sign=_sign(raw["sign"]), nakshatra=_nakshatra(raw["nakshatra"]),
                     house=raw["house"])
    return event


def _stays(positions: dict, events: list[dict], window: Window) -> list[dict]:
    """For each slow graha: the stretches it spends in one sign inside the window, with the house."""
    stays = []
    for key in _SLOW:
        start = positions[key]
        current = {"graha": start["graha"], "sign": _sign(start["sign"]), "house": start["house"],
                   "from": window.start_date.isoformat()}
        for event in events:
            if event["type"] == "ingress" and event["graha"]["key"] == key:
                stays.append({**current, "to": event["date"]})
                current = {"graha": event["graha"], "sign": event["to_sign"], "house": event["house"], "from": event["date"]}
        stays.append({**current, "to": window.end_date.isoformat()})
    return stays


def _saturn(rashi: int, window: Window, long_period: bool) -> dict:
    as_of = window.start.astimezone(dt.timezone.utc)
    sade_sati = engine.sade_sati(rashi, as_of)
    cycle = sade_sati["cycle"]
    current = next((p for p in cycle["periods"] if p["start"] <= sade_sati["as_of"] < p["end"]), None)
    slim = {
        "active": sade_sati["active"],
        "phase": sade_sati["phase"],
        "current_phase_period": current,
        "cycle": {"which": cycle["which"], "start": cycle["start"], "end": cycle["end"]},
    }
    if long_period:
        slim["cycle"]["periods"] = cycle["periods"]
    dhaiya = engine.dhaiya(rashi, as_of)
    return {
        "as_of": sade_sati["as_of"],
        "saturn_sign": _sign(sade_sati["saturn_sign"]),
        "saturn_house_from_moon": sade_sati["saturn_house_from_moon"],
        "sade_sati": slim,
        "dhaiya": {"active": dhaiya["active"], "kind": dhaiya["kind"], "period": dhaiya["period"]},
    }


def _lucky(rashi: int, vara: dict, chandra_bala: dict) -> dict:
    """The day's colour and number. Deterministic rule, printed on the page:

    when the Moon's transit house from the rashi is favourable (chandra bala), follow the lord of the
    weekday; otherwise lean on the rashi's own lord. Colour and number are that graha's traditional pair.
    """
    if chandra_bala["favourable"]:
        lord, basis = vara["lord"]["key"], "day_lord"
    else:
        lord, basis = sign_info(rashi - 1)["lord"], "rashi_lord"
    colour, number = _GRAHA_COLOUR[lord]
    return {"colour": {"key": colour, **COLOUR_NAMES[colour]}, "number": number, "basis": basis, "graha": graha_name(lord)}


def build_brief(rashi_slug: str, period: str, moment: dt.datetime | None = None) -> dict:
    """The transit brief for `rashi_slug` (exact URL slug) and `period`, for the window containing `moment`."""
    window = window_for(period, moment)
    return _build(rashi_slug, period, window.key)


@lru_cache(maxsize=256)
def _build_cached(rashi_slug: str, period: str, window_key: str) -> str:
    rashi = rashi_index(rashi_slug)
    window = window_for(period, dt.datetime.fromisoformat(window_key))
    short = period in ("today", "weekly")

    transits = engine.current_transits(window.start, rashi=rashi)
    positions = transits["grahas"]
    raw_events = engine.transit_events(window.start, window.end, rashi=rashi, include_moon=short)  # a month is <= 31 days: say so
    if period in ("6-months", "yearly"):
        raw_events = [e for e in raw_events if e["type"] == "station" or e["graha"]["key"] in _LONG_INGRESS]
    rashi_name = sign_info(rashi - 1)["name"]
    events = [_event(n, raw, rashi_name) for n, raw in enumerate(raw_events, 1)]

    brief = {
        "version": BRIEF_VERSION,
        "kind": "transit brief for a Moon sign (janma rashi) - general reading, not a birth chart",
        "rashi": _sign(sign_info(rashi - 1)),
        "period": {
            "slug": period,
            "start_date": window.start_date.isoformat(),
            "end_date": window.end_date.isoformat(),
            "days": window.days,
            "timezone": "Asia/Kolkata (IST)",
        },
        "houses_are": "whole-sign houses counted from the rashi (the rashi itself is house 1)",
        "positions_at_start": [_position(entry) for key, entry in positions.items() if short or key != "Moon"],
        "events": events,
        "saturn": _saturn(rashi, window, long_period=not short),
    }
    if short:
        moon = positions["Moon"]
        brief["moon_at_start"] = {
            "graha": moon["graha"], "sign": _sign(moon["sign"]), "nakshatra": _nakshatra(moon["nakshatra"]),
            "house": moon["house"], "chandra_bala": _chandra_bala(moon["house"]),
        }
    else:
        brief["slow_graha_stays"] = _stays(positions, events, window)
    if period == "today":
        panchang = engine.panchang(window.start_date)
        brief["panchang"] = panchang
        # Chandra bala for the day is read where the panchang reads everything else: at sunrise.
        at_sunrise = engine.current_transits(dt.datetime.fromisoformat(panchang["sunrise"]), rashi=rashi)["grahas"]["Moon"]
        brief["moon_at_sunrise"] = {
            "graha": at_sunrise["graha"], "sign": _sign(at_sunrise["sign"]), "house": at_sunrise["house"],
            "chandra_bala": _chandra_bala(at_sunrise["house"]),
        }
        brief["lucky"] = _lucky(rashi, panchang["vara"], brief["moon_at_sunrise"]["chandra_bala"])
    return json.dumps(_with_marathi(brief), ensure_ascii=False, sort_keys=True)


def _build(rashi_slug: str, period: str, window_key: str) -> dict:
    if period not in PERIOD_SLUGS:
        raise ValueError(f"unknown period {period!r}")
    return json.loads(_build_cached(rashi_slug, period, window_key))  # a fresh dict each time: callers may mutate


def brief_hash(brief: dict) -> str:
    return hashlib.sha256(json.dumps(brief, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
