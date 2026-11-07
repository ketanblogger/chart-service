"""The flagship Kundali book: Parts A-H, their chapters, and how they are split into Sonnet calls.

The book's structure - Parts A to H - lives here as data rather than as prose. Two things are
chart-driven rather than fixed, which is the whole point - "jitni chart demand kare", the book runs as
long as the chart demands and no longer:

- Part D's chapters come from the engine's timeline windows, so a chart with more dasha changes
  gets a thicker timeline and a simpler one a leaner book. Nothing is padded to a page count.
- A chapter whose engine facts are absent is not written at all (no yogas -> no yoga highlight,
  no engine gemstone -> no gemstone chapter). "Kuch bhi chipkana nahi": nothing generic is pasted in
  to fill space.

`build_book(facts)` turns the engine facts into the concrete part/chapter list for one chart, and
`plan(book)` splits that into the calls report.py makes. See docs/API.md "Paid AI reports".
"""

from dataclasses import dataclass, field

from .engine_facts import (
    AREAS,
    current_year_windows,
    far_block_windows,
    near_year_windows,
    past_entries,
    supplied,
    windows_for_areas,
)

# What a chapter may return beyond paragraphs. The output schema always has every key; this says
# which ones the brief asks the writer to fill, and book_report.py rejects a chapter that fills others.
PLAIN, WINDOWS, TABLE = "plain", "windows", "table"

# Chapters exempt from the generic-filler check. Not a loophole - these are the chapters whose job is
# NOT to cite a placement, so requiring one produced pure false positives that cost three retries and
# still redacted good text on a live run:
#   closing       Part H is a short encouraging summary; "hold to the routine and the years will
#                 reward it" names no graha by design and is the right closing line.
#   gemstone      grounded in the engine's stone table (stone, finger, day, metal), not in a house.
#   other_doshas  its framing paragraphs are the engine's own safety wording about a dosha.
# Everything else in the book still has to earn its place: nothing generic, nothing to fill space.
FILLER_EXEMPT_CHAPTERS = frozenset({"closing", "gemstone", "other_doshas"})


@dataclass(frozen=True)
class Chapter:
    id: str
    brief: str
    shape: str = PLAIN
    windows: tuple = ()             # engine windows this chapter writes one entry each for
    reference_windows: tuple = ()   # windows the brief may draw on without writing an entry for them
    words: str = "250-400 words"
    # The engine's per-language label for the span this chapter covers, when it covers one. The
    # printed heading is composed from THIS plus the model's theme, so the model never writes the
    # span itself - see `_part_d` and book_report.compose_heading.
    labels: dict = field(default_factory=dict)

    @property
    def window_ids(self) -> tuple:
        return tuple(window["id"] for window in self.windows)


@dataclass(frozen=True)
class Part:
    id: str
    label: str  # A .. H
    brief: str  # what this part is, for the writer's heading
    chapters: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class Call:
    """One Sonnet call. Writes whole chapters; a failure is retried alone, never the whole book."""

    key: str
    parts: tuple  # (Part with only this call's chapters,)
    wants_front_matter: bool = False  # title + summary
    wants_remedies: bool = False
    wants_highlights: bool = False    # the top-level Part A summary object
    wants_gemstone: bool = False      # the top-level Part F gemstone lines

    def windows(self) -> list:
        """Every engine window this call needs in its message - the ones it writes, then the ones its
        briefs merely draw on. Only these are sent, so a call that writes 2028 is not charged for 2046."""
        seen, out = set(), []
        for part in self.parts:
            for chapter in part.chapters:
                for window in list(chapter.windows) + list(chapter.reference_windows):
                    if window["id"] not in seen:
                        seen.add(window["id"])
                        out.append(window)
        return out

    def writable_ids(self) -> set:
        return {w["id"] for part in self.parts for c in part.chapters for w in c.windows}


# ---- Part A - the highlights page ------------------------------------------------------------------

# Part A, items 2-7. Item 1 (lagna / rashi / nakshatra) is plain chapter text; these six are the
# top-level `highlights` object the PDF lays out as cards. `needs` names the engine fact each requires.
HIGHLIGHT_ITEMS = (
    ("mangal", None,
     "`mangal`: `verdict` - is the dosha present, how strong, from which of lagna / Moon / Shukra it is "
     "counted, and whether mitigating factors apply. `remedy` - one practical line. A dosha that is "
     "present is softened, never cancelled."),
    ("sade_sati", None,
     "`sade_sati`: `verdict` - running now or not; if it is, which phase, and if it is not, when the "
     "next cycle begins. `guidance` - one line on what it asks for."),
    ("dasha", None,
     "`dasha`: `mood` - one line on the mahadasha and antardasha running now and what this stretch "
     "feels like. Name the lords."),
    ("strengths", "highlights",
     "`strengths`: exactly three lines, one per entry of `highlights.top_strengths` in the data, in "
     "that order. Name the graha, house or yoga behind each. Do not re-rank and do not add a fourth."),
    ("cautions", "highlights",
     "`cautions`: exactly three lines, one per entry of `highlights.top_cautions`, in that order. Each "
     "entry carries `how_to_frame_it`, and a health-related one carries `health` - follow both exactly. "
     "What the chart asks of this person, never fear, never an illness, never a loss."),
    ("yogas", "yogas",
     "`yogas`: one entry per yoga in `yogas` that is worth the reader's attention - `name` as the data "
     "spells it (in the book's language), `text` one line on what it gives or asks of this person."),
)


def highlight_keys(facts: dict) -> tuple:
    """The Part A items this chart actually has, in the order they are printed on the page.

    The order is `HIGHLIGHT_ITEMS` - the two doshas, then the running dasha, then strengths, cautions
    and the yoga list - and it is the printed order, not an arbitrary one, because this is the page a
    buyer judges the book by. Reorder the tuple, not this function.
    """
    return tuple(key for key, needs, _ in HIGHLIGHT_ITEMS if not needs or facts.get(needs))


def highlights_brief(facts: dict) -> str:
    keys = highlight_keys(facts)
    return "\n".join(f"  - {brief}" for key, _, brief in HIGHLIGHT_ITEMS if key in keys)


def _part_a(facts: dict) -> Part:
    return Part("highlights", "A",
                "the one page a reader takes in sixty seconds and feels is unmistakably about them",
                (Chapter(
                    "at_a_glance",
                    "The opening chapter only, as `bullets`: the lagna, the Moon rashi (with its English "
                    "name once) and the janma nakshatra with its pada - one short plain line each, no "
                    "interpretation beyond a handful of words. Then one `paragraphs` entry of two or "
                    "three sentences saying what this chart is about at its core. The other six "
                    "highlights go in the top-level `highlights` object, not here.",
                    words="one line per bullet, then 60-90 words"),))


# ---- Parts B, C ------------------------------------------------------------------------------------


def _part_b(facts: dict) -> Part:
    chapters = [Chapter(
        "what_your_chart_looks_like",
        "Plain-language orientation to this chart for a reader who does not read charts: the lagna and "
        "its lord and where that lord sits, the Moon's placement, which houses are occupied and which "
        "are empty, and the two or three placements that give this chart its character. The PDF already "
        "prints the chart diagrams and the full planet table from the engine, so describe, never tabulate, "
        "and never list every graha in turn.",
        words="300-450 words")]
    if facts.get("navamsa"):
        chapters.append(Chapter(
            "navamsa",
            "What the navamsa (D9) in `navamsa (D9)` adds: which grahas are vargottama (the same sign in "
            "D1 and D9, which tradition reads as a placement that holds up under pressure), and where the "
            "lagna lord and the 7th lord land in D9. Short, and only about placements actually in that "
            "block.",
            words="150-250 words"))
    return Part("chart_basics", "B", "the reference section: what this chart is", tuple(chapters))


def _part_c(_facts: dict) -> Part:
    return Part("personality", "C", "who this person is, read from the chart", (
        Chapter("nature_and_mind",
                "Nature and mind: the lagna and its lord, the Moon's sign, house and nakshatra, and the "
                "janma nakshatra's lord. How this person meets the world and how they feel things. Name "
                "the placement behind every trait.",
                words="300-450 words"),
        Chapter("drive_and_relating",
                "Drive and relating: Mangal and Surya for energy, temper and initiative; Shukra, the 7th "
                "house and its lord, and Guru for how this person loves, befriends and negotiates. "
                "Include the blind spots, as things to work on rather than faults.",
                words="300-450 words"),
        Chapter("work_money_health",
                "The practical grain of the chart: the 10th house, its lord and Shani for how this person "
                "works; the 2nd and 11th for how money comes and goes; the 6th house and the lagna lord "
                "for constitution and daily habits. Habits and routine only - no diagnosis of any kind.",
                words="300-450 words"),
    ))


# ---- Part D - the timeline (the heart of the book) --------------------------------------------------

_TIMELINE_RULE = (
    "Every prediction here belongs to one of the windows listed for this chapter. For each window you "
    "write, put its `id` in `window_id` - the printed date range is filled in from the engine, so you "
    "never write, shift or invent a date, and you never write an age or a decade. Use each window at "
    "most once. Skip a window only if its data genuinely supports nothing worth saying."
)


def _tuple(windows) -> tuple:
    return tuple(windows)


def _part_d(facts: dict) -> Part:
    timeline = facts["timeline"]
    chapters = []
    if past_entries(timeline):
        chapters.append(Chapter(
            "past", "A thin strip of history, for context and credibility only. One window per mahadasha "
            "the person has already lived, in order, each with a single sentence on what that stretch "
            "asked of them, read from where that mahadasha lord sits in the birth chart. One sentence "
            "each - this section is deliberately the shortest in the book. " + _TIMELINE_RULE,
            shape=WINDOWS, windows=_tuple(past_entries(timeline)), words="one sentence per window"))
    if current_year_windows(timeline):
        chapters.append(Chapter(
            "current_year", "The most detailed section of the book: the year ahead, window by window. For "
            "each window use its antardasha (and pratyantardasha where the data gives one) together with "
            "the transits listed inside that window, and say what the stretch is for - which of career, "
            "money, marriage or relationships, health habits, family, study, property the chart actually "
            "lights up then, and what to do in it. Tag those in `areas`. This is the part the reader will "
            "come back to, so be specific and practical. " + _TIMELINE_RULE,
            shape=WINDOWS, windows=_tuple(current_year_windows(timeline)),
            words="90-150 words per window"))
    for year, windows in near_year_windows(timeline):
        chapters.append(Chapter(
            f"year_{year['year']}", f"The year {year['year']}, in its dated ranges. Head this chapter "
            "with its THEME in a few words and no date at all - not the year, not a month, not a "
            "span; the year is added to the printed heading from the engine, and an empty heading is "
            "better than a long one. Proper depth, not a "
            "summary: for each window name the antardasha shift or transit that defines it and what it "
            "means for this person across the life areas the chart activates then, ending with something "
            "concrete to do. " + _TIMELINE_RULE,
            shape=WINDOWS, windows=_tuple(windows), words="90-140 words per window",
            labels=year["range"].get("labels") or {}))
    for block, windows in far_block_windows(timeline):
        chapters.append(Chapter(
            f"block_{block['range']['start'][:4]}",
            f"The stretch {block['range'].get('label') or block['range']['start'][:4]}, lighter in volume "
            "than the years above but never vague: every statement still sits inside one of the dated "
            "windows below, driven by the mahadasha and antardasha changes in them. Head this chapter "
            "with its THEME in a few words and no date at all - not a year, not a span; the span is "
            "added to the printed heading from the engine, and an empty heading is better than a "
            "long one. " + _TIMELINE_RULE,
            shape=WINDOWS, windows=_tuple(windows), words="70-110 words per window",
            labels=block["range"].get("labels") or {}))
    return Part("timeline", "D", "this person's life in real calendar date ranges", tuple(chapters))


# ---- Part E - life-area deep dives ------------------------------------------------------------------

_AREA_RULE = (
    "Pull the relevant dasha windows into this area's story. NAME A PERIOD BY ITS DASHA - \"the "
    "Rahu-Guru antardasha\", \"the sade-sati peak\", \"the dhaiya now running\" - never by a date you "
    "write and never by naming the sign a graha moves into. The dated windows are Part D's job; this "
    "chapter says what the area looks like and which dasha periods carry it. A transit sign named "
    "here will be rejected, because outside Part D only the birth chart and this year's transits are "
    "checkable.")

_AREA_CHAPTERS = (
    ("career", "Career and profession: the 10th house, its lord, the lagna lord's involvement in work, "
               "Shani and the 6th house. Which kinds of work suit this chart, how this person is best "
               "employed, the windows that favour a move or a push, and where to be patient. " + _AREA_RULE),
    ("money", "Money and wealth: the 2nd and 11th houses and their lords, and where the money-giving "
              "grahas sit. How earnings arrive, what leaks, which windows favour saving, buying or "
              "committing, and which ask for restraint. No investment advice of any kind. " + _AREA_RULE),
    ("marriage", "Marriage and relationships: the 7th house and its lord, Shukra, Guru and the Moon, and "
                 "the mangal dosha position as the data gives it. What kind of partner and partnership the "
                 "chart indicates, and the windows that favour meeting, deciding or deepening. Never tell "
                 "the reader to marry or not to marry. " + _AREA_RULE),
    ("health", "Health, as habits only: the 6th house, the lagna and its lord, and the windows that ask "
               "for more rest, slower decisions or steadier routine. Sleep, food, exercise, rest, pace. "
               "Never name an illness, an organ, a procedure or a body part at risk, and never suggest "
               "anything could be diagnosed from a chart. " + _AREA_RULE),
    ("education", "Education and learning: the 4th and 5th houses, Budha and Guru, and the nakshatra of "
                  "the Moon. What this person learns well and how, and the windows that favour study, "
                  "examinations, a course or a qualification. " + _AREA_RULE),
    ("family_property", "Family, home and property: the 4th house and its lord, the 2nd for family life, "
                        "Mangal and Shani for property and vehicles, and the windows in which home, "
                        "property or a move is indicated. " + _AREA_RULE),
)


# The six life-area deep dives of Part E. These are chapter ids, not window tags: the engine's `AREAS`
# vocabulary is finer (it splits family / property and adds travel, study, spiritual), and a window may
# be tagged with any of those while still being read under one of these six headings.
LIFE_AREA_CHAPTERS = tuple(cid for cid, _ in _AREA_CHAPTERS)


# Which engine area tags speak for each Part E chapter. `family_property` is one chapter in the book
# but two tags in the engine, and `education` absorbs `study`.
_CHAPTER_AREAS = {
    "career": {"career"}, "money": {"money"}, "marriage": {"marriage"},
    "health": {"health"}, "education": {"education", "study"},
    "family_property": {"family", "property"},
}


def _part_e(facts: dict) -> Part:
    timeline = facts["timeline"]
    return Part("life_areas", "E", "one focused reading per pillar of life", tuple(
        Chapter(cid, brief, words="250-400 words",
                reference_windows=tuple(windows_for_areas(timeline, _CHAPTER_AREAS[cid])))
        for cid, brief in _AREA_CHAPTERS))


# ---- Part F - doshas, remedies, gemstone --------------------------------------------------------------


def _part_f(facts: dict) -> Part:
    chapters = [
        Chapter("mangal_dosha",
                "Mangal dosha in full, from `mangal_dosha`: whether it is present, its intensity, Mangal's "
                "house counted from the lagna, the Moon and Shukra exactly as the data gives them, and "
                "which classical mitigating factors apply to this chart and which do not. A dosha that is "
                "present stays present and is softened - never cancelled, nullified or made ineffective. "
                "Then what it actually means day to day, calmly, and what to do about it.",
                words="300-450 words"),
        Chapter("sade_sati",
                "Sade sati from `sade_sati`, and Shani dhaiya from `dhaiya` if it is running: active or "
                "not, the phase, and every phase of the cycle the data lists with its own dates and "
                "what that stretch asks for. Shani as a teacher who rewards effort, not as a threat. "
                "Note that the sign Shani occupies NOW is a transit, not its birth-chart sign - word it "
                "that way ('Shani is currently moving through ...'), or the checker will reject it.",
                words="300-450 words"),
    ]
    if facts.get("yogas"):
        chapters.append(Chapter(
            "other_doshas",
            "Any other dosha or yoga in `yogas` that the data marks present and that has not been covered "
            "yet - named, with its dates where the data gives them, what it asks for and one practical "
            "response. Nothing that is not in the data.",
            words="200-350 words"))
    if supplied(facts)["has_gemstone"]:
        chapters.append(Chapter(
            "gemstone",
            "The gemstones the engine has selected, from `gemstone`: for each entry under `recommended`, "
            "the stone, which graha it serves and why that graha rules for this chart, the metal, the "
            "finger and the day exactly as given, and the classical weight range as `weight` words it. "
            "Then the stones under `avoid`, each with its reason. Use `presentation` and `wearing_note` as "
            "your framing: the tradition's optional suggestion, taken up with a practitioner. Do not name "
            "a price, a shop, a jeweller, a website or a seller, do not say a stone must be energised or "
            "installed by anybody, and never suggest that any harm, loss or delay follows from not "
            "wearing one.",
            words="250-400 words"))
    return Part("doshas_remedies", "F", "doshas, their remedies, and the stone for this chart",
                tuple(chapters))


# ---- Parts G, H ---------------------------------------------------------------------------------------


def _part_g(facts: dict) -> Part:
    years = ", ".join(str(row["year"]) for row in facts["timeline"].get("year_table", []))
    return Part("year_table", "G", "the scannable index to the timeline", (
        Chapter("year_by_year",
                "A single table and nothing else, built from `year_table` in the data: one row per year, "
                f"for {years or 'each of the coming years'}, in that order. Columns: the year, its "
                "mahadasha and antardasha as `year_table` gives them, and one short phrase each for "
                "career, money and relationships in that year, drawn from that year's `pillars` and its "
                "windows in the timeline. Keep every cell under about eight words. Leave `paragraphs` "
                "empty.",
                shape=TABLE, words="a table only"),))


def _part_h(_facts: dict) -> Part:
    return Part("closing", "H", "a short, honest closing", (
        Chapter("closing",
                "Three or four paragraphs: what this chart's real strength is, the one or two habits that "
                "would most repay this person over the coming years, and an encouraging close that does not "
                "promise anything. Do not write a disclaimer - the service appends its own.",
                words="200-300 words"),))


# ---- assembly -------------------------------------------------------------------------------------------

# ---- the Simple tier --------------------------------------------------------------------
#
# NOT a truncated Detailed book. The same chart, the same facts and every one of the same checks, but
# a different and smaller promise: who you are, where you stand now, and what the near term asks for.
#
# What it deliberately does not carry - the twenty-year dated timeline, the six life-area deep dives,
# the year table - is what the Detailed tier sells, and saying so honestly is the reason to upgrade.
# Part D here is the CURRENT dasha and the months ahead only, which is also where the cost goes: the
# far timeline is the expensive half of the Detailed book.


def _simple_part_b(facts: dict) -> Part:
    return Part("chart_basics", "B", "what this chart is", (
        Chapter("what_your_chart_looks_like",
                "One orientation to this chart for a reader who does not read charts: the lagna and "
                "its lord and where that lord sits, the Moon's placement and nakshatra, and the two "
                "or three placements that give this chart its character - what they say about this "
                "person's nature, work and relationships together. The PDF prints the chart and the "
                "planet table from the engine, so describe, never tabulate.",
                words="350-500 words"),))


def _simple_part_d(facts: dict) -> Part:
    """The current dasha and the months ahead. No near years, no far blocks."""
    timeline = facts["timeline"]
    current = current_year_windows(timeline)
    if not current:
        return Part("timeline", "D", "where you stand now", ())
    return Part("timeline", "D", "where you stand now and what the months ahead ask for", (
        Chapter("current_year",
                "The period running now and the months ahead, window by window. For each window use "
                "its antardasha (and pratyantardasha where the data gives one) with the transits "
                "listed inside it, and say plainly what the stretch is for and what to do in it. "
                "This is the whole of this report's timeline, so make each window count. "
                + _TIMELINE_RULE,
                shape=WINDOWS, windows=_tuple(current), words="80-120 words per window"),))


def _simple_part_f(facts: dict) -> Part:
    chapters = [
        Chapter("mangal_dosha",
                "Mangal dosha from `mangal_dosha`: present or not, its intensity, Mangal's house "
                "counted from the lagna, the Moon and Shukra exactly as given, and which classical "
                "mitigating factors apply. A dosha that is present stays present and is softened - "
                "never cancelled. Then what it means day to day, calmly, and what to do about it.",
                words="250-350 words"),
        Chapter("sade_sati",
                "Sade sati from `sade_sati`, and Shani dhaiya from `dhaiya` if it is running: active "
                "or not, which phase, and the dates the data gives. Shani as a teacher who rewards "
                "effort, not as a threat. Note that the sign Shani occupies NOW is a transit, not its "
                "birth-chart sign - word it that way.",
                words="250-350 words"),
    ]
    return Part("doshas_remedies", "F", "where the chart asks for care, and what helps", tuple(chapters))


def _simple_part_h(_facts: dict) -> Part:
    return Part("closing", "H", "a short, honest closing", (
        Chapter("closing",
                "Two or three paragraphs: this chart's real strength, the one or two habits that "
                "would most repay this person, and an encouraging close that promises nothing. Do "
                "not write a disclaimer - the service appends its own.",
                words="150-220 words"),))


_BUILDERS = (_part_a, _part_b, _part_c, _part_d, _part_e, _part_f, _part_g, _part_h)
_SIMPLE_BUILDERS = (_part_a, _simple_part_b, _simple_part_d, _simple_part_f, _simple_part_h)


def build_book(facts: dict, tier: str = "detailed") -> tuple:
    """The concrete parts for one chart: A-H for the Detailed tier, a smaller set for Simple."""
    builders = _SIMPLE_BUILDERS if tier == "simple" else _BUILDERS
    parts = [build(facts) for build in builders]
    return tuple(part for part in parts if part.chapters)


def _slice(part: Part, chapters) -> Part:
    return Part(part.id, part.label, part.brief, tuple(chapters))


def plan(book: tuple, tier: str = "detailed") -> list:
    """Split the book into Sonnet calls. Short parts share a call; Part D and Part E are split
    because they are the long ones, so a retry never regenerates more than a few chapters."""
    by_id = {part.id: part for part in book}
    calls, timeline = [], by_id.get("timeline")

    if tier == "simple":
        # Three calls, sharing the prefix the chart has already paid for. Part A carries the
        # highlights object, the timeline call carries the only windows, and B+F+H share the last.
        def simple(key, *parts, **kwargs):
            chosen = [part for part in parts if part is not None and part.chapters]
            if chosen:
                calls.append(Call(key, tuple(chosen), **kwargs))

        simple("S-A", by_id.get("highlights"), wants_highlights=True)
        simple("S-now", timeline)
        remedies = by_id.get("doshas_remedies")
        simple("S-rest", by_id.get("chart_basics"), remedies, by_id.get("closing"),
               wants_remedies=bool(remedies), wants_front_matter=True)
        return calls

    def call(key, *parts, **kwargs):
        chosen = [part for part in parts if part is not None and part.chapters]
        if chosen:
            calls.append(Call(key, tuple(chosen), **kwargs))

    call("A", by_id.get("highlights"), wants_highlights=True)
    call("BC", by_id.get("chart_basics"), by_id.get("personality"))

    if timeline:
        # ONE CHAPTER PER CALL, and the reason is measured rather than assumed.
        #
        # This used to be sized by WINDOW count with a cap of ten, after two calls - "19 windows
        # (past + current year)" and "17 (four far blocks)" - wrote their first chapter properly and
        # returned the rest empty. The cap helped, so the cause looked like output length. It was not:
        # asked for `year_2030` + `year_2031`, five windows between them, Sonnet wrote 2030 in full and
        # abandoned 2031 in BOTH languages - in Marathi as a part carrying a written heading and no
        # body, in English as a part it named `year_2031_placeholder_unused`. stop_reason was
        # `end_turn` both times and the output was a sixth of the cap, so nothing was truncated, and
        # the prompt already says a chapter is never a top-level entry. It is the SECOND CHAPTER that
        # gets dropped: both of the original failures were multi-chapter calls (2 and 4), and the
        # window cap only ever helped because cutting windows happened to cut chapters with them.
        #
        # A single chapter is written reliably at fifteen windows (`D-now` on a real chart), so the
        # unit is the chapter and the window count is not the variable. The extra calls are nearly
        # free: they read the same cached prefix, which is also why the old note called them cheap.
        chapters = {"past": [], "current": [], "years": [], "blocks": []}
        for chapter in timeline.chapters:
            if chapter.id == "past":
                chapters["past"].append(chapter)
            elif chapter.id == "current_year":
                chapters["current"].append(chapter)
            elif chapter.id.startswith("year_"):
                chapters["years"].append(chapter)
            else:
                chapters["blocks"].append(chapter)
        for n, chapter in enumerate(chapters["past"], 1):
            call(f"D-past{n}" if n > 1 else "D-past", _slice(timeline, [chapter]))
        for n, chapter in enumerate(chapters["current"], 1):
            call(f"D-now{n}" if n > 1 else "D-now", _slice(timeline, [chapter]))
        for n, chapter in enumerate(chapters["years"], 1):
            call(f"D-year{n}", _slice(timeline, [chapter]))
        for n, chapter in enumerate(chapters["blocks"], 1):
            call(f"D-far{n}", _slice(timeline, [chapter]))

    areas = by_id.get("life_areas")
    if areas:
        call("E1", _slice(areas, areas.chapters[:3]))
        call("E2", _slice(areas, areas.chapters[3:]))

    remedies = by_id.get("doshas_remedies")
    call("F", remedies, wants_remedies=True,
         wants_gemstone=any(c.id == "gemstone" for c in (remedies.chapters if remedies else ())))
    call("GH", by_id.get("year_table"), by_id.get("closing"), wants_front_matter=True)
    return calls


def chapter_ids(book: tuple) -> list:
    return [(part.id, chapter.id) for part in book for chapter in part.chapters]


__all__ = ["AREAS", "Call", "Chapter", "HIGHLIGHT_ITEMS", "LIFE_AREA_CHAPTERS", "Part", "build_book",
           "chapter_ids", "highlight_keys", "highlights_brief", "plan", "PLAIN", "TABLE", "WINDOWS"]
