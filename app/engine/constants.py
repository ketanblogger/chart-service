"""Static reference data: signs, nakshatras, grahas. No calculation here."""

# (English key, Sanskrit name, Devanagari, lord)
_SIGNS = [
    ("Aries", "Mesha", "मेष", "Mars"),
    ("Taurus", "Vrishabha", "वृषभ", "Venus"),
    ("Gemini", "Mithuna", "मिथुन", "Mercury"),
    ("Cancer", "Karka", "कर्क", "Moon"),
    ("Leo", "Simha", "सिंह", "Sun"),
    ("Virgo", "Kanya", "कन्या", "Mercury"),
    ("Libra", "Tula", "तुला", "Venus"),
    ("Scorpio", "Vrishchika", "वृश्चिक", "Mars"),
    ("Sagittarius", "Dhanu", "धनु", "Jupiter"),
    ("Capricorn", "Makara", "मकर", "Saturn"),
    ("Aquarius", "Kumbha", "कुंभ", "Saturn"),
    ("Pisces", "Meena", "मीन", "Jupiter"),
]

# (name, Devanagari). Vimshottari lord follows from index % 9 (see DASHA_SEQUENCE).
_NAKSHATRAS = [
    ("Ashwini", "अश्विनी"),
    ("Bharani", "भरणी"),
    ("Krittika", "कृत्तिका"),
    ("Rohini", "रोहिणी"),
    ("Mrigashira", "मृगशीर्ष"),
    ("Ardra", "आर्द्रा"),
    ("Punarvasu", "पुनर्वसु"),
    ("Pushya", "पुष्य"),
    ("Ashlesha", "आश्लेषा"),
    ("Magha", "मघा"),
    ("Purva Phalguni", "पूर्वा फाल्गुनी"),
    ("Uttara Phalguni", "उत्तरा फाल्गुनी"),
    ("Hasta", "हस्त"),
    ("Chitra", "चित्रा"),
    ("Swati", "स्वाती"),
    ("Vishakha", "विशाखा"),
    ("Anuradha", "अनुराधा"),
    ("Jyeshtha", "ज्येष्ठा"),
    ("Mula", "मूल"),
    ("Purvashadha", "पूर्वाषाढा"),
    ("Uttarashadha", "उत्तराषाढा"),
    ("Shravana", "श्रवण"),
    ("Dhanishta", "धनिष्ठा"),
    ("Shatabhisha", "शतभिषा"),
    ("Purva Bhadrapada", "पूर्वा भाद्रपदा"),
    ("Uttara Bhadrapada", "उत्तरा भाद्रपदा"),
    ("Revati", "रेवती"),
]

# English key -> (Sanskrit name, Devanagari). Order is the conventional graha order.
_GRAHAS = {
    "Sun": ("Surya", "सूर्य"),
    "Moon": ("Chandra", "चंद्र"),
    "Mars": ("Mangal", "मंगल"),
    "Mercury": ("Budha", "बुध"),
    "Jupiter": ("Guru", "गुरु"),
    "Venus": ("Shukra", "शुक्र"),
    "Saturn": ("Shani", "शनि"),
    "Rahu": ("Rahu", "राहु"),
    "Ketu": ("Ketu", "केतु"),
}

GRAHA_KEYS = list(_GRAHAS)

# Vimshottari order and mahadasha lengths in years (total 120).
DASHA_SEQUENCE = [
    ("Ketu", 7), ("Venus", 20), ("Sun", 6), ("Moon", 10), ("Mars", 7),
    ("Rahu", 18), ("Jupiter", 16), ("Saturn", 19), ("Mercury", 17),
]

NAKSHATRA_SPAN = 360 / 27  # 13°20'
PADA_SPAN = NAKSHATRA_SPAN / 4  # 3°20'

# The platform's three output languages, and THE month-name table for all of them. The engine owns
# date formatting for the whole platform (one formatter = the same printed range in the book, the
# tables and the debug markdown), so this table is canonical: app/pdf/labels.py, app/rashifal/i18n.py
# and app/ai/engine_facts.py each carry a copy and should read this one instead.
# English is short-form, as the book prints it ("Jan 2028 - May 2028"); Devanagari
# has no conventional short form, so hi/mr use the full name. Years and days are ALWAYS Latin digits.
LANGUAGES = ("en", "hi", "mr")
MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "hi": ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
           "नवंबर", "दिसंबर"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर",
           "नोव्हेंबर", "डिसेंबर"],
}


def graha_name(key: str) -> dict:
    name, devanagari = _GRAHAS[key]
    return {"key": key, "name": name, "devanagari": devanagari}


def sign_info(index: int) -> dict:
    key, name, devanagari, lord = _SIGNS[index]
    return {
        "index": index + 1,  # 1 = Aries/Mesha ... 12 = Pisces/Meena
        "key": key,
        "name": name,
        "devanagari": devanagari,
        "slug": name.lower(),
        "lord": lord,
    }


def nakshatra_info(index: int) -> dict:
    name, devanagari = _NAKSHATRAS[index]
    return {
        "index": index + 1,  # 1 = Ashwini ... 27 = Revati
        "key": name,
        "name": name,
        "devanagari": devanagari,
        "lord": DASHA_SEQUENCE[index % 9][0],
    }


def sign_lord(index: int) -> str:
    return _SIGNS[index][3]


def resolve_sign(value: int | str) -> int:
    """Accept 1-12, an English key ("Leo"), Sanskrit name or slug ("simha"). Returns 0-based index."""
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        number = int(value)
        if 1 <= number <= 12:
            return number - 1
        raise ValueError(f"sign number must be 1-12, got {value}")
    wanted = value.strip().lower()
    for index, (key, name, _, _) in enumerate(_SIGNS):
        if wanted in (key.lower(), name.lower()):
            return index
    raise ValueError(f"unknown sign/rashi: {value!r}")
