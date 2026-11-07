"""Ashtakoota guna milan (8 kootas, 36 points) from the two Moon longitudes.

North Indian Ashtakoota as used by mainstream kundali software. Varna, Vashya and Gana are
directional (groom vs bride); the rest are symmetric. Regional texts differ slightly in the
Vashya and Gana tables - the widely published versions are used here.
"""

from . import namakshar
from .constants import NAKSHATRA_SPAN, PADA_SPAN, nakshatra_info, sign_info, sign_lord

# --- Varna (1): by Moon sign element. Groom's varna should be equal or higher. -----------
_VARNA_RANK = {"Brahmin": 4, "Kshatriya": 3, "Vaishya": 2, "Shudra": 1}
_VARNA_BY_SIGN = ["Kshatriya", "Vaishya", "Shudra", "Brahmin"] * 3  # fire, earth, air, water

# --- Vashya (2): by Moon sign; Sagittarius and Capricorn split at 15°. -------------------
_VASHYA_BY_SIGN = [
    "Chatushpada", "Chatushpada", "Manava", "Jalachara", "Vanachara", "Manava",
    "Manava", "Keeta", None, None, "Manava", "Jalachara",
]
_VASHYA_POINTS = {  # [groom][bride]
    "Chatushpada": {"Chatushpada": 2, "Manava": 1, "Jalachara": 1, "Vanachara": 0.5, "Keeta": 1},
    "Manava": {"Chatushpada": 1, "Manava": 2, "Jalachara": 0.5, "Vanachara": 0, "Keeta": 1},
    "Jalachara": {"Chatushpada": 1, "Manava": 0.5, "Jalachara": 2, "Vanachara": 1, "Keeta": 1},
    "Vanachara": {"Chatushpada": 0, "Manava": 0, "Jalachara": 0, "Vanachara": 2, "Keeta": 0},
    "Keeta": {"Chatushpada": 1, "Manava": 1, "Jalachara": 1, "Vanachara": 0, "Keeta": 2},
}

# --- Yoni (4): by nakshatra. ---------------------------------------------------------------
_YONI_ANIMALS = [
    "Horse", "Elephant", "Sheep", "Serpent", "Dog", "Cat", "Rat",
    "Cow", "Buffalo", "Tiger", "Deer", "Monkey", "Mongoose", "Lion",
]
_YONI_BY_NAKSHATRA = [
    "Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat", "Sheep", "Cat",
    "Rat", "Rat", "Cow", "Buffalo", "Tiger", "Buffalo", "Tiger", "Deer", "Deer",
    "Dog", "Monkey", "Mongoose", "Monkey", "Lion", "Horse", "Lion", "Cow", "Elephant",
]
_YONI_POINTS = [  # symmetric; rows/columns in _YONI_ANIMALS order
    [4, 2, 2, 3, 2, 2, 2, 1, 0, 1, 3, 3, 2, 1],
    [2, 4, 3, 3, 2, 2, 2, 2, 3, 1, 2, 3, 2, 0],
    [2, 3, 4, 2, 1, 2, 1, 3, 3, 1, 2, 0, 3, 1],
    [3, 3, 2, 4, 2, 1, 1, 1, 1, 2, 2, 2, 0, 2],
    [2, 2, 1, 2, 4, 2, 1, 2, 2, 1, 0, 2, 1, 1],
    [2, 2, 2, 1, 2, 4, 0, 2, 2, 1, 3, 3, 2, 1],
    [2, 2, 1, 1, 1, 0, 4, 2, 2, 2, 2, 2, 1, 2],
    [1, 2, 3, 1, 2, 2, 2, 4, 3, 0, 3, 2, 2, 1],
    [0, 3, 3, 1, 2, 2, 2, 3, 4, 1, 2, 2, 2, 1],
    [1, 1, 1, 2, 1, 1, 2, 0, 1, 4, 1, 1, 2, 1],
    [3, 2, 2, 2, 0, 3, 2, 3, 2, 1, 4, 2, 2, 1],
    [3, 3, 0, 2, 2, 3, 2, 2, 2, 1, 2, 4, 3, 2],
    [2, 2, 3, 0, 1, 2, 1, 2, 2, 2, 2, 3, 4, 2],
    [1, 0, 1, 2, 1, 1, 2, 1, 1, 1, 1, 2, 2, 4],
]

# --- Graha maitri (5): natural friendship between the two Moon-sign lords. -----------------
_FRIENDS = {
    "Sun": {"Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
_ENEMIES = {
    "Sun": {"Venus", "Saturn"},
    "Moon": set(),
    "Mars": {"Mercury"},
    "Mercury": {"Moon"},
    "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon"},
    "Saturn": {"Sun", "Moon", "Mars"},
}
_MAITRI_POINTS = {
    ("friend", "friend"): 5, ("friend", "neutral"): 4, ("neutral", "neutral"): 3,
    ("enemy", "friend"): 1, ("enemy", "neutral"): 0.5, ("enemy", "enemy"): 0,
}

# --- Gana (6): by nakshatra. ---------------------------------------------------------------
_GANA_CYCLE = {"D": "Deva", "M": "Manushya", "R": "Rakshasa"}
_GANA_BY_NAKSHATRA = [_GANA_CYCLE[c] for c in "DMRMDMDDRRMMDRDRDRRMMDRRMMD"]
_GANA_POINTS = {  # [groom][bride]
    "Deva": {"Deva": 6, "Manushya": 6, "Rakshasa": 0},
    "Manushya": {"Deva": 5, "Manushya": 6, "Rakshasa": 0},
    "Rakshasa": {"Deva": 1, "Manushya": 0, "Rakshasa": 6},
}

# --- Nadi (8): by nakshatra, repeating Aadi-Madhya-Antya-Antya-Madhya-Aadi. ----------------
_NADI_CYCLE = ["Aadi", "Madhya", "Antya", "Antya", "Madhya", "Aadi"]

MAX_POINTS = {"varna": 1, "vashya": 2, "tara": 3, "yoni": 4, "graha_maitri": 5, "gana": 6, "bhakoot": 7, "nadi": 8}


def _vashya(longitude: float) -> str:
    sign, degree = int(longitude // 30), longitude % 30
    if sign == 8:  # Sagittarius: human first half, quadruped second half
        return "Manava" if degree < 15 else "Chatushpada"
    if sign == 9:  # Capricorn: quadruped first half, aquatic second half
        return "Chatushpada" if degree < 15 else "Jalachara"
    return _VASHYA_BY_SIGN[sign]


def _relation(lord: str, other: str) -> str:
    if other == lord or other in _FRIENDS[lord]:
        return "friend"
    return "enemy" if other in _ENEMIES[lord] else "neutral"


def _tara_is_auspicious(from_nakshatra: int, to_nakshatra: int) -> bool:
    count = (to_nakshatra - from_nakshatra) % 27 + 1  # inclusive count
    return count % 9 not in (3, 5, 7)  # vipat, pratyari, vadha


def _profile(longitude: float, vashya: str | None = None) -> dict:
    sign, nakshatra = int(longitude // 30), int(longitude // NAKSHATRA_SPAN)
    return {
        "moon_sign": sign_info(sign),
        "moon_nakshatra": nakshatra_info(nakshatra),
        "varna": _VARNA_BY_SIGN[sign],
        "vashya": vashya or _vashya(longitude),
        "yoni": _YONI_BY_NAKSHATRA[nakshatra],
        "sign_lord": sign_lord(sign),
        "gana": _GANA_BY_NAKSHATRA[nakshatra],
        "nadi": _NADI_CYCLE[nakshatra % 6],
    }


def ashtakoota(boy_moon_longitude: float, girl_moon_longitude: float,
               boy_vashya: str | None = None, girl_vashya: str | None = None) -> dict:
    """`*_vashya` override the class read from the longitude (by-name matching, where a pada can straddle 15 deg)."""
    boy_lon, girl_lon = boy_moon_longitude % 360, girl_moon_longitude % 360
    boy, girl = _profile(boy_lon, boy_vashya), _profile(girl_lon, girl_vashya)
    boy_sign, girl_sign = boy["moon_sign"]["index"], girl["moon_sign"]["index"]
    boy_nak, girl_nak = boy["moon_nakshatra"]["index"], girl["moon_nakshatra"]["index"]

    relations = tuple(sorted((_relation(boy["sign_lord"], girl["sign_lord"]),
                              _relation(girl["sign_lord"], boy["sign_lord"]))))
    sign_distance = (girl_sign - boy_sign) % 12 + 1  # girl's sign counted from boy's
    bhakoot_dosha = sign_distance in (2, 12, 5, 9, 6, 8)
    nadi_dosha = boy["nadi"] == girl["nadi"]

    scores = {
        "varna": 1 if _VARNA_RANK[boy["varna"]] >= _VARNA_RANK[girl["varna"]] else 0,
        "vashya": _VASHYA_POINTS[boy["vashya"]][girl["vashya"]],
        "tara": 1.5 * _tara_is_auspicious(girl_nak, boy_nak) + 1.5 * _tara_is_auspicious(boy_nak, girl_nak),
        "yoni": _YONI_POINTS[_YONI_ANIMALS.index(boy["yoni"])][_YONI_ANIMALS.index(girl["yoni"])],
        "graha_maitri": _MAITRI_POINTS[relations],
        "gana": _GANA_POINTS[boy["gana"]][girl["gana"]],
        "bhakoot": 0 if bhakoot_dosha else 7,
        "nadi": 0 if nadi_dosha else 8,
    }
    values = {
        "varna": (boy["varna"], girl["varna"]),
        "vashya": (boy["vashya"], girl["vashya"]),
        "tara": (boy["moon_nakshatra"]["name"], girl["moon_nakshatra"]["name"]),
        "yoni": (boy["yoni"], girl["yoni"]),
        "graha_maitri": (boy["sign_lord"], girl["sign_lord"]),
        "gana": (boy["gana"], girl["gana"]),
        "bhakoot": (boy["moon_sign"]["name"], girl["moon_sign"]["name"]),
        "nadi": (boy["nadi"], girl["nadi"]),
    }
    total = sum(scores.values())
    return {
        "boy": boy,
        "girl": girl,
        "kootas": [
            {"koota": name, "boy": values[name][0], "girl": values[name][1],
             "score": scores[name], "max": MAX_POINTS[name]}
            for name in MAX_POINTS
        ],
        "total": total,
        "max_total": 36,
        "percentage": round(total / 36 * 100, 1),
        # Conventional bands: below 18 not recommended, 18-24 average, 25-32 good, 33+ excellent.
        "verdict": "excellent" if total >= 33 else "good" if total >= 25 else "average" if total >= 18 else "below_average",
        "doshas": {
            "nadi_dosha": {
                "present": nadi_dosha,
                # Same rashi with different nakshatras, or same nakshatra with different rashis.
                "cancellation_applies": nadi_dosha and (boy_sign == girl_sign) != (boy_nak == girl_nak),
            },
            "bhakoot_dosha": {
                "present": bhakoot_dosha,
                "sign_distance": [sign_distance, (boy_sign - girl_sign) % 12 + 1],
                # Moon-sign lords being the same graha or mutual friends.
                "cancellation_applies": bhakoot_dosha and relations == ("friend", "friend"),
            },
        },
    }


def match_charts(boy_chart: dict, girl_chart: dict) -> dict:
    """Guna milan plus Mangal dosha comparison, from two charts built by `compute_chart`."""
    result = ashtakoota(boy_chart["grahas"]["Moon"]["longitude"], girl_chart["grahas"]["Moon"]["longitude"])
    boy_dosha, girl_dosha = boy_chart["mangal_dosha"], girl_chart["mangal_dosha"]
    result["mangal_dosha"] = {
        "boy": boy_dosha,
        "girl": girl_dosha,
        # Traditionally fine when both have it (mutual cancellation) or neither does.
        "compatible": boy_dosha["present"] == girl_dosha["present"],
    }
    return result


def _vashya_options(longitude: float) -> list[str]:
    """Vashya class(es) of the pada whose midpoint is `longitude`. Sagittarius and Capricorn change class at
    15 deg, and exactly two padas straddle that point (Purvashadha 1, Shravana 2): they get both classes,
    the one the pada begins in first."""
    start, end = longitude - PADA_SPAN / 2, longitude + PADA_SPAN / 2 - 1e-9
    options = [_vashya(start)]
    if _vashya(end) != options[0]:
        options.append(_vashya(end))
    return options


def match_names(boy_name: str, girl_name: str, boy_syllable: str | None = None, girl_syllable: str | None = None) -> dict:
    """Guna milan from two names (Avakahada chakra). Same shape as `ashtakoota`, plus `basis`, `note`, each
    person's `pada`, `input` and `name_match`; `mangal_dosha` is null (it needs a birth chart).
    Raises namakshar.NameError_ (a ValueError) for a name with no readable first syllable."""
    people = {"boy": namakshar.from_name(boy_name, boy_syllable), "girl": namakshar.from_name(girl_name, girl_syllable)}
    options = {who: _vashya_options(person["longitude"]) for who, person in people.items()}
    result = ashtakoota(people["boy"]["longitude"], people["girl"]["longitude"], options["boy"][0], options["girl"][0])
    alternatives = sorted({
        ashtakoota(people["boy"]["longitude"], people["girl"]["longitude"], boy_class, girl_class)["total"]
        for boy_class in options["boy"] for girl_class in options["girl"]
    })
    for who, person in people.items():
        result[who]["pada"] = person["pada"]
        result[who]["input"] = {"name": person["name"]}
        result[who]["name_match"] = {key: person[key] for key in
                                     ("read_as", "script", "syllable", "latin", "confidence", "rules")}
        result[who]["name_match"]["candidates"] = [
            {key: candidate[key] for key in ("syllable", "latin", "nakshatra", "pada", "moon_sign")}
            for candidate in person["candidates"]
        ]
        result[who]["name_match"]["vashya_options"] = options[who]
    result["basis"] = "name"
    result["note"] = namakshar.NOTE
    # Only when a pada straddles the 15-degree vashya boundary can the total differ (by at most 2 points).
    result["total_range"] = [alternatives[0], alternatives[-1]]
    result["mangal_dosha"] = None
    return result
