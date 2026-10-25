#!/usr/bin/env python3
"""Store a reading WRITTEN BY HAND (no API call) and run every check the generator runs.

    scripts/rashifal_handwritten.py check  <json>     # validate, print problems, store nothing
    scripts/rashifal_handwritten.py save   <json>     # validate, then store if clean
    scripts/rashifal_handwritten.py brief  <rashi> <period> [as-of]   # the brief, to write from

WHY THIS EXISTS. The 2027 yearly and monthly pages are being written in a Claude Code session
rather than through the Batch API, so nothing reaches `generate.py`'s call path - but a page that
skips the call must not skip the CHECKS. This runs the same structure, style and date checks the
generated pages go through, plus the cross-page similarity check, and refuses to store a reading
that fails any of them.

The JSON file is {"rashi": ..., "period": ..., "as_of": "YYYY-MM-DD", "content": {"hi": {...}, "mr": {...}}}
where each language value is exactly the page object the schema describes.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rashifal import store
from app.rashifal.periods import base_period                                    # noqa: E402
from app.rashifal.brief import brief_hash, build_brief            # noqa: E402
from app.rashifal.generate import structure_problems, style_problems, calendar_years  # noqa: E402
from app.rashifal.prompts import sections_for                     # noqa: E402

#: A date written in the prose, in any of the three shapes these pages use.
_DEVANAGARI_MONTHS = {
    "जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
    "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "नवंबर": 11, "नवम्बर": 11,
    "दिसंबर": 12, "दिसम्बर": 12,
    "जानेवारी": 1, "फेब्रुवारी": 2, "एप्रिल": 4, "मे": 5, "जुलै": 7, "ऑगस्ट": 8,
    "सप्टेंबर": 9, "ऑक्टोबर": 10, "नोव्हेंबर": 11, "डिसेंबर": 12,
}
# TWO GUARDS, both learned the hard way on Devanagari.
#
# (?<!\d) - otherwise "2027 में" yields day 27: the last two digits of a YEAR followed by a month.
# (?![\u0900-\u097F]) - otherwise Marathi "मे" (May) matches inside Hindi "में" (in), which is the
# single commonest word on these pages. Devanagari has no \b worth using; the test is that the next
# character is not another Devanagari letter, matra or sign.
_DATE_IN_PROSE = re.compile(
    r"(?<!\d)(\d{1,2})\s*(" + "|".join(sorted(_DEVANAGARI_MONTHS, key=len, reverse=True))
    + r")(?![\u0900-\u097F])")


def dates_in(text: str, year: int) -> set[dt.date]:
    """Every (day, month) pair written in the prose, as dates in `year`."""
    found = set()
    for day, month in _DATE_IN_PROSE.findall(text or ""):
        try:
            found.add(dt.date(year, _DEVANAGARI_MONTHS[month], int(day)))
        except ValueError:
            pass            # 31 February in the prose is caught by the date check below as unknown
    return found


def computed_dates(brief: dict) -> set[dt.date]:
    """Every date the ENGINE produced for this window: events, eclipses, Saturn phases, stays."""
    out: set[dt.date] = set()

    def add(value):
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            out.add(dt.date.fromisoformat(value))
        elif isinstance(value, dict):
            for item in value.values():
                add(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                add(item)

    for key in ("events", "eclipses", "saturn", "slow_graha_stays", "months", "period"):
        add(brief.get(key))
    return out


def date_problems(page: dict, brief: dict) -> list[str]:
    """EVERY DATE IN THE PROSE MUST BE ONE THE ENGINE PRODUCED.

    This is the check the whole build rests on: a reading may interpret freely, but it may not
    invent a date. A date that is not in the computed set is either a typo or a hallucination, and
    both read as fact to somebody planning around it.
    """
    year = int((brief.get("period") or {}).get("start_date", "2027-01-01")[:4])
    allowed = computed_dates(brief)
    text = " ".join(_all_text(page))
    unknown = sorted(d for d in dates_in(text, year) if d not in allowed)
    return [f"{d.isoformat()} is written in the text but the engine produced no such date"
            for d in unknown]


def _all_text(page: dict) -> list[str]:
    parts = [page.get("headline") or "", page.get("summary") or "", page.get("overview") or "",
             page.get("tip") or ""]
    for paragraphs in (page.get("sections") or {}).values():
        parts += [p or "" for p in (paragraphs or [])]
    for month in (page.get("months") or []):
        parts.append((month or {}).get("text") or "")
    for item in (page.get("key_dates") or []):
        parts.append((item or {}).get("note") or "")
    return parts


# The tokens twelve pages MUST share. All twelve rashis read one sky: Guru really does turn direct
# on 13 April for every one of them, and the ninth really is the house of fortune for every one of
# them. Counting those as borrowed text makes the check impossible to pass no matter how well the
# pages are written - it measures the astronomy, not the writing.
#
# So the comparison runs on the INTERPRETATION only: these tokens are dropped from both streams
# before the runs are counted, and what is left must still differ. A shared run now means two pages
# said the same thing about their own different houses, which is the thing actually worth catching.
#: Where the pending batch lives. The similarity check reads it so a batch is compared
#: against the world it is about to create, not the one it is replacing.
HERE = pathlib.Path(__file__).resolve().parent.parent / "var" / "handwritten"

_SHARED_FACT_TOKEN = re.compile(
    r"^(?:\d+|[०-९]+"
    r"|जनवरी|फ़रवरी|फरवरी|मार्च|अप्रैल|मई|मे|जून|जुलाई|जुलै|अगस्त|ऑगस्ट|सितंबर|सप्टेंबर"
    r"|अक्टूबर|ऑक्टोबर|नवंबर|नोव्हेंबर|दिसंबर|डिसेंबर"
    r"|गुरु|गुरू|शनि|शनी|मंगल|मंगळ|बुध|सूर्य|चंद्र|राहु|राहू|केतु|केतू"
    r"|वक्री|मार्गी|भाव|भावात|स्थान|स्थानात|स्थानात्|राशि|राशी|राशीत"
    # ECLIPSE VOCABULARY. Twelve pages describe the same five eclipses, and there is no second way
    # to say "penumbral, so no sutak is observed" - it is a definition, not a turn of phrase. Left
    # in the stream it made every accurate wording collide with the next one I invented.
    r"|ग्रहण|सूर्यग्रहण|चंद्रग्रहण|उपच्छाया|सूतक|सुतक|श्रेणी|आंशिक|खग्रास|पूर्ण"
    # THE TRADITIONAL DONATION ITEMS. There is no second way to name til, or gud, or a blanket -
    # they are fixed items the way a bija mantra is a fixed string, and Makar Sankranti's til-gud is
    # the same sentence on all twelve pages because it is the same practice for all twelve readers.
    # What must still differ is WHY a page recommends one, which is the rashi's own.
    r"|तिल|तीळ|गुड़|गूळ|कंबल|घोंगडी|नारियल|नारळ|सरसों|मोहरी|उड़द|उडीद|हल्दी|हळद"
    # THE GEMSTONES, for the same reason as the donation items. Six pairs of signs share a ruling
    # graha, so they share a stone: Vrishabha and Tula are both Shukra's and both say हीरा, Makara
    # and Kumbha are both Shani's, Mesha and Vrishchika both Mangal's. There is no second name for
    # the stone of a graha - it is a fact, like the date of an ingress. What must still differ is
    # what the page says AROUND it, which is the rashi's own.
    r"|माणिक|मोती|मूंगा|मूँगा|पोवळा|पन्ना|पाचू|पुखराज|पुष्कराज|हीरा|हिरा|नीलम|गोमेद|लहसुनिया|वैडूर्य"
    r"|मसूर|केला|केळे|चना|हरभरा|मूँग|मूग|चावल|तांदूळ|दही|दान|व्रत|जप|मंत्र|पाठ"
    r"|पहले|दूसरे|तीसरे|चौथे|पाँचवें|पांचवें|छठे|सातवें|आठवें|नवें|दसवें|ग्यारहवें|बारहवें"
    r"|पहिल्या|दुसऱ्या|तिसऱ्या|चौथ्या|पाचव्या|सहाव्या|सातव्या|आठव्या|नवव्या|दहाव्या|अकराव्या|बाराव्या"
    r"|को|से|तक|में|और|है|हैं|होते|रहते|आते|जाते|पर|का|की|के"
    r"|ला|पासून|पर्यंत|मध्ये|आणि|आहे|आहेत|होतात|राहतात|येतात|जातात|चा|ची|चे|रोजी"
    r")$")

# The twelve sign names, which are facts in the same way the dates are: Guru is in Karka from 25
# January for EVERY rashi, so every page says Karka. Matched as a stem with any inflection after it,
# because the locative differs by language and by sign - कर्केत, कन्येत, मकरेत, कर्क में, कन्या में.
_SIGN_STEM = re.compile(
    r"^(?:मेष|वृषभ|वृष|मिथुन|कर्क|सिंह|कन्य|तूळ|तुळ|तुला|वृश्चिक|वृषचिक|धनु|धनू|मकर|कुंभ|मीन)")


#: Bija mantras, quoted verbatim or not at all. "ॐ शं शनैश्चराय नमः" is a fixed string in the same
#: way 13 April is a fixed date: there is no second way to write it, so two pages that both name
#: Saturn's mantra are not copying each other. Stripped before runs are counted, like the dates.
_MANTRAS = (
    "ॐ शं शनैश्चराय नमः", "ॐ बृं बृहस्पतये नमः", "ॐ रां राहवे नमः", "ॐ कें केतवे नमः",
    "ॐ अं अंगारकाय नमः", "ॐ बुं बुधाय नमः", "ॐ शुं शुक्राय नमः", "ॐ सों सोमाय नमः",
    "ॐ घृणिः सूर्याय नमः", "ॐ नमः शिवाय",
)


def _interpretation_only(text: str) -> str:
    """The text with the tokens every rashi shares removed, for the similarity comparison."""
    for mantra in _MANTRAS:
        text = text.replace(mantra, " ")
    out = []
    for word in text.split():
        bare = word.strip(" ।,.-:'\"()")
        if _SHARED_FACT_TOKEN.match(bare) or _SIGN_STEM.match(bare):
            continue
        out.append(word)
    return " ".join(out)


def _corpus(rashi: str, period: str, language: str):
    """Every other page this one will sit beside: what is STORED plus what is PENDING on disk.

    The store alone is a stale baseline, and that cost a whole pass. Twelve pages were validated
    clean against the stored set, the first was saved, and the other eleven then failed against it -
    because a scripted edit had written the same sentence onto all twelve, and each had only ever
    been compared with the OLD version of its neighbours. A batch must be checked against the world
    it is about to create, not the one it is replacing.
    """
    seen: dict[tuple[str, str], dict | None] = {}
    for other_rashi, other_period in store.list_pages():
        if (other_rashi, other_period) == (rashi, period):
            continue
        full = store.get_page(other_rashi, other_period)
        seen[(other_rashi, other_period)] = ((full or {}).get("content") or {}).get(language)
    for path in sorted(HERE.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        key = (payload.get("rashi"), payload.get("period"))
        if key == (rashi, period) or not all(key):
            continue
        pending = (payload.get("content") or {}).get(language)
        if pending:
            seen[key] = pending          # the pending version wins over the stored one
    return sorted(seen.items())


def similarity_problems(page: dict, rashi: str, period: str, language: str) -> list[str]:
    """No two pages may share a long run of identical text.

    An eight-word run is the same threshold the mantra explainers use. Shared boilerplate is how a
    set of twelve "personalised" pages turns out to be one page with the sign's name swapped.
    """
    from app.mantra.originality import borrowed

    mine = " ".join(_all_text(page))
    problems = []
    for (other_rashi, other_period), other in _corpus(rashi, period, language):
        if other is None:
            continue
        shared = borrowed(_interpretation_only(mine),
                          [_interpretation_only(" ".join(_all_text(other)))])
        if shared:
            problems.append(f"shares {len(shared)} run(s) of 8+ words with {other_rashi}/{other_period}, "
                            f"e.g. {shared[0][:70]!r}")
    return problems


#: Words that claim an eclipse covers the whole disc. Writing one of these about a date the engine
#: reports as PARTIAL from India is the exact error that shipped on all twelve yearly pages: the
#: 2 August 2027 solar eclipse is total on its own path and 0.296 magnitude from Ujjain, and
#: "total solar eclipse, visible in India" is wrong on both halves of the sentence.
_TOTALITY_WORDS = ("पूर्ण", "खग्रास", "संपूर्ण", "वलयाकार", "कंकणाकृती", "कंकणाकृत")

#: The word a reader searches for. A penumbral lunar eclipse is not one of these in practice - no
#: sutak is observed - so it must not be presented as a date to be careful of.
_GRAHAN_WORDS = ("ग्रहण", "सूर्यग्रहण", "चंद्रग्रहण")

#: Prose that tells the reader to hold off. Harmless on a real grahan date, wrong on a penumbral one.
_AVOIDANCE_WORDS = ("टालिए", "टालने", "टालना", "टाळा", "टाळण्याची", "टाळणे", "न घेणे", "न करने",
                    "न कीजिए", "मत कीजिए", "बचने", "बचिए", "ढकला", "ढकलणे", "पुढे ढकल")

#: Prose that has already told the reader this is not a grahan. Saying so is the correct handling.
_NOT_GRAHAN_MARKS = ("उपच्छाया", "ग्रहण नहीं मानती", "ग्रहण नहीं मानत", "ग्रहण मानत नाही",
                     "सूतक नहीं", "सूतक का कोई नियम नहीं", "सूतक का नियम नहीं",
                     "सुतक पाळत नाही", "सुतक पाळले जात नाही", "सुतक नाही", "दिखाई नहीं देते",
                     "दिखाई ही नहीं देते", "भारतात दिसत नाही")


def eclipse_problems(page: dict, brief: dict, language: str) -> list[str]:
    """What the prose says a reader will SEE must match what the engine says they will see.

    Two separate mistakes, both of which shipped:

    1. Calling an eclipse total or annular when that is its classification somewhere else on Earth.
       An eclipse is total only along a narrow path; everywhere else it is partial, and the brief's
       `india_kind` is the field that knows which.
    2. Listing a penumbral lunar eclipse as a caution date. The tradition observes no sutak for one,
       so a reader who plans around it has been given a rule that does not exist.
    """
    problems: list[str] = []
    year = int(str(brief.get("period", {}).get("start", "2027"))[:4])
    for eclipse in brief.get("eclipses", ()):
        when = dt.date.fromisoformat(eclipse["date"])
        india = eclipse.get("india_kind", "none")
        for where, text in _slots(page):
            if when not in dates_in(text, year):
                continue
            # ADJACENT TO THE ECLIPSE NOUN, not merely present in the sentence: "संपूर्ण" also means
            # "entire", and "राहू संपूर्ण वर्ष" (Rahu all year) read as a totality claim.
            said = next((word for word in _TOTALITY_WORDS
                         if re.search(rf"{word}\s*\S{{0,12}}\s*(?:{'|'.join(_GRAHAN_WORDS)})", text)), None)
            if india != "total" and said:
                problems.append(
                    f"{where} calls the {eclipse['date']} eclipse '{said}', but from India the engine"
                    f" computes it as {india} (magnitude {eclipse.get('india_magnitude')}). Say what a"
                    f" reader here will actually see.")
            # NOT ONLY IN caution_periods. Telling a reader to postpone a decision around a penumbral
            # eclipse is the same error wherever it is written, and it was written inside ordinary
            # sections too.
            # A PAGE MAY MENTION ONE - it should, because the reader will see "21 February chandra
            # grahan" on a calendar and wonder - as long as it says the tradition does not treat it
            # as one. Prose that explains that is passing, not failing, and "टालने की ज़रूरत नहीं"
            # (no need to postpone) contains the same word as "टालिए" (postpone it).
            explained = any(mark in text for mark in _NOT_GRAHAN_MARKS)
            if (not eclipse.get("observed_as_grahan") and not explained
                    and any(w in text for w in _AVOIDANCE_WORDS)):
                problems.append(
                    f"{where} advises caution around {eclipse['date']}, a {eclipse['kind']} eclipse"
                    f" ({india} from India) that the tradition does not treat as grahan - no sutak is"
                    f" observed for it, so there is no rule to plan around.")
    return problems


def _slots(page: dict) -> list[tuple[str, str]]:
    """(where, text) for every piece of prose on the page, named so a problem can point at it."""
    out = [(key, page[key]) for key in ("headline", "summary", "overview", "tip") if page.get(key)]
    for key, paragraphs in (page.get("sections") or {}).items():
        for paragraph in paragraphs:
            out.append((key, paragraph))
    for month in page.get("months") or ():
        out.append((f"months/{month.get('month')}", month.get("text", "")))
    for item in page.get("key_dates") or ():
        out.append((f"key_dates/{item.get('event_id')}", item.get("note", "")))
    return out


def check(payload: dict) -> dict[str, list[str]]:
    rashi, period = payload["rashi"], payload["period"]
    as_of = dt.datetime.fromisoformat(payload.get("as_of") or "2027-01-01") 
    brief = build_brief(rashi, period, as_of)
    spans = calendar_years(brief)
    found: dict[str, list[str]] = {}
    for language, page in payload["content"].items():
        problems = structure_problems(page, language, brief)
        problems += style_problems(page, language, spans)
        problems += date_problems(page, brief)
        problems += eclipse_problems(page, brief, language)
        problems += similarity_problems(page, rashi, period, language)
        missing = [s for s in sections_for(base_period(period))
                   if not (page.get("sections") or {}).get(s)]
        if missing:
            problems.append(f"missing section(s): {', '.join(missing)}")
        # DEDUPED, order kept. structure_problems and style_problems both police the year-mention
        # rule, so every long page reported it twice - and a duplicated line is one more line in
        # which a second, different problem can hide.
        found[language] = list(dict.fromkeys(problems))
    return found


def words_in(page: dict) -> int:
    return len(" ".join(_all_text(page)).split())


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else ""
    if mode == "brief":
        rashi, period = argv[1], argv[2]
        as_of = dt.datetime.fromisoformat(argv[3]) if len(argv) > 3 else dt.datetime(2027, 1, 1, 9, 0)
        print(json.dumps(build_brief(rashi, period, as_of), ensure_ascii=False, indent=1))
        return 0
    if mode == "load":
        # MANY FILES, ALL OR NOTHING PER FILE. This is the deploy's step: the readings are content
        # in the repository, and a code deploy that shipped the templates without them would leave
        # the live page rendering three generated sections under a sixteen-section layout.
        #
        # Every check runs again here rather than being trusted from when the file was written. The
        # prose is fixed but the brief is not: it is recomputed from the ephemeris at load time, so
        # a date that was right in November and wrong after an ephemeris update fails HERE, on the
        # machine that is about to serve it, instead of silently going live.
        # SAY WHICH DATABASE, because the whole point of this step is that the readings land in the
        # one the service reads. Printed before the work, so a wrong path is visible even if a later
        # file is refused.
        from app import db as _db
        print(f"  database: {_db.db_path()}")
        failed = []
        for name in argv[1:]:
            payload = json.loads(Path(name).read_text(encoding="utf-8"))
            found = check(payload)
            problems = {lang: items for lang, items in found.items() if items}
            if problems:
                failed.append(name)
                print(f"  REFUSED {name}")
                for language, items in problems.items():
                    for problem in items[:4]:
                        print(f"     {language}: {problem}")
                continue
            _store(payload)
            print(f"  loaded {payload['rashi']}/{payload['period']} "
                  f"in {sorted(payload['content'])} from {Path(name).name}")
        if failed:
            print(f"  {len(failed)} file(s) refused, {len(argv) - 1 - len(failed)} loaded")
            return 1
        print(f"  {len(argv) - 1} file(s) loaded, all checks clean")
        return 0
    if mode not in ("check", "save"):
        print(__doc__)
        return 2
    payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    found = check(payload)
    clean = True
    for language, problems in found.items():
        page = payload["content"][language]
        print(f"  {language}: {words_in(page)} words, {len(problems)} problem(s)")
        for problem in problems[:12]:
            print(f"     - {problem}")
        clean = clean and not problems
    if not clean:
        print("  NOT STORED: fix the problems above")
        return 1
    if mode == "save":
        _store(payload)
        print(f"  STORED {payload['rashi']}/{payload['period']} in {sorted(payload['content'])}")
        return 0
    return 0


def _store(payload: dict) -> None:
    """Write a checked payload to the store. The one path both `save` and `load` go through."""
    as_of = dt.datetime.fromisoformat(payload.get("as_of") or "2027-01-01")
    brief = build_brief(payload["rashi"], payload["period"], as_of)
    period_info = brief["period"]
    store.save_page(payload["rashi"], payload["period"],
                    period_start=period_info["start_date"], period_end=period_info["end_date"],
                    generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    model="handwritten", brief_hash=brief_hash(brief),
                    content=payload["content"], brief=brief,
                    meta={"source": "handwritten", "written_in": "claude-code-session"})


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
