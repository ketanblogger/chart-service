"""Every defect this project has actually produced, pinned so it can never come back quietly.

READ THIS BEFORE LOOSENING A CHECK.

These are not synthetic examples. Each one is a real string a real model produced for the reference
chart, and each is annotated with when it happened. They live in their own file, away from the tests
that describe intended behaviour, because their job is different: they are the memory of what has
already gone wrong.

**The rule this file exists to enforce:** loosening a validator rule - for any reason, including a
justified one - requires re-running this file. A rule that no longer catches its own defect has been
broken, not relaxed. Rewrite it so it catches the defect and not the false positive; do not delete
the case, and do not weaken the assertion to match the new behaviour.

**Why the rule is needed.** The pressure here runs one way. A false positive is loud and expensive -
it fails a paid generation, costs rupees, and someone is watching a run fail. A false negative is
silent and free today: the book generates, the checks pass, and a wrong date or an invented dignity
claim reaches a customer who paid ₹49 for it. Six of these checks were loosened inside half an hour
during one afternoon of live runs, every loosening individually correct. This file is what makes the
cumulative version of that safe.

THE CHART CHANGED, AND EACH CASE WAS REWORKED RATHER THAN RENAMED. These defects were produced for a
different chart, and a find-and-replace would have left cases that still pass while proving nothing -
"Guru enters your 9th house" is only a defect because that chart's lagna sign was also its 9th from
the Moon. The reference chart is now KALAM (15 Oct 1931, Rameswaram): Karka lagna, Vrishchika Moon,
Anuradha pada 3. It was chosen partly because it reproduces the shipped defect exactly - Guru enters
KARKA on 25 January 2027, which is house 1 from this lagna and the 9th only from this Moon, the same
shape as the sentence that reached a live transcript. Where a case could not be made equivalent it
says so rather than being kept as decoration.
"""

import datetime as dt

import pytest

from app.ai import engine_facts
from app.ai.report import Birth, _chart, book_facts
from app.ai.safety import screen_text
from app.ai.validator import (
    check_text,
    filler_issues,
    narrow_to_window,
    near_horizon,
    untranslated_heading,
    untraceable_issues,
    written_range_issues,
)

from tests.reference_charts import AS_OF as REFERENCE_AS_OF
from tests.reference_charts import KALAM as PRIMARY

AS_OF = REFERENCE_AS_OF.date()
KALAM = Birth(dt.date.fromisoformat(PRIMARY.request()["date"]),
              dt.time.fromisoformat(PRIMARY.request()["time"]),
              PRIMARY.request()["lat"], PRIMARY.request()["lon"],
              PRIMARY.request()["timezone"], PRIMARY.place)


@pytest.fixture(scope="module")
def engine_data():
    chart = _chart(KALAM, AS_OF)
    return chart, engine_facts.report_facts(chart, AS_OF)


@pytest.fixture(scope="module")
def unscoped(engine_data):
    """The raw whole-book fact set. **Production never checks prose against this** - see
    `test_no_prose_is_ever_checked_against_the_unscoped_fact_set`. It is here only as the base the
    two real scopes are derived from, and to make that distinction explicit rather than implicit."""
    chart, report = engine_data
    return book_facts({"chart": chart, **report})


@pytest.fixture(scope="module")
def facts(unscoped, engine_data):
    """What Parts A, B, C, E, F and H prose is actually checked against: the birth chart plus the
    current year's transits. Over a twenty-year book the unscoped set has every slow graha in every
    sign, so a transit claim checked against it cannot fail."""
    _, report = engine_data
    return near_horizon(unscoped, report["timeline"])


@pytest.fixture(scope="module")
def guru_window(engine_data, facts):
    """Scoped to the window Guru enters Simha in (Oct-Nov 2026), as Part D prose is checked."""
    _, report = engine_data
    window = next(w for w in engine_facts.all_windows(report["timeline"]).values()
                  if any(t["graha"]["key"] == "Jupiter" and t["date"].startswith("2027-01")
                         for t in w.get("transits") or []))
    return narrow_to_window(facts, window)


@pytest.fixture(scope="module")
def surya_transit(engine_data, facts):
    """(checker, house) for a window in which Surya transits a house it does NOT occupy natally.

    The house number is taken from the window rather than written here. The first draft of this
    fixture picked the window by the same condition but then asserted a hard-coded "9th", landed on a
    window where Surya is in the 4th, and the three assertions all passed for the wrong reason - the
    claim really was false there. A fixture that selects a window must read its numbers from the same
    window it selected.
    """
    chart, report = engine_data
    natal = chart["grahas"]["Sun"]["house"]
    for window in engine_facts.all_windows(report["timeline"]).values():
        for transit in window.get("transits") or []:
            if transit["graha"]["key"] == "Sun" and transit["house_from_lagna"] != natal:
                return narrow_to_window(facts, window), transit["house_from_lagna"]
    raise AssertionError("no window has Surya transiting outside its natal house")


def kinds(text, checker):
    return {issue.kind for issue in check_text(text, checker)}


# ---- the one that reached a customer-facing surface -------------------------------------------------


def test_a_from_moon_house_written_as_a_from_lagna_house(guru_window):
    """SHIPPED. Found by hand in a live consultation transcript, 2026-09-21.

    The original sentence named Simha, which was that chart's LAGNA - the 1st house - and the 9th only
    counted from its Moon. The model wrote the from-Moon count as though it were the chart's own house
    numbering, which is the numbering the printed chart uses, so the reader would have compared it to
    their chart and found it wrong.

    On THIS chart the identical trap exists with the same numbers: Guru enters Karka on 25 January
    2027, Karka being the lagna (house 1) and the 9th only from the Vrishchika Moon. The case is
    therefore transferred, not weakened.

    This case is also the reason the own-sign subject rule must stay narrow: that rule changed how a
    sentence's subject is identified, and this assertion is what proves the house rule was not
    collateral damage.
    """
    assert "house" in kinds("Guru also enters your 9th house transit-wise around 25 January 2027.",
                            guru_window)
    assert "house_sign" in kinds("Guru bhi 25 January 2027 ko aapke 9th house (Karka) mein pravesh karega.",
                                 guru_window)
    assert "house_sign" in kinds("25 जानेवारी 2027 रोजी गुरू कर्क राशीत, म्हणजे नवम भावात प्रवेश करतो.",
                                 guru_window)
    # and the correct forms still pass, or the rule is useless
    assert check_text("Guru enters Karka, your 1st house (9th from your Moon sign), on 25 January 2027.",
                      guru_window) == []


# ---- invented facts ---------------------------------------------------------------------------------


def test_an_invented_date(facts):
    """Live English run, compact mode: a sade-sati date the engine never produced."""
    assert "date" in kinds("Your next sade-sati begins on 8 June 2044.", facts)
    assert "date" in kinds("Your Budha antardasha ends on 14 March 2027.", facts)


def test_invented_dignity_claims(facts, guru_window):
    """Live Marathi report run 1, and live chat run 2, reworked for this chart.

    On the original chart the false claims were about Budha in Makara and Guru in Vrishchika. Here
    Shani sits in Dhanu (Guru's sign) and Guru in Karka (Chandra's sign), so the same shape of claim
    is still false - while Shukra in Tula genuinely IS its own sign, which is the control below.

    Asserted in BOTH scopes production uses - near horizon and a window - because the rule reads
    in-scope transits for slow grahas, and a claim that survives one scope but not the other would
    be a hole.
    """
    for claim in ["त्याचा स्वामी शनी षष्ठ भावात स्वतःच्याच धनु राशीत बसलेला आहे.",
                  "शनी धनु राशीत स्वतःच्याच राशीत आहे.",
                  "Shani sits in the sixth house in its own sign Dhanu.",
                  "Guru is in its own sign in Karka.",
                  "With Guru (your 6th lord) placed strongly in its own sign in the 1st house, growth follows."]:
        assert "dignity" in kinds(claim, facts), f"near horizon: {claim}"
        assert "dignity" in kinds(claim, guru_window), f"window scope: {claim}"
    # Shukra genuinely IS in its own sign here, and saying so must not be flagged
    assert check_text("Shukra sits in the fourth house in Tula, Venus's own sign.", facts) == []


def test_KNOWN_LIMIT_a_wrong_year_on_a_correct_placement_passes_in_non_window_prose(facts):
    """**This is a gap, pinned deliberately. Read it before widening anything.**

    `near_horizon` narrows PLACEMENTS to the birth chart plus the current year's transits. It does
    NOT narrow dates, months or years: those stay whole-book, because Part G's table legitimately
    names every year in the report and Part E names periods years out. The two are checked
    independently, so a date and a placement that are each individually valid pass together even
    when the pairing is wrong:

        "Shani enters Vrishabha in 2031."  -> caught: Vrishabha is not a near-horizon Shani sign
        "Shani enters Mithuna in 2032."    -> caught: same
        "Shani enters Mesha in 2031."      -> NOT caught: Shani really does enter Mesha (in 2027,
                                              inside the current-year window) and 2031 really is a
                                              year in the report - but four years apart

    So the honest statement of the guarantee is: **placements are narrowed; a date paired with an
    in-scope placement is not.** In non-window prose the model may name a date, and a wrong one
    attached to a correct sign will pass.

    Why it is not fixed here: narrowing dates in non-window prose would reject Part G's year table
    and every legitimate mention of a future period, which is how false positives come back. The
    containment is in the prompt instead - BOOK_SYSTEM_PROMPT tells the writer that outside the
    timeline chapters a period is named by what it is ("the Rahu-Guru antardasha"), not by a date -
    and in the structure: dated claims belong in windows, where both halves are scoped together.

    If you do fix this, the shape is probably pairing the date with the placement (does THIS graha
    reach THIS sign within the window containing THAT date), not widening the date rule.
    """
    assert kinds("Shani enters Vrishabha in 2031.", facts) == {"sign"}
    assert kinds("Shani enters Mithuna in 2032.", facts) == {"sign"}
    assert kinds("Shani enters Mesha in 2031.", facts) == set(), (
        "this gap has been closed - good. Update this test to assert the new behaviour and move it "
        "out of KNOWN_LIMIT")


def test_the_prompt_tells_non_window_prose_not_to_name_dates(facts):
    """The containment for the gap above is a prompt rule, so it has to actually be in the prompt."""
    from app.ai.prompts import BOOK_SYSTEM_PROMPT

    assert "Outside the timeline chapters, refer to a period by what it is" in BOOK_SYSTEM_PROMPT


def test_no_prose_is_ever_checked_against_the_unscoped_fact_set(engine_data, unscoped):
    """The scoping above is only honest if production really never uses the raw whole-book facts.

    Over twenty years every slow graha visits every sign, so against the unscoped set the defect that
    actually shipped - "Guru also enters your 9th house" - passes. That is not a bug in the fact set;
    it is why `find_problems` hands every slot either its window's scope or the near horizon. This
    test is what stops someone "simplifying" that away.
    """
    from app.ai.book_report import find_problems

    chart, report = engine_data
    shipped = "Guru also enters your 9th house transit-wise around 25 January 2027."
    assert check_text(shipped, unscoped) == [], (
        "the unscoped set is expected to miss this - if it now catches it, the timeline shrank and "
        "this test's premise needs rechecking")

    windows = engine_facts.all_windows(report["timeline"])
    window_id = next(w["id"] for w in windows.values()
                     if any(t["graha"]["key"] == "Jupiter" and t["date"].startswith("2027-01")
                            for t in w.get("transits") or []))

    class _Chapter:
        id, shape, windows, labels = "current_year", "windows", (), {}

    class _Part:
        id, label, brief, chapters = "timeline", "D", "", (_Chapter(),)

    class _Call:
        key, parts = "D", (_Part(),)
        wants_front_matter = wants_remedies = wants_highlights = wants_gemstone = False

    body = {"parts": [{"id": "timeline", "heading": "x", "intro": "", "chapters": [
        {"id": "current_year", "heading": "x", "paragraphs": [], "bullets": [], "table": None,
         "windows": [{"window_id": window_id, "headline": "x", "paragraphs": [shipped],
                      "areas": [], "area_lines": []}]}]}]}
    found = find_problems(_Call(), body, unscoped, False, windows, "en", report["timeline"])
    assert "house" in {p["kind"] for p in found}, (
        "the shipped defect passed through find_problems - prose is no longer being scoped")

    # `dignity` is inert against the unscoped set for the same reason, and this was worth an hour:
    # a hand-run of the own-sign cases against `collect_facts(PRIMARY.chart(detail="full"))` showed
    # ALL of them passing, which looks exactly like the rule being switched off. It was not - over
    # twenty years Guru visits Dhanu and Meena, its own signs, so "its own sign" cannot fail there.
    # Production never checks prose against this set; the line below is what says so out loud.
    #
    # The risk is real and worth naming: `dignity` is now blocking, and a blocking rule that has gone
    # inert looks identical to a passing suite. Anyone verifying it by hand must scope the facts the
    # way `find_problems` does, or they are measuring the fact set rather than the rule.
    shipped_dignity = ("Guru (Jupiter), the great benefic, sits in your first house itself, in Karka, "
                       "its own sign of exaltation.")
    assert check_text(shipped_dignity, unscoped) == [], (
        "the unscoped set is expected to miss this too - if it now catches it, the timeline shrank")
    assert "dignity" in {issue.kind for issue
                         in check_text(shipped_dignity, near_horizon(unscoped, report["timeline"]))}, (
        "scoped to the near horizon it MUST fire - this is the sentence that reached a finished book")


def test_a_transit_sign_asserted_as_a_natal_placement(facts, guru_window):
    """Live Marathi report at effort low, reworked. On this chart Guru only TRANSITS Simha (Oct 2026);
    natally it is in Karka. This is what the natal-vs-transit separation exists for, and a slow graha
    visiting every sign over a twenty-year book is what makes it easy to lose."""
    assert "sign" in kinds("With Guru in Simha alongside the Moon you are wise.", facts)
    assert "sign" in kinds("सिंह राशीत गुरू आणि चंद्र एकत्र असल्यामुळे शिक्षण केंद्रस्थानी आहे.", facts)
    # inside a window, a sign Guru does not reach in THAT window is wrong even though it is real later
    assert "sign" in kinds("Guru moves into Kanya this month.", guru_window)


def test_a_true_transit_house_written_bare_as_a_natal_one(surya_transit):
    """Live Simple run, 22 Sep 2026, effort medium. Surya really does enter house 9 on 15 March 2027,
    and the model said so correctly in the window's paragraph - "Surya's move into your 9th house" -
    then wrote the same fact in the window's one-line `education` entry as "Surya in your 9th house".
    Natal Surya is in house 3, so the bare form is a natal claim and a false one; the line was cut.

    The checker is RIGHT here and must stay right: the shipped defect this file opens with was exactly
    a transit read as a natal placement. What was wrong was the prompt, which never said that the
    movement verb is load-bearing, so the model dropped it wherever words were scarce - the short area
    lines. Three live runs paid retries for it (two at effort low, one Simple).

    The checker needs NO change for this: it already reads "moves into" and "enters" as transits and
    only the bare form as natal. That is the whole point - the rule was right and the prompt never
    told the model the distinction existed. Nothing here is loosened.

    So this case pins BOTH halves. If the prompt rule is ever dropped, the assertions below still
    pass and nothing complains, which is why the prompt itself is asserted separately.
    """
    checker, house = surya_transit
    assert "house" in kinds(f"Surya in your {house}th house favours long-term direction.", checker)
    for worded_as_a_transit in (f"Surya moves into your {house}th house, favouring long-term direction.",
                                f"Surya enters your {house}th house this month.",
                                f"Surya's move into your {house}th house favours reflection."):
        assert check_text(worded_as_a_transit, checker) == [], worded_as_a_transit


def test_your_own_sign_is_the_readers_lagna_not_the_grahas(facts):
    """THE FALSE POSITIVES, and the reason `dignity` could be promoted to blocking at all.

    Three sentences were rejected across two live runs, all true, all the same shape: "Jupiter back
    in your own sign", "Guru sits retrograde in your own sign", "Guru Returns to Your Own Sign". The
    graha was transiting that chart's LAGNA sign, and "your own sign" is ordinary Jyotish for the
    native's rashi. The rule read the second-person possessive as if it were "its own" and checked it
    against the graha's `in_own_sign`, costing a regeneration each time.

    Those three were produced for the retired chart, whose lagna was Simha; this is the same shape on
    PRIMARY, whose lagna is Karka. The construction carries the case, not the sign - so the sentences
    are reworked rather than renamed, as the header requires.

    This is a subject-identification fix, not a seventh loosening: the same misreading once made
    "Simha lagna with Shani seated firmly in its own sign" fail. Both halves must keep passing
    together - fixing one by breaking the other is the failure this file exists to prevent.
    """
    for true_sentence in ("With the dhaiya lifted and Guru back in your own sign, this is supportive.",
                          "Keep your pace steady while Guru sits retrograde in your own sign.",
                          "Guru Returns to Your Own Sign"):
        assert check_text(true_sentence, facts) == [], true_sentence
    # and the check the rule could not make before: a NAMED sign must actually be the lagna
    assert "dignity" in kinds("Guru returns to your own sign Simha this year.", facts)
    assert check_text("Guru returns to your own sign Karka this year.", facts) == []

    # THE HOLE THE FIRST VERSION OF THIS FIX OPENED, found by diffing the new rule against the old
    # one rather than by testing the cases the fix was written for. "your own sign" with no sign
    # named is still a placement claim - it says the graha is in the LAGNA rashi - and the first
    # branch returned early as "nothing to verify", silently switching off a check the old rule got
    # right. Guru is natally in Karka, the lagna, so its sentence is true; Shani is in Dhanu, so its
    # sentence is false and must fail.
    assert check_text("Guru sits in your own sign.", facts) == []
    assert "dignity" in kinds("Shani sits in your own sign.", facts)
    assert "dignity" in kinds("Shani is placed in your own sign and steadies you.", facts)

    # THE POSSESSIVE MUST BE ATTACHED, NOT MERELY PRESENT. A book paragraph says "your" constantly -
    # "your 7th house", "your Moon" - and if any of those counted, the rule would switch itself off
    # for the rest of the sentence. Third person immediately before the phrase is decisive whatever
    # appears earlier; `_RE_THIRD_PERSON_OWNS` states that in words so it survives the `$` anchor on
    # `_RE_READER_OWNS_EN` being edited away.
    for still_about_the_graha in (
            "Your lagna is Karka and your temperament is steady, and Guru sits in Karka, its own sign of exaltation.",
            "Because your 7th house is strong, Shani rests in its own sign Dhanu.",
            "Guru, in his own sign of exaltation Karka, steadies the chart.",
            "Guru and its dispositor sit in Karka, their own sign of exaltation."):
        assert "dignity" in kinds(still_about_the_graha, facts), still_about_the_graha
    # ... and a distant "your" still does not stop a genuine "your own sign" from being reader-owned
    assert check_text("Your lagna is Karka and your Moon is deep in Vrishchika, so when Guru "
                      "comes back to your own sign the mood steadies.", facts) == []
    # Devanagari takes the same decision from the matched phrase itself, never from a prefix of the
    # text, so a distant तुमच्या cannot reach a स्वतःच्या phrase. All the recorded Devanagari cases
    # were short, which is exactly why this long one is here.
    assert "dignity" in kinds("तुमच्या पहिल्या घरात गुरू आहे आणि शनी स्वतःच्या राशीत आहे.", facts)
    assert check_text("गुरू तुमच्या राशीत परत येतो.", facts) == []


def test_KNOWN_LIMIT_one_own_sign_graha_excuses_the_others_in_the_same_sentence(facts):
    """Pre-existing and deliberate, verified identical before and after the subject fix.

    With no sign bound at the phrase the rule passes the sentence if ANY graha named in it is in its
    own sign - the precision-first trade recorded in `check_own_sign`. So the shipped defect was
    caught partly by luck: its sentence named Guru alone. Add a graha that IS in its own sign and the
    same false claim about Guru goes through, because Shukra is in Tula and Tula is Shukra's.

    Not fixed here. Tightening it means picking a subject among several grahas, which is the exact
    judgement that produced the "Simha lagna with Shani seated firmly in its own sign" false positive.
    Recorded so the limit is known rather than discovered again.
    """
    assert check_text("Your 4th house holds Mangal and Shukra, and Guru sits in Karka, "
                      "its own sign of exaltation.", facts) == []


def test_own_sign_of_exaltation_is_a_contradiction(facts):
    """SHIPPED, twice. Both medium Detailed runs wrote "Guru ... in Karka, its own sign of exaltation".
    Guru IS exalted in Karka, and Karka is Chandra's sign, not Guru's - own sign and exaltation are
    different dignities and are never the same sign for one graha.

    The checker caught it on all three BC attempts and it shipped anyway, because `dignity` was in
    SOFT_KINDS. It is blocking now (validator.REDACT_KINDS), so this sentence would cost a retry and,
    if it survived, the paragraph - which is the cheaper mistake against a factual error about the
    customer's own chart.

    THE FIRST LINE BELOW IS THE EXACT STRING THAT REACHED A FINISHED BOOK, byte for byte. It is
    pinned verbatim rather than paraphrased because a paraphrase is a different test: this sentence
    also contains "your first house" earlier in it, and any future attempt to detect the
    second-person possessive by scanning the sentence instead of the words attached to the phrase
    would route it to the lagna branch, where Karka IS the lagna and it would pass. The verbatim
    string is what makes that regression impossible to miss.
    """
    from app.ai.prompts import BOOK_SYSTEM_PROMPT

    shipped = ("Guru (Jupiter), the great benefic, sits in your first house itself, in Karka, "
               "its own sign of exaltation.")
    assert "dignity" in kinds(shipped, facts)
    assert "dignity" in kinds("Guru sits in Karka, its own sign of exaltation.", facts)
    assert "dignity" in kinds("Guru (Jupiter) sits in Karka, its own sign of exaltation.", facts)
    # the prompt half: the phrase is wrong for every chart, so it needs no heuristic to judge
    assert "own sign of exaltation" in BOOK_SYSTEM_PROMPT
    assert "different dignities" in BOOK_SYSTEM_PROMPT


def test_the_prompt_keeps_the_machinery_out_of_the_prose():
    """Live runs, 21-22 Sep 2026, both tiers. "the engine finds a strong Vipreeta Raja Yoga", "the data
    marks its intensity as high", "the yogas the engine has found in this chart" - four distinct
    sentences in the Detailed book and two in the Simple one, in prose a customer pays for.

    Nothing was factually wrong, so no checker fired and nothing would have. The cause is that the
    prompt itself says "the data" on nearly every line, because it is addressed to the writer - and the
    writer picked the phrase up and used it on the reader. The fix is the prompt telling it not to,
    which is only as durable as this test.
    """
    from app.ai.prompts import BOOK_SYSTEM_PROMPT

    assert "Never name the machinery in the prose" in BOOK_SYSTEM_PROMPT
    assert "addressed to the reader" in BOOK_SYSTEM_PROMPT
    # Second pass. The first version of this bullet QUOTED the offending sentences as examples of what
    # not to write, and the phrase that survived into the next live book was one of those examples,
    # word for word. An illustration is a sample the model may copy, not only a rule it may follow.
    # The rule now forbids the strings and shows only correct output; these assert it stayed that way.
    assert '"the data" and "the engine" must not appear' in BOOK_SYSTEM_PROMPT
    assert "in any capitalisation" in BOOK_SYSTEM_PROMPT
    forbidden_shown_as_samples = ('"The engine finds', '"the data marks', '"the data places')
    for sample in forbidden_shown_as_samples:
        assert sample not in BOOK_SYSTEM_PROMPT, sample


def test_the_prompt_says_the_movement_verb_is_load_bearing():
    """The fix for the defect above is a prompt rule, not a validator change - so the rule is the
    thing that has to be pinned. Deleting it to save prefix tokens would silently bring the retries
    back, and the retries cost more than the tokens."""
    from app.ai.prompts import BOOK_SYSTEM_PROMPT

    assert "movement verb" in BOOK_SYSTEM_PROMPT
    assert "ALWAYS means the birth chart" in BOOK_SYSTEM_PROMPT


def test_a_wrong_sign_after_a_movement_verb(guru_window):
    """The sign check used to fire only on "in <sign>", so "enters <sign>" walked past it."""
    for wrong in ["Guru enters Mesha on 25 January 2027.", "Shani shifts into Vrishabha here.",
                  "Guru returns to Meena this month."]:
        assert "sign" in kinds(wrong, guru_window), wrong
    assert check_text("Guru enters Karka on 25 January 2027.", guru_window) == []


def test_fact_types_the_engine_never_computes(facts):
    """Aspects, dignity and the D9 ARE computed and may be discussed. These are not."""
    for invented in ["Your dashamsha (D10) points to administration.",
                     "The ashtakavarga gives this house six bindus.",
                     "There is a planetary war between Shani and Mangal.",
                     "शनी आणि मंगळ यांच्यात ग्रहयुद्ध आहे."]:
        assert "untraceable" in {i.kind for i in untraceable_issues(invented, facts)}, invented


# ---- wording that changes the meaning ----------------------------------------------------------------


def test_a_present_dosha_described_as_cancelled(facts):
    """The engine's cancellations never flip `present`; they soften. "Cancelled" tells the reader the
    opposite of what the data says."""
    assert facts.mangal_present
    for wrong in ["मंगळ दोष प्रभावहीन ठरतो.", "तुमच्या कुंडलीतील मंगळ दोष प्रभावहीन ठरतो.",
                  "So the dosha is cancelled for your chart.", "इसलिए आपका मंगल दोष रद्द हो जाता है।"]:
        assert "wording" in kinds(wrong, facts), wrong
    assert check_text("The mitigating factors soften the dosha considerably.", facts) == []


# ---- things that would have reached the page ----------------------------------------------------------


def test_a_model_written_date_range_inside_a_window(facts):
    """The engine's label is printed above the window's text. A second range written by the model can
    only duplicate it or contradict it, and it bypasses the engine's formatter entirely."""
    for wrong in ["Jan 2028 – May 2028 brings steady work.", "From Jan to May 2028 things settle.",
                  "जानेवारी 2028 ते मे 2028 या काळात प्रगती आहे."]:
        assert [i.kind for i in written_range_issues(wrong)] == ["date_range"], wrong


def test_an_english_heading_in_a_devanagari_book():
    """Found in a rendered Marathi book: the year and block chapters came back headed "Year 2028" and
    "Block 2032", which the auto-generated contents page prints on page two. Every other check passed."""
    for wrong in ["Year 2028", "Block 2032", "Doshas Remedies", "Career and Profession"]:
        assert untranslated_heading(wrong, "mr") is not None, wrong
        assert untranslated_heading(wrong, "hi") is not None, wrong
    for fine in ["वर्ष 2028", "2032 – 2036", "मीन (Pisces) मधील प्रवास"]:
        assert untranslated_heading(fine, "mr") is None, fine


def test_generic_filler_that_would_read_the_same_in_anyones_book():
    """Nothing generic may be pasted in to fill space ("kuch bhi chipkana nahi"). The gemstone-chapter
    exemption widened the anchor set, so
    this pins that ordinary padding is still caught."""
    padding = ("You have a great deal of potential within you, and if you keep working steadily and "
               "believe in yourself the results will surely come in time, because honest effort is "
               "always rewarded in the end and good things come to those who are patient.")
    assert [i.kind for i in filler_issues(padding)] == ["filler"]
    assert [i.kind for i in filler_issues("In conclusion, Guru in the 1st house rewards patience.")] \
        == ["boilerplate"]


# ---- safety -------------------------------------------------------------------------------------------


def test_forbidden_topics_in_all_three_languages():
    """The gemstone policy reversal added an `allow_gemstone` path. None of these may travel through it."""
    for text, category in [("There is a danger of a fatal accident in 2027.", "catastrophe"),
                           ("या काळात कुटुंबात मृत्यूची शक्यता आहे.", "death"),
                           ("तुम्हाला कर्करोग किंवा हृदयविकाराचा झटका येऊ शकतो.", "illness"),
                           ("वाहन दुर्घटना और तलाक के योग हैं।", "catastrophe")]:
        assert category in {hit.category for hit in screen_text(text)}, text
        assert category in {hit.category for hit in screen_text(text, allow_gemstone=True)}, text


def test_the_gemstone_chapter_may_name_a_stone_but_never_sell_one():
    """The book's gemstone chapter reversed a blanket ban on naming stones. The ban on SELLING one did
    not move."""
    for selling, category in [("A good ruby costs around 12000 rupees from a reputable jeweller.", "hard_sell"),
                              ("Buy a 5 carat Manikya online and have it energised.", "hard_sell"),
                              ("Without this stone your career will stall.", "gem_fear"),
                              ("You must wear this stone for the dosha to soften.", "gem_fear"),
                              ("Consult an astrologer before you wear it.", "hard_sell"),
                              ("नीलम रत्नाची किंमत साधारण बारा हजार रुपये असते.", "hard_sell")]:
        assert category in {h.category for h in screen_text(selling, allow_gemstone=True)}, selling
    # naming a stone is a hit everywhere the carve-out does not apply
    assert "gemstone" in {h.category for h in screen_text("Wear a blue sapphire.")}
    assert screen_text("Tradition suggests Manikya for Surya, worn on a Sunday in gold.",
                       allow_gemstone=True) == []
