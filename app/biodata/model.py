"""The fields a marriage biodata carries, and what this server is willing to keep.

FOUR SECTIONS, because that is what the sheet families actually exchange looks like: who the person
is, what they studied and do, who their family is, and how to reach them. Every field is free text
supplied by the person - the engine fills only the kundli block (app/biodata/core.py) and only from a
birth date, optionally a time and place.

NOTHING HERE IS STORED. A biodata is the one document on this site made entirely of personal details
about a named living person, usually assembled by a parent, and it is made to be handed to
strangers. So the server treats every field as something to render and drop: the fields arrive on a
POST, become a PDF or a .docx in memory, and go out in the response. There is no biodata table, no
cache keyed by name, and the photo is never written to disk at all (see `app/biodata/sheet.py`).

The one exception is the opt-in QR, which needs the birth details to survive - and it stores them as
a signed token the person can see and switch off, not as a row.
"""
from __future__ import annotations

import datetime as dt
import re

# A field is (key, kind), where kind decides only how it is laid out and validated.
#   "text"  one line
#   "long"  a few lines, kept as lines
#   "date"  a date, printed in the reader's own format
TEXT_LIMIT = 120
LONG_LIMIT = 400
MAX_LINES = 6

SECTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "personal": (("full_name", "text"), ("date_of_birth", "date"), ("birth_time", "text"),
                 ("birth_place", "text"), ("height", "text"), ("complexion", "text"),
                 ("blood_group", "text"), ("marital_status", "text"), ("diet", "text"),
                 ("languages", "text")),
    "work": (("qualification", "text"), ("college", "text"), ("occupation", "text"),
             ("employer", "text"), ("work_place", "text"), ("income", "text")),
    # DEVAK AND GOTRA ARE NOT HERE. They are free text like everything else in this file, but they
    # print in the kundli block beside gan and nadi, which is where a family reading a Marathi
    # biodata looks for them - and listing them in both places put them on the sheet twice.
    "family": (("father_name", "text"), ("father_occupation", "text"), ("mother_name", "text"),
               ("mother_occupation", "text"), ("siblings", "long"), ("native_place", "text")),
    "contact": (("contact_name", "text"), ("contact_relation", "text"), ("phone", "text"),
                ("email", "text"), ("address", "long")),
}

SECTION_TITLES = {
    "personal": {"en": "Personal details", "hi": "व्यक्तिगत जानकारी", "mr": "वैयक्तिक माहिती"},
    "work": {"en": "Education and work", "hi": "शिक्षा और व्यवसाय", "mr": "शिक्षण आणि व्यवसाय"},
    "family": {"en": "Family details", "hi": "पारिवारिक जानकारी", "mr": "कौटुंबिक माहिती"},
    "contact": {"en": "Contact", "hi": "संपर्क", "mr": "संपर्क"},
    "kundli": {"en": "Horoscope details", "hi": "कुंडली विवरण", "mr": "कुंडली तपशील"},
}

FIELD_LABELS = {
    "full_name": {"en": "Name", "hi": "नाम", "mr": "नाव"},
    "date_of_birth": {"en": "Date of birth", "hi": "जन्म तिथि", "mr": "जन्मतारीख"},
    "birth_time": {"en": "Time of birth", "hi": "जन्म समय", "mr": "जन्मवेळ"},
    "birth_place": {"en": "Place of birth", "hi": "जन्म स्थान", "mr": "जन्मस्थळ"},
    "height": {"en": "Height", "hi": "ऊँचाई", "mr": "उंची"},
    "complexion": {"en": "Complexion", "hi": "रंग", "mr": "वर्ण"},
    "blood_group": {"en": "Blood group", "hi": "रक्त समूह", "mr": "रक्तगट"},
    "marital_status": {"en": "Marital status", "hi": "वैवाहिक स्थिति", "mr": "वैवाहिक स्थिती"},
    "diet": {"en": "Diet", "hi": "आहार", "mr": "आहार"},
    "languages": {"en": "Languages", "hi": "भाषाएँ", "mr": "भाषा"},
    "qualification": {"en": "Qualification", "hi": "शिक्षा", "mr": "शिक्षण"},
    "college": {"en": "College", "hi": "महाविद्यालय", "mr": "महाविद्यालय"},
    "occupation": {"en": "Occupation", "hi": "व्यवसाय", "mr": "व्यवसाय"},
    "employer": {"en": "Organisation", "hi": "संस्था", "mr": "संस्था"},
    "work_place": {"en": "Place of work", "hi": "कार्यस्थल", "mr": "कार्यस्थळ"},
    "income": {"en": "Annual income", "hi": "वार्षिक आय", "mr": "वार्षिक उत्पन्न"},
    "father_name": {"en": "Father's name", "hi": "पिता का नाम", "mr": "वडिलांचे नाव"},
    "father_occupation": {"en": "Father's occupation", "hi": "पिता का व्यवसाय",
                          "mr": "वडिलांचा व्यवसाय"},
    "mother_name": {"en": "Mother's name", "hi": "माता का नाम", "mr": "आईचे नाव"},
    "mother_occupation": {"en": "Mother's occupation", "hi": "माता का व्यवसाय",
                          "mr": "आईचा व्यवसाय"},
    "siblings": {"en": "Brothers and sisters", "hi": "भाई-बहन", "mr": "भाऊ-बहीण"},
    "devak": {"en": "Devak", "hi": "देवक", "mr": "देवक"},
    "gotra": {"en": "Gotra", "hi": "गोत्र", "mr": "गोत्र"},
    "native_place": {"en": "Native place", "hi": "मूल स्थान", "mr": "मूळ गाव"},
    "contact_name": {"en": "Contact person", "hi": "संपर्क व्यक्ति", "mr": "संपर्क व्यक्ती"},
    "contact_relation": {"en": "Relation", "hi": "संबंध", "mr": "नाते"},
    "phone": {"en": "Phone", "hi": "फ़ोन", "mr": "दूरध्वनी"},
    "email": {"en": "Email", "hi": "ईमेल", "mr": "ईमेल"},
    "address": {"en": "Address", "hi": "पता", "mr": "पत्ता"},
}

# Collected from the form and printed in the kundli block rather than in a section of their own.
LINEAGE = (("devak", "text"), ("gotra", "text"))

ALL_FIELDS = tuple(key for fields in SECTIONS.values() for key, _ in fields) + tuple(
    key for key, _ in LINEAGE)
KINDS = {key: kind for fields in SECTIONS.values() for key, kind in fields}
KINDS.update(dict(LINEAGE))

# Control characters, and the two directional marks that let text render in an order it is not
# stored in. A biodata is pasted together from WhatsApp messages, so this arrives in practice.
_STRIP = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‎‏‪-‮]")


def clean(value: str, *, kind: str = "text") -> str:
    """One field, trimmed to what the sheet can lay out. Never raises: a biodata is typed by hand."""
    text = _STRIP.sub("", str(value or ""))
    if kind == "long":
        lines = [" ".join(line.split()) for line in text.splitlines()]
        return "\n".join([line for line in lines if line][:MAX_LINES])[:LONG_LIMIT]
    return " ".join(text.split())[:TEXT_LIMIT]


def parse_date(value: str) -> dt.date | None:
    """A date typed by a person. ISO first, then the two orders Indian forms use.

    DAY FIRST WHERE IT IS AMBIGUOUS. 04/03/1991 is the fourth of March to everyone filling in this
    form, and reading it as April would put the wrong rashi on the sheet - which is the same mistake
    the numerology form made with a native date input and had to be rebuilt to avoid.
    """
    text = " ".join(str(value or "").split())
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def parse_time(value: str) -> dt.time | None:
    text = " ".join(str(value or "").upper().split())
    if not text:
        return None
    for pattern in ("%H:%M", "%I:%M %p", "%I:%M%p", "%H.%M", "%I %p"):
        try:
            return dt.datetime.strptime(text, pattern).time()
        except ValueError:
            continue
    return None


def fields_from(raw: dict) -> dict[str, str]:
    """Every known field, cleaned; unknown keys dropped. Missing fields are simply absent."""
    out = {}
    for key in ALL_FIELDS:
        value = clean(raw.get(key, ""), kind=KINDS[key])
        if value:
            out[key] = value
    return out


def filled_sections(fields: dict, *, language: str) -> list[dict]:
    """The sections that have something in them, laid out for a template. Empty ones do not print:
    a biodata with an empty "Education and work" heading looks like a form somebody abandoned."""
    out = []
    for section, declared in SECTIONS.items():
        rows = [{"label": FIELD_LABELS[key][language], "value": fields[key], "kind": kind,
                 "lines": fields[key].splitlines() if kind == "long" else None}
                for key, kind in declared if fields.get(key)]
        if rows:
            out.append({"key": section, "title": SECTION_TITLES[section][language], "rows": rows})
    return out
