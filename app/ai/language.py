"""Is this text actually written in the language we asked for?

MOVED HERE FROM `app/rashifal/generate.py` ON 2026-09-29, and the move IS the fix. Every check below ran on
the free rashifal and on nothing else, so a Rs 299 Marathi book was the one product with no Marathi checking
at all - a paying customer got worse Marathi than a reader who paid nothing. The delivered book that started
this carried राहु, शनि and "पंचम भावात", all of which the rashifal would have rejected outright.

Nothing here is about astrology; it is about script and vocabulary. The astrology checks live in
`app/ai/validator.py` and run on both already.

What these checks CANNOT do is catch the next invented word - सुरटण्यासाठी and लांबमेय are in the table
because they were published, not because a rule predicted them. That gap is what the model choice, the
prompt and a native reviewer are for.
"""

import re

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER = re.compile(r"[A-Za-zऀ-ॿ]")
_WORD = "\u0900-\u0963\u0966-\u097f"  # Devanagari letters, signs and digits - not the danda (U+0964/5), which ends a sentence
_HINDI_ONLY = re.compile(rf"(?<![{_WORD}])(?:है|हैं|और|नहीं|यह|के लिए|बेहतर|करें|रहें|लेकिन)(?![{_WORD}])")
_MARATHI_ONLY = re.compile(rf"(?<![{_WORD}])(?:आहे|आहेत|आणि|नाही|साठी|करा|पण)(?![{_WORD}])")
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
_LATIN_ALLOWED = {"IST"}
_HOUSE_WORDS = {"en": re.compile(r"\bhouse\b", re.I), "hi": re.compile("भाव"), "mr": re.compile("स्थान|भाव")}

# Hindi words, Marathi misspellings and outright invented words that the LIVE Marathi readings carried, each
# with the Marathi that belongs there. Blocking rather than advisory: the prompt has asked for Marathi
# vocabulary since its first version and the readings still came out like this, so asking again more firmly is
# not the lever - and a Hindi word in a Marathi sentence is the one defect a Marathi reader spots instantly.
# The message names the replacement because it goes back to the model as retry feedback.
#
# Every entry was observed in published output; this is not a list of words that merely look Hindi. Anything
# with a legitimate Marathi use stays out, which is most of the work here: सरल is Hindi for "simple" but
# सरल योग is the name of a Vipreeta Raja yoga, so it is absent; मंगल is Hindi for Mars where Marathi writes
# मंगळ, but मंगल कार्य is ordinary Marathi for an auspicious occasion, so it is matched away from that.
#
# What this CANNOT do is catch the next invented word - सुरटण्यासाठी and लांबमेय are here because they were
# published, not because a rule predicted them. That gap is what the model choice and a native reader are for.
# Third element: the SINGLE correct token to substitute, or None when there is no mechanical fix. Only a
# whole wrong word with exactly one right spelling qualifies - "अत्यधिक" has two good Marathi answers and
# `तुला राश` overlaps the following word (substituting "तूळ" would eat "राश" and leave "तूळीत"), so both are
# left for the model. What `fix_spelling` changes is therefore exactly what this table finds, by construction.
_MR_WRONG_WORDS = tuple((re.compile(pattern), correct, fix) for pattern, correct, fix in (
    (rf"(?<![{_WORD}])सदे ?-?साती", "साडेसाती, one word", None),
    (rf"(?<![{_WORD}])धीरे", "हळूहळू", None),
    (rf"(?<![{_WORD}])धीरज(?![{_WORD}])", "धैर्य", None),
    (rf"(?<![{_WORD}])धीम[ािीे](?![{_WORD}])", "संथ", None),
    (rf"(?<![{_WORD}])मांग[तण][ेोाी]?(?![{_WORD}])", "मागणे (मागते / मागतो)", None),
    (rf"(?<![{_WORD}])जिम्मेदार(ी)?(?![{_WORD}])", "जबाबदार / जबाबदारी", None),
    (rf"(?<![{_WORD}])महसूस(?![{_WORD}])", "जाणवणे", None),
    (rf"(?<![{_WORD}])हो\s+जा", "होईल / होते", None),
    (rf"(?<![{_WORD}])खाना(?![{_WORD}])", "जेवण", None),
    (rf"(?<![{_WORD}])सैर(?![{_WORD}])", "फेरफटका", None),
    (rf"(?<![{_WORD}])छुप[ािीे](?![{_WORD}])", "गुप्त / गूढ", None),
    (rf"(?<![{_WORD}])सारावेळ(?![{_WORD}])", "संपूर्ण काळ", None),
    (rf"(?<![{_WORD}])प्रयास(?![{_WORD}])", "प्रयत्न", None),
    (rf"(?<![{_WORD}])अत्यधिक(?![{_WORD}])", "अत्यंत / अतिशय", None),
    (rf"(?<![{_WORD}])व्यक्तिगत(?![{_WORD}])", "वैयक्तिक", None),
    (rf"(?<![{_WORD}])जिज्ञासु(?![{_WORD}])", "जिज्ञासू", None),
    (rf"(?<![{_WORD}])कठिन(?![{_WORD}])", "कठीण", None),
    # the same word in both languages, but a different meaning - the Hindi sense says something we do not mean
    (rf"(?<![{_WORD}])शिक्षा(?![{_WORD}])", "शिक्षण (शिक्षा means punishment in Marathi)", None),
    (rf"(?<![{_WORD}])उजाड(?![{_WORD}])", "उत्साही / टवटवीत (उजाड means desolate)", None),
    # invented words, and Sanskritised forms no Marathi reader uses for a retrograde graha
    (rf"(?<![{_WORD}])(?:पिछलग|प्रतिलोमगामी)", "वक्री", None),
    (rf"(?<![{_WORD}])मुरठ[तण][ेोा]?(?![{_WORD}])", "परत येतो / परततो", None),
    (rf"(?<![{_WORD}])सुरटण", "सोडवणे (सुरटणे is not a word)", None),
    (rf"(?<![{_WORD}])लांबमेय(?![{_WORD}])", "दीर्घकालीन (लांबमेय is not a word)", None),
    (rf"(?<![{_WORD}])हळूवारीचा(?![{_WORD}])", "संयमी (हळूवारीचा is not a word)", None),
    (rf"(?<![{_WORD}])आजतर(?![{_WORD}])", "आज (आजतर is not a word)", None),
    # graha and sign spellings. The brief now carries these as `devanagari_mr`, so there is no excuse left:
    # until BRIEF_VERSION 2 the brief handed the model the Hindi spelling and the prompt told it to use it.
    (rf"(?<![{_WORD}])मंगल(?![{_WORD}])(?!\s*कार्य)", "मंगळ", "मंगळ"),
    (rf"(?<![{_WORD}])शनि(?![{_WORD}])", "शनी", "शनी"),
    (rf"(?<![{_WORD}])गुरु(?![{_WORD}])", "गुरू", "गुरू"),
    (rf"(?<![{_WORD}])राहु(?![{_WORD}])", "राहू", "राहू"),
    (rf"(?<![{_WORD}])केतु(?![{_WORD}])", "केतू", "केतू"),
    (r"तुला\s*राश", "तूळ", None),
    # ---- the 2026-09-29 Marathi review (B4). Every pattern here was COUNTED against the 1014 Marathi
    # strings the rashifal store holds before it was added, because a blocking rule that fires on good
    # Marathi costs a whole regeneration, and a rule that fires on nothing at all is worse than no rule.
    #
    # धनु is the engine's spelling and Marathi writes धनू - the same defect as मंगल / शनि / गुरु above, and
    # the same fix: app/rashifal/i18n.py now carries it, and this is the net underneath. The trailing
    # boundary is what keeps धनुष्य (a bow) safe, which `test_the_words_that_must_not_be_touched` has
    # asserted since before this line existed.
    (rf"(?<![{_WORD}])धनु(?![{_WORD}])", "धनू", "धनू"),
    # पुनर्वसु is Hindi's spelling of the nakshatra; Marathi lengthens it. NO trailing boundary, so the
    # inflected पुनर्वसुचा / पुनर्वसुत is corrected too - nothing else in Marathi begins with these letters.
    # The other 26 nakshatras are left exactly as the engine spells them.
    (rf"(?<![{_WORD}])पुनर्वसु", "पुनर्वसू", "पुनर्वसू"),
    # शतभिषा is Hindi's spelling; Marathi's panchang word is शततारका (advisor, 2026-09-30). Both boundaries,
    # unlike पुनर्वसु above, because the two words do not share a stem - substituting into an inflected
    # शतभिषेत would produce शततारकाेत, which is the half-correction the single-token rule exists to stop. An
    # inflected Hindi form therefore goes unreported rather than wrongly rewritten, which is the right way
    # round.
    (rf"(?<![{_WORD}])शतभिषा(?![{_WORD}])", "शततारका", "शततारका"),
    # मूल -> मूळ IS THE THIRD MARATHI NAKSHATRA SPELLING AND IT IS DELIBERATELY NOT HERE. The name tables
    # (app/rashifal/i18n._MR_NAKSHATRA) make our own output write मूळ, which is the whole of the advisor's
    # instruction. A BLOCKING rule is a different thing, and मूल is the ordinary Marathi word for a CHILD -
    # a fifth-house chapter about children is exactly where a paid book would write it correctly and be
    # rejected for it. Zero occurrences either way in the 800 stored Marathi strings or in the two paid
    # reports, so there is no evidence a rule would catch anything real, and a false positive here costs a
    # regeneration on a true sentence. The nakshatra reaches the model already spelled मूळ; if it starts
    # writing मूल anyway, that is a measurement worth having before a rule, not after.
    # चंद्रबळ, and ONLY in this compound - in BOTH its wrong spellings. The store holds चंद्रबल 17 times and
    # चांद्रबल 3, the same compound misspelled twice over, against चंद्रबळ 30 times right. The `चा?ं` is those
    # two: चांद्र- is a genuine Sanskrit form, which is why it was left out when this rule was written and
    # reported instead, and the advisor has since ruled that Marathi takes चंद्रबळ for both.
    # बल is a perfectly good Marathi word (बलवान, मनोबल) and even
    # sits inside unrelated ones (थांबलेली), so the rule is anchored to चंद्र- and substitutes the prefix,
    # which corrects चंद्रबलाने as well. 17 wrong against 32 right in the store.
    (rf"(?<![{_WORD}])चा?ंद्रबल", "चंद्रबळ", "चंद्रबळ"),
    # Saturn's two-and-a-half-year transit is अडीचकी in Marathi - which app/rashifal/i18n.py has printed
    # all along, while the AI prose wrote the Hindi word 45 times in five spellings. No mechanical fix:
    # ढैया is masculine and अडीचकी feminine, so "शनीचा ढैया" has to become "शनीची अडीचकी" and the word
    # BEFORE the match changes. A substitution that leaves शनीचा standing has not fixed the sentence.
    # अडीच on its own is the number two-and-a-half and is not matched.
    (rf"(?<![{_WORD}])(?:ढैय्या|ढैया|ढय्या|धैय्या|धैया)", "अडीचकी (शनीची अडीचकी)", None),
    # Sade sati has three phases and they have names: पहिला / मधला / शेवटचा टप्पा. उगवता and वाढता are
    # inventions - all six occurrences in the store read साडेसातीचा उगवता टप्पा or साडेसातीच्या वाढत्या
    # टप्प्यात, so there is no innocent use to protect. उतरणीचा and शिखर are deliberately NOT here:
    # app/ai/prompts.py itself offers उतार and शिखर as the glosses for the third and middle phases, and a
    # checker that rejects what our own prompt asks for is a checker that will be turned off.
    (rf"(?<![{_WORD}])(?:उगवता|उगवत्या|वाढता|वाढत्या)\s+टप्प",
     "पहिला टप्पा / मधला टप्पा / शेवटचा टप्पा (साडेसातीच्या टप्प्यांना हीच नावे आहेत)", None),
    # An ordinal before an INFLECTED स्थान / घर takes its oblique form. Two things keep this off good
    # Marathi. The ordinals are ENUMERATED rather than caught as "any word ending -वा/-वे", because
    # "ठेवा घरात" (keep it at home) is an ordinary imperative that ends in वा. And the noun must carry a
    # suffix: bare "सातवे स्थान" is correct nominative Marathi, stands four times in the store, and is
    # what app/rashifal/i18n.py prints itself ("तुमच्या राशीपासून दहावे स्थान"). Measured over those 1014
    # strings: 589 correct oblique forms, 4 correct nominative ones, and the 2 this fires on.
    # No mechanical fix: the right answer depends on which ordinal matched, and this table substitutes one
    # fixed token per entry. Two occurrences in 1014 strings does not buy a second substitution mechanism.
    (rf"(?<![{_WORD}])(?:पाच|सहा|सात|आठ|नव|दहा|अकरा|बारा)व[ाे]\s+(?:स्थान|घर)(?=[{_WORD}])",
     "the oblique ordinal before an inflected स्थान / घर: बाराव्या स्थानात, सहाव्या स्थानातील, बाराव्या घरात", None),
    # "turning inward" as a state of mind is अंतर्मुख. आतला / आतल्या is left alone otherwise: "आतल्या आत"
    # and "आतल्या मनाचा" are ordinary Marathi and are 15 of the 18 uses in the store, so only the two
    # shapes the review named are matched. आंतरिक is Hindi.
    (rf"(?<![{_WORD}])आतल्याकडे", "अंतर्मुख (मन अंतर्मुख होईल)", None),
    (rf"(?<![{_WORD}])आतला\s+जा", "अंतर्मुख राहील", None),
    (rf"(?<![{_WORD}])आंतरिक(?![{_WORD}])", "अंतर्मुख", None),
    # अंश is masculine in Marathi, so the possessive agreeing with it is लग्नाचे. NOT substitutable, though
    # it looks it: the gender runs on through the sentence, and "लग्नाची अचूक अंश महत्त्वाची आहे" needs
    # महत्त्वाचे as well. Replacing the phrase alone yields "लग्नाचे अचूक अंश महत्त्वाची आहे" - still wrong and
    # no longer caught, which is the one outcome a fixer must never produce. Three tokens can only be
    # replaced by guessing at the agreement of a fourth, which is why a fix here is one whole token or None.
    (r"लग्नाची\s+अचूक\s+अंश", "लग्नाचे अचूक अंश", None),
))
_MR_WRONG_LIMIT = 8  # enough for one retry to fix the lot without burying the rest of the feedback


def language_problems(text: str, language: str) -> list[str]:
    """Every way `text` fails to be the language asked for. Empty list = nothing wrong.

    Shared by the rashifal and the book so the two cannot drift: the rashifal had these for months while
    the paid book had none, and the only thing that made that survivable was nobody comparing them.

    `text` is the whole of one language version already joined - the caller decides what counts as its
    text, because a rashifal page and a book chapter hold their prose in completely different shapes.
    """
    return [message for message, _ in language_findings(text, language)]


def language_findings(text: str, language: str) -> list[tuple[str, str]]:
    """The same checks, as (message, the text that was matched).

    THE SECOND HALF IS EVIDENCE, and it went missing for a year. `validator.language_issues` had nothing
    better to put in an `Issue.found` than the first forty characters of the slot, and `book_report`'s
    `_sentence_around` then searched the slot for THAT - which matches at position zero, so every wording
    finding stored the opening sentence of the chapter rather than the sentence the wrong word is in. On
    2026-09-30 an आंतरिक finding was recorded against a sentence with no आंतरिक in it.

    That field is not decoration: `meta.checks.warnings` is what a reviewer reads, and the Marathi style
    sheet is sourced from these rows, so every wording sample in it was liable to be the wrong sentence.
    The checks themselves are unchanged - this only stops the finding throwing away what it found.

    A check that matches a whole-text property rather than a span (script share, Devanagari digits) has no
    single offending word, so it returns the empty string and the caller falls back as it always did.
    """
    findings: list[tuple[str, str]] = []

    def report(message: str, found: str = "") -> None:
        findings.append((message, found))

    # Nothing written is not the wrong language. An empty string used to score a Devanagari share of 0 and be
    # reported as "not written in Devanagari", which a live Marathi book on 2026-09-29 duly did for a span
    # chapter's heading - and a span chapter is ALLOWED an empty theme, because the printed heading falls back
    # to the engine's date range. Whether a slot may be empty is a structural question (app/ai/schema.py), not
    # a question about language, and answering it here produced a warning that could never be acted on.
    if not text.strip():
        return findings
    letters = len(_LETTER.findall(text)) or 1
    devanagari_share = len(_DEVANAGARI.findall(text)) / letters
    # No `found` on these two: they are properties of the whole text, not a word in it.
    if language == "en" and devanagari_share > 0.2:
        report("the English version is not in English")
    if language in ("mr", "hi") and devanagari_share < 0.6:
        report(f"the `{language}` version is not written in Devanagari")
    if language == "mr" and (hindi := _HINDI_ONLY.search(text)):
        report(f"the Marathi version contains Hindi ('{hindi.group(0)}'); write Marathi", hindi.group(0))
    if language == "mr":
        wrong = [(found.group(0).strip(), correct) for pattern, correct, _ in _MR_WRONG_WORDS
                 if (found := pattern.search(text))]
        for word, correct in wrong[:_MR_WRONG_LIMIT]:
            report(f"the Marathi version writes '{word}'; the Marathi for this is {correct}", word)
        if len(wrong) > _MR_WRONG_LIMIT:
            # The overflow line names several words, so it points at the first of them rather than at one
            # the reader would then have to pick out of a list.
            report(f"and {len(wrong) - _MR_WRONG_LIMIT} more non-Marathi words: "
                   f"{', '.join(word for word, _ in wrong[_MR_WRONG_LIMIT:])}", wrong[_MR_WRONG_LIMIT][0])
    if language == "hi" and (marathi := _MARATHI_ONLY.search(text)):
        report(f"the Hindi version contains Marathi ('{marathi.group(0)}'); write Hindi", marathi.group(0))
    if language in ("mr", "hi") and (digit := _RE_DEVANAGARI_DIGIT.search(text)):
        seen = "".join(sorted(set(_RE_DEVANAGARI_DIGIT.findall(text))))
        report(f"Devanagari digits in the {language} version ({seen}); write numerals in Latin "
               "digits (2026, 7, 11:15) - a reader types the date back into a search box", digit.group(0))
    if language in ("mr", "hi"):
        latin = sorted({word for word in _LATIN_WORD.findall(text) if word not in _LATIN_ALLOWED})
        if latin:
            # The FIRST one as it appears in the text, not the first alphabetically: `found` has to be
            # findable in the text for the stored sentence to be the right sentence.
            first = min(latin, key=text.find)
            report(f"Latin-script words in the Devanagari version: {latin[:6]}; write them in Devanagari or drop them",
                   first)
    return findings


# A parenthetical that is ENTIRELY Latin letters and spaces, in a Devanagari version: "वृश्चिक (Scorpio)",
# "सिंह (Leo)", "शनी (Shani)". The prompt has forbidden these since 2026-09-28 (app/ai/prompts.py) and a real
# Marathi report on 2026-09-29 still produced one, in a bullet - the model glosses a sign name for a reader it
# imagines needs it. Numbers, Devanagari and mixed content are left alone: this only drops a translation nobody
# asked for, never a parenthesis the sentence needs.
_LATIN_GLOSS = re.compile(r"\s*\(\s*[A-Za-z][A-Za-z ]*\)")

# Devanagari digits, in any language (B8, 2026-09-29). Every prompt in this codebase has asked for Latin
# numerals since before the Marathi review - "Write numerals in Latin digits (2026, 7, 11:15) so dates and
# times stay unambiguous" - and the chat still answered "वयाच्या २८ नंतर". Asking again is not the lever.
# The reason to want Latin digits is not typography: it is that a date, a time and an age are what a reader
# SEARCHES for and types back, and half a page in ०-९ and half in 0-9 is worse than either alone.
# Not gated on language, because ०-९ is wrong in a romanised reply and in English too, and a function that
# only cleans two of the five outputs is a function someone will call from the third and trust.
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_RE_DEVANAGARI_DIGIT = re.compile(r"[०-९]")


def normalise_digits(text: str) -> str:
    """०-९ -> 0-9. Safe in any language and on any string; digits are the only characters it touches."""
    return text.translate(_DEVANAGARI_DIGITS) if text else text


def fix_language(text: str, language: str) -> tuple[str, dict[str, int]]:
    """Correct what has exactly one right answer. Returns (text, {"was->now": count}).

    WHY A FIXER AND NOT A REGENERATION. A `wording` finding is deliberately not worth re-writing a whole part
    (book_report.NO_REGENERATION_KINDS), so B1 made these visible without making them stop: a real Marathi
    simple report generated on 2026-09-29 shipped `गुरु` FORTY-ONE times, every one recorded as a warning that
    nobody would ever act on, and the delivered book that prompted the Marathi review carried राहु and शनि
    for the same reason.
    Regenerating instead would be the worst of the options - the model writes the Hindi-influenced spelling
    because that is what it has most of, so a retry commonly returns it again, and a Rs 299 book would pay two
    or three times over to arrive at the same word.

    The substitution is exactly as narrow as the check: the same patterns, the same word boundaries, and only
    the entries whose correction is one whole token. `गुरुवार` is untouched (वार follows, so the boundary does
    not match), `मंगल कार्य` is untouched (its own lookahead), and text that has been through this function
    cannot carry the finding it just removed - which is asserted rather than assumed.

    It does NOT make the checks redundant: a Hindi sentence, an invented word, a Latin word in running prose
    or a wrong word with two possible answers still fails, still earns its retry and is still reported. This
    stops the handful of corrections that are mechanical from being shipped as prose nobody corrected.
    """
    if not text or language not in ("mr", "hi"):
        return text, {}
    changed: dict[str, int] = {}

    def replace(match, right):
        # keyed by the text that was actually there, not by the pattern: the pattern carries boundary and
        # lookahead noise, and the line this ends up on has to be readable ("गुरु->गुरू 41").
        key = f"{match.group(0).strip()}->{right or 'dropped'}"
        changed[key] = changed.get(key, 0) + 1
        return right

    if language == "mr":
        for pattern, _, fix in _MR_WRONG_WORDS:
            if fix:
                text = pattern.sub(lambda match, right=fix: replace(match, right), text)
    text = _RE_DEVANAGARI_DIGIT.sub(lambda match: replace(match, normalise_digits(match.group(0))), text)

    def drop_gloss(match):
        # `_LATIN_ALLOWED` is the checker's list of Latin words that may stand in Devanagari text, so a
        # parenthetical made only of those is not a gloss - "(IST)" beside a time is the sentence, and the
        # checker would not have complained about it either. The fixer must not be stricter than the check.
        if all(word in _LATIN_ALLOWED for word in _LATIN_WORD.findall(match.group(0))):
            return match.group(0)
        return replace(match, "")

    text = _LATIN_GLOSS.sub(drop_gloss, text)
    return text, changed


def names_a_house(text: str, language: str) -> bool:
    """A reading built on placements names at least one house. Rashifal-only today; the book's chapters
    are not all about houses, so it is exported rather than applied."""
    return language not in _HOUSE_WORDS or bool(_HOUSE_WORDS[language].search(text))
