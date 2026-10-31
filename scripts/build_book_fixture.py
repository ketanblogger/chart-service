"""Build the long BOOK fixtures the PDF tests and the visual checks run on.

    .venv/bin/python scripts/build_book_fixture.py            # -> tests/fixtures/kundali_book_{en,mr}.json

Why a synthetic fixture: the flagship Kundali book is 30-60 pages of AI text,
and app/pdf must be built and checked against that length **without making a single billed AI call**.
So: real engine data (the reference Miraj chart, the real Vimshottari dates, the real timeline windows
from app/ai/engine_facts.py), the real part/chapter plan from app/ai/book.py, and placeholder prose of
the length each chapter's brief asks for. `meta.model == "fixture"` and every paragraph is marked, so
nobody can mistake this for a real reading.

Everything factual here - the navamsa, the yogas, the gemstone table, every window and every date - is
real engine output via `app.ai.book_report.build_book_data`, and the windows are resolved exactly the way
`book_report` resolves them after a real call. Only the prose is placeholder, so the fixture cannot drift
from the contract: if `ai-layer` changes the book's parts or `calc-engine` changes a fact, re-running this
script produces the new shape and tests/test_pdf.py renders it.
"""

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import book as ai_book  # noqa: E402
from app.ai import book_report, engine_facts  # noqa: E402
from app.ai.products import PRODUCTS  # noqa: E402
from app.ai.prompts import DISCLAIMERS  # noqa: E402
from app.ai.report import Birth, report_id  # noqa: E402
from tests.reference_charts import AS_OF as REFERENCE_AS_OF  # noqa: E402
from tests.reference_charts import PRIMARY  # noqa: E402

OUT = ROOT / "tests/fixtures"
# The published chart the whole suite is anchored on (tests/reference_charts.py). PRIMARY is the feature-rich
# one - nine yogas, two exaltations, two combust grahas, a debilitated Moon - so the book fixture exercises
# more of the renderer than a quieter chart would. `AS_OF` is pinned there so the fixture does not change
# meaning as real time passes.
BIRTH = Birth(dt.date.fromisoformat(PRIMARY.request()["date"]), dt.time.fromisoformat(PRIMARY.request()["time"]),
              PRIMARY.lat, PRIMARY.lon, PRIMARY.tz, PRIMARY.place)
AS_OF = REFERENCE_AS_OF.date()
GRAHA_ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


# ---- placeholder prose --------------------------------------------------------------------------------

MARK = {"en": "[FIXTURE TEXT]", "mr": "[फिक्स्चर मजकूर]"}
# Placeholder prose. It says nothing about any particular chart on purpose: the reference chart is being
# replaced, and text that named houses and placements would quietly become astrologically false for the next
# one. What it must do is exercise the typography - Devanagari shaping, sentence length, a full page of it.
SENTENCES = {
    "en": [
        "The lagna lord's placement gives this chart a steady, negotiating temper rather than a combative one.",
        "Guru's aspect keeps work honest and slow-burning; recognition tends to arrive after the work is done "
        "rather than before it.",
        "The Moon wants meaning in what it does, so routine work without a purpose behind it drains this person "
        "faster than long hours do.",
        "Shani asks for patience with partners of every kind - in business as much as at home - and rewards the "
        "ones who stay.",
        "Budha and Shukra together give a practical, service-minded turn of mind and a real talent for sorting "
        "out other people's tangles.",
        "Gains arrive through groups, old colleagues and older mentors rather than through cold approaches.",
        "Energy is best spent early in the day here; late-night pushing costs more than it returns.",
        "Nothing in this chart asks for a dramatic change of direction - it asks for the same direction, held "
        "for longer than feels comfortable.",
    ],
    "mr": [
        "लग्नेशाच्या स्थितीमुळे या कुंडलीचा स्वभाव भांडखोर नसून समजुतीने मार्ग काढणारा आहे.",
        "गुरूच्या दृष्टीमुळे काम प्रामाणिक आणि संथ गतीने पुढे जाते; ओळख कामानंतर मिळते, आधी नाही.",
        "चंद्र कामात अर्थ शोधतो, त्यामुळे निव्वळ यांत्रिक कामाने थकवा लवकर येतो.",
        "शनी प्रत्येक भागीदारीत संयम मागतो - व्यवसायात आणि घरातही - आणि टिकणाऱ्यांना फळ देतो.",
        "बुध आणि शुक्र एकत्र असल्याने व्यवहारी, सेवाभावी वृत्ती आणि दुसऱ्यांचे गुंते सोडवण्याची खरी हातोटी मिळते.",
        "लाभ हे गट, जुने सहकारी आणि ज्येष्ठ मंडळींच्या माध्यमातून येतात असे दिसते.",
        "ऊर्जा दिवसाच्या सुरुवातीला वापरणे येथे हिताचे; रात्री उशिरापर्यंतचा ताण महागात पडतो.",
        "ही कुंडली दिशा बदलायला सांगत नाही - तीच दिशा अपेक्षेपेक्षा जास्त काळ टिकवायला सांगते.",
        "जन्मनक्षत्राचा प्रभाव ज्येष्ठांच्या सल्ल्याला महत्त्व देतो आणि निर्णयात घाई टाळायला शिकवतो.",
        # deliberate shaping torture for the Devanagari face: ष्ट्र, त्त्व, ऱ्हास, क्ष, त्र, ज्ञ, श्री
        "श्री महाराष्ट्रातील ज्येष्ठ ज्योतिषांच्या मते व्यक्तिमत्त्वाचा ऱ्हास टाळण्यासाठी क्षमता, त्रास आणि ज्ञान "
        "यांचा तिसऱ्या स्थानातून समतोल राखणे आवश्यक आहे.",
    ],
}
HEADLINES = {
    "en": ["Steady build", "A door opens", "Consolidate", "Slow, then sudden", "Money finds a shape",
           "Family first", "Learn something hard", "Rest and rebuild"],
    "mr": ["संथ उभारणी", "एक दार उघडते", "बांधणी पक्की करा", "आधी संथ, मग वेगवान", "पैशाला आकार",
           "कुटुंब प्रथम", "कठीण काही शिका", "विश्रांती आणि पुनर्बांधणी"],
}
AREAS = ("career", "money", "marriage", "health", "education", "family", "property")
# A chapter that covers a span is headed by the engine's range label plus the model's THEME (up to 64
# characters). The fixture uses themes of that length, so the contents page is laid out against the
# longest heading it can really be given, not against a short placeholder.
THEMES = {
    "en": ["Steady building, and the patience it asks for", "Work turns outward and money follows slowly",
           "A settled stretch for family, home and study", "Responsibility arrives before the recognition does"],
    "mr": ["संथ उभारणी आणि त्यासाठी लागणारा संयम", "काम बाहेर वळते आणि पैसा हळूहळू मागे येतो",
           "कुटुंब, घर आणि शिक्षणासाठी स्थिर काळ", "ओळखीच्या आधी जबाबदारी येऊन उभी राहते"],
}


class Prose:
    """Deterministic placeholder text: the same fixture is produced on every run."""

    def __init__(self, language: str) -> None:
        self.language = language
        self.at = 0

    def sentences(self, count: int) -> str:
        pool = SENTENCES[self.language]
        out = []
        for _ in range(count):
            out.append(pool[self.at % len(pool)])
            self.at += 1
        return " ".join(out)

    def paragraphs(self, count: int, per: int = 4) -> list:
        return [f"{MARK[self.language]} {self.sentences(per)}" for _ in range(count)]

    def headline(self) -> str:
        pool = HEADLINES[self.language]
        self.at += 1
        return pool[self.at % len(pool)]


def _heading(language: str, chapter_id: str) -> str:
    from app.pdf.labels import Labels

    return Labels(language).chapter(chapter_id)


def _chapter_body(prose: Prose, language: str, chapter, facts: dict, windows: dict) -> dict:
    """One chapter in the shape its brief asks for - and, for a timeline chapter, with its windows already
    resolved to the engine's dates, exactly as app/ai/book_report.py resolves them after a real call.

    The heading goes through `book_report.compose_heading` too: for a chapter that covers a span (a year,
    a five-year block) the printed heading is the ENGINE's label plus the model's theme, so the fixture
    exercises the long composed headings the contents page really has to fit."""
    theme = THEMES[language][prose.at % len(THEMES[language])] if getattr(chapter, "labels", None) \
        else _heading(language, chapter.id)
    heading = book_report.compose_heading(chapter, theme, language)
    body = {"id": chapter.id, "heading": heading, "paragraphs": [], "bullets": [],
            "highlights": [], "windows": [], "table": None}
    if chapter.shape == getattr(ai_book, "HIGHLIGHTS", "\0"):  # older shape: the items lived in the chapter
        for key in ai_book.highlight_keys(facts):
            body["highlights"].append({"key": key, "heading": _heading(language, key),
                                       "lines": [f"{MARK[language]} {prose.sentences(1)}" for _ in range(2)]})
    elif chapter.shape == ai_book.WINDOWS:
        short = chapter.id == "past"
        for window_id in chapter.window_ids:
            window = windows.get(window_id)
            if window is None:
                continue
            body["windows"].append({
                **engine_facts.window_public(window, language),
                "headline": prose.headline(),
                "paragraphs": prose.paragraphs(1, 2 if short else 5),
                "areas": [] if short else list(AREAS[prose.at % 3: prose.at % 3 + 3]),
            })
    elif chapter.shape == ai_book.TABLE:
        years = [year["year"] for year in facts["timeline"].get("year_table", [])]
        columns = {"en": ["Year", "Dasha", "Career", "Money", "Relationships"],
                   "mr": ["वर्ष", "दशा", "करिअर", "पैसा", "नाती"]}[language]
        body["table"] = {"columns": columns,
                         "rows": [[str(year), "Rahu - Guru" if language == "en" else "राहू - गुरू",
                                   prose.headline(), prose.headline(), prose.headline()] for year in years]}
    else:
        body["paragraphs"] = prose.paragraphs(3, 5)
        if chapter.id in ("closing", "work_money_health", "at_a_glance"):
            body["bullets"] = [f"{MARK[language]} {prose.sentences(1)}" for _ in range(3)]
    return body


def _highlights(prose: Prose, language: str, facts: dict) -> dict:
    """Part A items 2-7, the top-level `highlights` object of the report JSON (app/ai/schema.py)."""
    line = lambda: f"{MARK[language]} {prose.sentences(1)}"  # noqa: E731
    keys = ai_book.highlight_keys(facts)
    written = {"mangal": {"verdict": line(), "remedy": line()},
               "sade_sati": {"verdict": line(), "guidance": line()},
               "dasha": {"mood": line()},
               "strengths": [line() for _ in range(3)],
               "cautions": [line() for _ in range(3)],
               "yogas": [{"name": yoga["name"], "text": line()} for yoga in facts.get("yogas") or []]}
    return {key: value for key, value in written.items()
            if key in keys or key.replace("mangal", "mangal_dosha") in keys}


def _gemstone(prose: Prose, language: str, facts: dict) -> dict:
    """The writer's own gemstone card, in the report language (the engine table is in `data`)."""
    recommended = ((facts.get("gemstone") or {}).get("recommended") or [{}])[0]
    if not recommended:
        return {}
    return {"stone": recommended.get("stone", ""), "finger": recommended.get("finger", ""),
            "day": recommended.get("day", ""), "metal": recommended.get("metal", ""),
            "avoid": "", "note": f"{MARK[language]} {prose.sentences(2)}"}


REMEDIES = {
    "en": [("Gayatri mantra at sunrise", "mantra", "Surya is the lagna lord here, so a Surya-facing habit "
            "supports the whole chart.", "Face the sun, offer water, and say the Gayatri mantra eleven times.",
            "Every morning"),
           ("Feed someone on Saturdays", "charity", "Shani sits in the seventh; simple, regular giving is the "
            "traditional response.", "Give cooked food or grain to whoever needs it near you.", "Saturdays"),
           ("Hanuman Chalisa", "worship", "The classical support where Mangal is strong.",
            "Read it once, calmly, without hurrying the last verses.", "Tuesdays and Saturdays"),
           ("A fixed sleeping hour", "habit", "Chandra in the fifth does better on rhythm than on rest taken "
            "in lumps.", "Same hour every night for a month, then keep it.", "Daily"),
           ("Ten minutes of stillness", "meditation", "Rahu dasha rewards a settled mind more than a busy one.",
            "Sit, breathe, and let the day settle before you answer anything.", "Before the working day"),
           ("Service to elders", "service", "Guru's aspect here grows through what is given to teachers.",
            "Help one older person with something practical each week.", "Weekly")],
    "mr": [("सूर्योदयी गायत्री मंत्र", "mantra", "येथे सूर्य लग्नेश असल्याने सूर्याभिमुख सवय संपूर्ण कुंडलीला आधार देते.",
            "सूर्याकडे तोंड करून अर्घ्य द्या आणि गायत्री मंत्राचे अकरा वेळा पठण करा.", "दररोज सकाळी"),
           ("शनिवारी अन्नदान", "charity", "शनी सातव्या स्थानी आहे; नियमित, साधे दान हीच पारंपरिक प्रतिक्रिया आहे.",
            "जवळच्या गरजू व्यक्तीला शिजवलेले अन्न किंवा धान्य द्या.", "शनिवारी"),
           ("हनुमान चालीसा", "worship", "मंगळ बलवान असताना सांगितला जाणारा शास्त्रीय आधार.",
            "शांतपणे, शेवटच्या ओळी घाईत न म्हणता एकदा वाचा.", "मंगळवार आणि शनिवार"),
           ("झोपेची ठरलेली वेळ", "habit", "पंचमातील चंद्राला तुटक विश्रांतीपेक्षा नियमित लय अधिक मानवते.",
            "महिनाभर रोज एकाच वेळी झोपा, मग तीच वेळ टिकवा.", "दररोज"),
           ("दहा मिनिटे स्तब्धता", "meditation", "राहू महादशेत शांत मन व्यस्त मनापेक्षा अधिक फळ देते.",
            "बसा, श्वासावर लक्ष द्या आणि उत्तर देण्याआधी दिवस स्थिरावू द्या.", "कामाच्या आधी"),
           ("ज्येष्ठांची सेवा", "service", "येथे गुरूची दृष्टी दिलेल्या सेवेतून वाढते.",
            "दर आठवड्याला एका ज्येष्ठ व्यक्तीला काही प्रत्यक्ष मदत करा.", "दर आठवड्याला")],
}
TITLES = {"en": "Your Kundali Book", "mr": "तुमचे कुंडली पुस्तक"}


def build(language: str) -> dict:
    chart = PRIMARY.chart(REFERENCE_AS_OF, detail="full")
    data, _prompt, book = book_report.build_book_data(chart, language, AS_OF)
    windows = engine_facts.all_windows(data["timeline"])

    prose = Prose(language)
    parts = []
    for part in book:
        parts.append({"id": part.id, "heading": _part_heading(language, part.id),
                      "chapters": [_chapter_body(prose, language, chapter, data, windows)
                                   for chapter in part.chapters]})
    return {
        "id": report_id("kundali-report", language, [BIRTH], AS_OF),
        "product": "kundali-report", "product_name": PRODUCTS["kundali-report"].name, "language": language,
        "title": TITLES[language], "summary": f"{MARK[language]} {prose.sentences(4)}",
        "parts": parts,
        "highlights": _highlights(prose, language, data),
        "gemstone": _gemstone(prose, language, data),
        "remedies": [{"title": title, "type": kind, "description": description, "how_to": how, "frequency": when}
                     for title, kind, description, how, when in REMEDIES[language]],
        "disclaimer": DISCLAIMERS[language], "data": data,
        "meta": {"model": "fixture", "as_of": AS_OF.isoformat(),
                 "note": "FIXTURE - placeholder prose over real engine data; no AI call was made "
                         "(scripts/build_book_fixture.py)."},
    }


def _part_heading(language: str, part_id: str) -> str:
    from app.pdf.labels import Labels

    return Labels(language).part(0, part_id)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for language in ("en", "mr"):
        report = build(language)
        path = OUT / f"kundali_book_{language}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        chapters = sum(len(part["chapters"]) for part in report["parts"])
        windows = sum(len(chapter["windows"]) for part in report["parts"] for chapter in part["chapters"])
        print(f"{path}  {len(report['parts'])} parts, {chapters} chapters, {windows} windows, "
              f"{path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
