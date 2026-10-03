"""Is the text the language we asked for, and what can be corrected without asking the model again?

app/ai/language.py holds the checks (shared by the free rashifal and the paid reports since B1) and
`fix_language`, which corrects the handful of things that have exactly one right answer.

The reason this file exists: B1 made the Marathi defects VISIBLE in the paid book without making them stop.
A `wording` finding is deliberately not worth regenerating a part, so a real Marathi report generated with the
live model on 2026-09-29 shipped `गुरु` forty-one times, every one of them recorded as a warning that nobody
was ever going to act on. Detection is not correction, and a customer reads the text, not meta.checks.
"""

import re

import pytest

from app.ai.language import _MR_WRONG_WORDS, fix_language, language_problems, names_a_house, normalise_digits

FIXABLE = [(pattern, correct, fix) for pattern, correct, fix in _MR_WRONG_WORDS if fix]
UNFIXABLE = [(pattern, correct, fix) for pattern, correct, fix in _MR_WRONG_WORDS if not fix]


def test_only_the_words_with_one_right_answer_are_corrected_and_nothing_else_is():
    """What is mechanical and what is not. A word is substituted only where there is exactly ONE right
    Marathi form and it is ONE WHOLE TOKEN: the five graha and sign spellings, plus the three B4 added on
    2026-09-29. Everything else in the table needs a sentence rewritten and stays the model's job - the
    ordinal rule because its answer depends on which ordinal matched, ढैया because अडीचकी is feminine where
    ढैया is masculine so the word BEFORE the match has to change too, and "लग्नाची अचूक अंश" because the
    gender runs on past the phrase and a three-token replacement would leave the rest of the sentence
    disagreeing with it - corrected enough to escape the check, not enough to be right. The table is the single source
    for both, so the fixer cannot correct something the checker does not look for, or miss something it does.

    शततारका joined on 2026-09-30 with the advisor's nakshatra ruling. मूळ did NOT, although it is the third
    spelling in the same ruling: see the comment beside it in app/ai/language.py - मूल is the ordinary Marathi
    word for a child, so the name tables spell it and the checker leaves it alone."""
    assert len(FIXABLE) == 9
    assert {fix for _, _, fix in FIXABLE} == {"मंगळ", "शनी", "गुरू", "राहू", "केतू", "धनू", "पुनर्वसू",
                                              "चंद्रबळ", "शततारका"}
    assert all(len(fix.split()) == 1 for _, _, fix in FIXABLE)  # one whole token, never a phrase
    assert len(UNFIXABLE) >= 20
    # "अत्यंत / अतिशय" is two possible answers, `तुला राश` overlaps the next word: neither is substitutable
    assert any("अत्यंत" in correct for _, correct, _ in UNFIXABLE)


@pytest.mark.parametrize("wrong, right", [("मंगल", "मंगळ"), ("शनि", "शनी"), ("गुरु", "गुरू"),
                                          ("राहु", "राहू"), ("केतु", "केतू")])
def test_a_corrected_sentence_no_longer_carries_the_finding_it_had(wrong, right):
    """The guarantee, asserted rather than assumed: the fixer changes exactly what the checker finds, so
    text that has been through `fix_language` cannot still be reported for the word it just corrected."""
    sentence = f"{wrong} या काळात बलवान आहे आणि त्याचा प्रभाव जाणवेल."
    before = language_problems(sentence, "mr")
    assert any(wrong in problem and right in problem for problem in before), before

    fixed, changed = fix_language(sentence, "mr")
    assert right in fixed and wrong not in fixed
    assert changed == {f"{wrong}->{right}": 1}
    assert language_problems(fixed, "mr") == []


def test_a_wrong_word_with_no_single_answer_is_left_for_the_model():
    """The fixer must not LOOK as though it fixed something. A Hindi word in a Marathi sentence still fails,
    still earns its retry, and is still reported after the fixer has run."""
    sentence = "हे काम अत्यधिक कठिन आहे आणि जिम्मेदारी वाढते."
    fixed, changed = fix_language(sentence, "mr")
    assert changed == {} and fixed == sentence
    assert len(language_problems(fixed, "mr")) >= 3


def test_the_three_marathi_nakshatra_spellings_reach_every_consumer():
    """The advisor's instruction, 2026-09-30: do NOT change the shared engine table - Hindi keeps मूल,
    शतभिषा and पुनर्वसु - and add a Marathi-only map instead, the same pattern as _MR_SIGN, carried into the
    briefs, the PDF and the pages. Changing `app/engine/constants.py` in place would have respelled the Hindi
    product to fix the Marathi one, which is the mistake this arrangement exists to avoid.

    Asserted per language at every consumer rather than on the table, because a table nobody reads is the
    failure mode this project already had twice - a second copy in app/pdf/labels.py, and a third in
    app/web/i18n.py that was still saying धनु."""
    from app.engine.constants import nakshatra_info
    from app.pdf.labels import Labels
    from app.rashifal.i18n import nakshatra_name

    wanted = {"Punarvasu": ("पुनर्वसु", "पुनर्वसू"), "Mula": ("मूल", "मूळ"),
              "Shatabhisha": ("शतभिषा", "शततारका")}
    found = {}
    for index in range(27):
        info = nakshatra_info(index)
        if info["name"] in wanted:
            hindi, marathi = wanted[info["name"]]
            found[info["name"]] = True
            assert info["devanagari"] == hindi, "the shared engine table must NOT be respelled"
            assert nakshatra_name(info, "mr") == marathi and nakshatra_name(info, "hi") == hindi
            assert nakshatra_name(info, "en") == info["name"]
            assert Labels("mr").nakshatra(info) == marathi and Labels("hi").nakshatra(info) == hindi
    assert found.keys() == wanted.keys(), f"an engine nakshatra name changed: {found.keys()}"

    # the other 24 are spelled the same in both, so the map must not grow silently
    from app.rashifal.i18n import _MR_NAKSHATRA

    assert set(_MR_NAKSHATRA) == set(wanted)


def test_the_hindi_nakshatra_spelling_is_rejected_in_marathi_but_child_is_not():
    """शतभिषा is unambiguous - it is a nakshatra name and nothing else - so it is blocked and corrected.

    मूल is NOT, and that is the judgement in this pair. It is the ordinary Marathi word for a CHILD, so a
    fifth-house chapter is exactly where a paid book would write it correctly and be rejected for it. The
    name map already hands the model मूळ; a blocking rule would risk a regeneration on a true sentence to
    catch something that appears zero times in the stored Marathi."""
    assert any("शततारका" in problem for problem in language_problems("चंद्र शतभिषा नक्षत्रात आहे.", "mr"))
    assert fix_language("चंद्र शतभिषा नक्षत्रात आहे.", "mr")[0] == "चंद्र शततारका नक्षत्रात आहे."

    for child in ("तुमचे मूल आनंदी राहील.", "मूल आणि कुटुंब यांना वेळ द्या.", "मूळ स्वभाव शांत आहे."):
        assert language_problems(child, "mr") == [], child
        assert fix_language(child, "mr") == (child, {}), child


def test_both_misspellings_of_chandrabala_are_corrected_and_bala_alone_is_not():
    """The advisor's ruling, 2026-09-30: Marathi takes चंद्रबळ for चंद्रबल AND चांद्रबल. The second was
    reported rather than blocked when the rule was written, because चांद्र- is a genuine Sanskrit form and
    that was not a call to make from the data - the store holds the compound misspelled 17 times one way and
    3 the other, against 30 correct.

    The rule stays scoped to the COMPOUND. बल is ordinary Marathi (बलवान, मनोबल), and a rule that fired on it
    would reject correct sentences at a regeneration each."""
    for wrong in ("चांद्रबल", "चंद्रबल"):
        sentence = f"या काळात {wrong} कमी आहे आणि संयम ठेवावा लागेल."
        assert any("चंद्रबळ" in problem for problem in language_problems(sentence, "mr")), wrong
        fixed, changed = fix_language(sentence, "mr")
        assert "चंद्रबळ" in fixed and wrong not in fixed
        assert changed == {f"{wrong}->चंद्रबळ": 1}
        assert language_problems(fixed, "mr") == []
    # inflected, inside one word: the substitution is still a single token
    assert fix_language("चांद्रबलाने काम होईल.", "mr")[0] == "चंद्रबळाने काम होईल."
    # and बल on its own is untouched
    for keep in ("मनोबल वाढेल.", "तो बलवान आहे.", "हे बल चांगले आहे."):
        assert fix_language(keep, "mr") == (keep, {}), keep


def test_the_words_that_must_not_be_touched():
    """Where a blind replacement would do damage. Every one of these is why the substitution reuses the
    checker's own word boundaries instead of a plain str.replace."""
    keep = ("गुरुवार शुभ आहे.",                      # Thursday: Marathi spells it गुरुवार
            "मंगल कार्य या काळात शुभ आहे.",            # an auspicious occasion, not the planet
            "धनुष्य आणि बाण.",                        # a bow: धनु inside a longer word
            "गुरुत्वाकर्षण हा शब्द वेगळा आहे.")        # gravity
    for sentence in keep:
        fixed, changed = fix_language(sentence, "mr")
        assert fixed == sentence and changed == {}, sentence


# B4, the 2026-09-29 Marathi review. (wrong sentence, the same sentence written right, a word the message
# must offer). Both halves are the point: a rule that fires on the wrong form and ALSO on the right one does
# not improve the Marathi, it just spends a regeneration arriving back where it started.
B4_RULES = [
    ("चंद्र धनु राशीत आहे.", "चंद्र धनू राशीत आहे.", "धनू"),
    ("चंद्र पुनर्वसु नक्षत्रात आहे.", "चंद्र पुनर्वसू नक्षत्रात आहे.", "पुनर्वसू"),
    ("आज चंद्रबल कमी आहे.", "आज चंद्रबळ कमी आहे.", "चंद्रबळ"),
    ("आज चंद्रबलाने साथ दिली.", "आज चंद्रबळाने साथ दिली.", "चंद्रबळ"),
    ("शनीचा ढैया सुरू आहे.", "शनीची अडीचकी सुरू आहे.", "अडीचकी"),
    ("शनीची ढैय्या सुरू आहे.", "शनीची अडीचकी सुरू आहे.", "अडीचकी"),
    ("शनीची धैया सुरू आहे.", "शनीची अडीचकी सुरू आहे.", "अडीचकी"),
    ("साडेसातीचा उगवता टप्पा सुरू आहे.", "साडेसातीचा पहिला टप्पा सुरू आहे.", "मधला टप्पा"),
    ("साडेसातीच्या वाढत्या टप्प्यात संयम ठेवा.", "साडेसातीच्या मधल्या टप्प्यात संयम ठेवा.", "मधला टप्पा"),
    ("शनी बारावा स्थानात आहे.", "शनी बाराव्या स्थानात आहे.", "बाराव्या स्थानात"),
    ("सहावे स्थानातील ग्रह पाहा.", "सहाव्या स्थानातील ग्रह पाहा.", "सहाव्या स्थानातील"),
    ("बारावा घरात शनी आहे.", "बाराव्या घरात शनी आहे.", "बाराव्या घरात"),
    ("दहावे स्थानातून गुरू पाहतो.", "दहाव्या स्थानातून गुरू पाहतो.", "बाराव्या स्थानात"),
    ("ऊर्जा आतल्याकडे वळते.", "ऊर्जा अंतर्मुख होते.", "अंतर्मुख"),
    ("आठवड्याचा शेवट आतला जाईल.", "आठवड्याचा शेवट अंतर्मुख राहील.", "अंतर्मुख"),
    ("आंतरिक शांती मिळेल.", "अंतर्मुख शांती मिळेल.", "अंतर्मुख"),
    ("लग्नाची अचूक अंश महत्त्वाची आहे.", "लग्नाचे अचूक अंश महत्त्वाचे आहेत.", "लग्नाचे अचूक अंश"),
]


@pytest.mark.parametrize("wrong, right, offered", B4_RULES)
def test_each_b4_rule_fires_on_the_wrong_form(wrong, right, offered):
    found = language_problems(wrong, "mr")
    assert found, wrong
    assert any(offered in problem for problem in found), (wrong, found)


@pytest.mark.parametrize("wrong, right, offered", B4_RULES)
def test_no_b4_rule_fires_on_the_sentence_written_correctly(wrong, right, offered):
    assert language_problems(right, "mr") == [], (right, language_problems(right, "mr"))


def test_the_b4_rules_leave_ordinary_marathi_alone():
    """The sentences a blocking rule would damage, each one taken from or modelled on the 1014 Marathi
    strings in the rashifal store. The ordinal rule is the one with teeth: "सातवे स्थान" is correct
    nominative Marathi, appears in the store, and is what app/rashifal/i18n.py itself prints - so the rule
    requires a CASE ENDING on the noun, and the ordinals are enumerated rather than matched as "any word
    ending -वा/-वे", because "ठेवा घरात" is an imperative, not a twelfth house."""
    for sentence in ("सातवे स्थान बलवान आहे.",
                     "तुमच्या राशीपासून दहावे स्थान.",
                     "पैसे ठेवा घरात.",
                     "त्याचे मनोबल वाढेल आणि तो बलवान होईल.",
                     "थांबलेली कामे पुन्हा सुरू होतील.",
                     "अडीच तास लागतील.",
                     "आतल्या आत विचार सुरू आहेत.",
                     "तेव्हा घरातील वातावरण चांगले राहील.",
                     "साडेसातीच्या शेवटच्या टप्प्यात संयम ठेवा.",
                     "साडेसातीचा मधला टप्पा सुरू आहे."):
        assert language_problems(sentence, "mr") == [], (sentence, language_problems(sentence, "mr"))
        assert fix_language(sentence, "mr") == (sentence, {}), sentence


def test_the_pdf_and_the_prose_spell_marathi_the_same_way():
    """app/pdf/labels.py keeps its own copy of the Marathi spellings, because app/pdf must not import the
    rashifal package. The cost of that copy is that a spelling can be corrected in one place and not the
    other, and then the printed book disagrees with the free page about the same word. Nothing asserted
    this until B4 added धनू and पुनर्वसू to both."""
    from app.engine.constants import sign_info
    from app.pdf.labels import _MR_GRAHAS, _MR_NAKSHATRAS, _MR_SIGNS
    from app.rashifal.i18n import _MR_GRAHA, _MR_NAKSHATRA, _MR_SIGN

    assert _MR_GRAHAS == _MR_GRAHA
    assert _MR_NAKSHATRAS == _MR_NAKSHATRA
    assert {sign_info(index - 1)["key"]: name for index, name in _MR_SIGN.items()} == _MR_SIGNS


def test_a_marathi_reading_may_name_its_houses_with_any_of_the_three_words():
    """B6, and the decision is about the PROMPTS, not about this check. स्थान is what every Marathi prompt
    now asks for, in the rashifal, the book and the chat, because a reader who moves between the free page
    and the Rs 299 book should meet one word for a house. What `names_a_house` asks is a different and much
    weaker question - "is this reading built on placements at all" - and it must stay weak: a Marathi
    sentence that says भाव has named a house, and failing it for using the word we did not ask for would
    reject a true reading over a preference. (घर is not in that pattern and does not need to be: this
    function is the rashifal's, and the rashifal writes स्थान. The chat, where B6 allows घर, never calls it.)"""
    for sentence in ("सातव्या स्थानात शुक्र आहे.", "सप्तम स्थानात शुक्र आहे.", "सातव्या भावात शुक्र आहे."):
        assert names_a_house(sentence, "mr"), sentence
    assert not names_a_house("हा आठवडा शांत राहील.", "mr")


def test_hindi_keeps_its_own_spellings_and_english_is_untouched():
    """The same five words are CORRECT in Hindi. A fixer that ran everywhere would break the Hindi product
    to fix the Marathi one."""
    hindi = "गुरु और शनि का प्रभाव राहु के कारण बढ़ता है."
    assert fix_language(hindi, "hi") == (hindi, {})
    assert language_problems(hindi, "hi") == []
    english = "Jupiter and Saturn strengthen this period (Leo)."
    assert fix_language(english, "en") == (english, {})


def test_a_latin_gloss_is_dropped_from_a_devanagari_version():
    """"वृश्चिक (Scorpio)" - the model glosses a sign name for a reader it imagines needs it. The prompt has
    forbidden this since 2026-09-28 and a live Marathi report still produced one, in a bullet, on 2026-09-29.
    Only a parenthetical that is ENTIRELY Latin letters goes: a number or Devanagari in brackets is part of
    the sentence."""
    fixed, changed = fix_language("चंद्र रास - वृश्चिक (Scorpio) आहे.", "mr")
    assert fixed == "चंद्र रास - वृश्चिक आहे." and changed == {"(Scorpio)->dropped": 1}
    assert language_problems(fixed, "mr") == []

    fixed, changed = fix_language("सिंह (Leo) राशि में गुरु (Jupiter) है.", "hi")
    assert fixed == "सिंह राशि में गुरु है." and len(changed) == 2

    # A Devanagari parenthetical stays. (A fixable word INSIDE one is still corrected, which is right - the
    # gloss rule is about script, the spelling rule is about the word, and they are independent.)
    for keep in ("शुक्र (3 अंश) मजबूत आहे.", "गुरू (देव शिक्षक) बलवान आहे.", "हे 2026 (साल) आहे.",
                 "वेळ 10:30 (IST) आहे."):
        assert fix_language(keep, "mr")[0] == keep, keep


def test_devanagari_digits_are_normalised_and_reported():
    """B8. Every prompt in this codebase has asked for Latin numerals for longer than the Marathi review has
    existed - "Write numerals in Latin digits (2026, 7, 11:15) so dates and times stay unambiguous" - and the
    live chat still answered "वयाच्या २८ नंतर". The reason to want them is not typography: a date, a time and
    an age are what the reader types back into a search box, and half a page in ०-९ is worse than either
    alphabet alone. So the fixer settles it and the check is the net underneath."""
    for language, text in (("mr", "वयाच्या २८ नंतर बदल होतो."), ("hi", "उम्र २८ के बाद बदलाव होता है।")):
        assert any("Devanagari digits" in problem for problem in language_problems(text, language)), language
        fixed, changed = fix_language(text, language)
        assert "28" in fixed and not re.search(r"[०-९]", fixed), fixed
        assert changed == {"२->2": 1, "८->8": 1}
        assert language_problems(fixed, language) == [], language_problems(fixed, language)

    assert normalise_digits("२०२६ मध्ये ११:१५ वाजता") == "2026 मध्ये 11:15 वाजता"
    assert normalise_digits("") == "" and normalise_digits("2026 is already Latin") == "2026 is already Latin"
    assert normalise_digits("चंद्र") == "चंद्र"  # only digits are touched


def test_a_finding_keeps_the_word_it_found_so_the_evidence_points_at_the_right_sentence():
    """`language_problems` threw away WHAT it matched, and the consequence reached the stored record: the
    only thing `validator.language_issues` had to put in `Issue.found` was the first forty characters of the
    slot, and `book_report._sentence_around` then searched the slot for THAT - which matches at position zero,
    so a wording finding stored the chapter's opening sentence instead of the sentence the wrong word is in.
    On 2026-09-30 an आंतरिक finding was recorded against a sentence with no आंतरिक anywhere in it.

    That field is not decoration: `meta.checks.warnings` is what a reviewer reads, and the Marathi style
    sheet is sourced from these rows, so every wording sample in it could have been the wrong sentence."""
    from app.ai.language import language_findings
    from app.ai.validator import language_issues

    text = ("लग्नस्वामी चंद्र पाचव्या स्थानात वृश्चिक राशीत आहे, अनुराधा नक्षत्रात, चरण तीन. "
            "या काळात आंतरिक शांतता मिळेल आणि मन स्थिर राहील.")
    issues = language_issues(text, "mr")
    assert len(issues) == 1 and issues[0].found == "आंतरिक"
    assert issues[0].found in text and text.index(issues[0].found) > 40, \
        "the whole point is a word the old forty-character prefix could not have reached"

    # the two views cannot disagree: one implementation, two shapes
    assert language_problems(text, "mr") == [message for message, _ in language_findings(text, "mr")]

    # every `found` a check reports must be findable in the text it was found in, or the stored sentence is
    # a different sentence. The two whole-text properties report nothing and fall back, which is correct.
    samples = [("मोती (Pearl) घाला, आणि शनि बलवान आहे.", "mr"),
               ("यह हिंदी है और आहे मराठी शब्द है.", "hi"),
               ("वयाच्या २८ नंतर गुरु बलवान होईल.", "mr")]
    for sample, language in samples:
        for message, found in language_findings(sample, language):
            if found:
                assert found in sample, (language, message[:50], found)


def test_a_whole_text_property_reports_no_word_because_it_has_none():
    from app.ai.language import language_findings

    for message, found in language_findings("x", "mr"):
        assert found == "", message
    for message, found in language_findings("The English version.", "mr"):
        assert not found or found in "The English version."


def test_nothing_written_is_not_the_wrong_language():
    """An empty string used to score a Devanagari share of 0 and be reported as "not written in Devanagari",
    which a live Marathi book duly did for a span chapter's heading - and a span chapter is ALLOWED an empty
    theme, because the printed heading falls back to the engine's date range. Whether a slot may be empty is
    a structural question (app/ai/schema.py), and answering it here produced a warning nobody could act on."""
    for blank in ("", "   ", "\n"):
        assert language_problems(blank, "mr") == []
        assert language_problems(blank, "hi") == []
        assert language_problems(blank, "en") == []
    assert language_problems("अ", "mr") == []                      # one Devanagari letter is still Devanagari
    assert language_problems("x", "mr") == ["the `mr` version is not written in Devanagari"]


def test_the_delivered_marathi_report_that_started_this_would_now_be_clean():
    """The actual sentences from the report generated with the live model on 2026-09-29, which shipped with
    thirteen wording warnings and forty-one occurrences of गुरु."""
    shipped = ["सध्या गुरु महादशेत बुध अंतर्दशा सुरू आहे.",
               "हंस योग - गुरु कर्क राशीत, लग्नातच उच्च स्थानी आहे.",
               "चंद्र रास - वृश्चिक (Scorpio)",
               "1 एप्रिलला मंगळ आणि 13 एप्रिलला गुरु दोघेही मार्गी होतात."]
    fixed = [fix_language(text, "mr")[0] for text in shipped]
    assert all(language_problems(text, "mr") == [] for text in fixed), \
        [(text, language_problems(text, "mr")) for text in fixed if language_problems(text, "mr")]
    W = "ऀ-ॣ०-ॿ"
    assert not re.search(rf"(?<![{W}])गुरु(?![{W}])", " ".join(fixed))
    assert "(Scorpio)" not in " ".join(fixed)
