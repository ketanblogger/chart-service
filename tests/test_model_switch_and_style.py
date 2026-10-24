"""The rashifal model switch, and the style rules the two external reviews asked for.

THE SWITCH. Rashifal moves to claude-haiku-5-5 in all three languages, and Marathi's Sonnet 5 override
goes. That reverses a deliberate earlier decision, so it rests on measurement: on twelve Marathi pages
Haiku 5.5 passed this checker 12/12 against Sonnet's 9/12, both blind judges preferred it overall (9/12
and 7/12), it scored higher on language and markedly higher on length, faithfulness was identical at
4.54, and it costs a fifth as much per token.

THE STYLE RULES are the mechanical half of what the reviewers objected to. The half that needs taste -
contradictions, generic remedies in prose - is in the prompt, because a checker that guesses at taste
rejects good writing and charges a rewrite for the privilege.
"""
from __future__ import annotations

import json
import pathlib

import pytest


# ---- the switch --------------------------------------------------------------------------------------

def test_every_language_writes_with_haiku_5_5():
    from app.rashifal.config import LANGUAGE_MODEL_DEFAULTS, get_rashifal_settings

    settings = get_rashifal_settings()
    assert settings.model == "claude-haiku-5-5", settings.model
    assert LANGUAGE_MODEL_DEFAULTS == {}, LANGUAGE_MODEL_DEFAULTS
    for lang in ("en", "hi", "mr"):
        assert settings.model_for((lang,)) == "claude-haiku-5-5", lang


def test_haiku_5_5_is_sent_thinking_and_effort():
    """THE TRAP THIS SWITCH WALKED INTO. The client decided on `startswith("claude-haiku")`, written when
    Haiku 4.5 - which has neither adaptive thinking nor an effort setting - was the only Haiku here.
    Haiku 5.5 has both. A family prefix would have stripped them from every rashifal call with no error
    and no log line: a weaker model than the one being paid for."""
    from app.ai.client import MODELS_WITHOUT_THINKING

    assert "claude-haiku-5-5" not in MODELS_WITHOUT_THINKING
    assert "claude-haiku-4-5" in MODELS_WITHOUT_THINKING


def test_the_effort_setting_is_not_silently_lowered_by_the_switch():
    """RASHIFAL_EFFORT was INERT for the whole of Haiku 4.5's time here, because the client omitted
    effort for that model. The switch makes it live, and its old default of "low" was never a choice
    anybody made - it was the default of a setting that did nothing. Medium is the model's own default."""
    from app.rashifal.config import get_rashifal_settings

    assert get_rashifal_settings().effort == "medium"


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5",
                                   "claude-fable-5-1", "claude-fable-5", "claude-sonnet-5",
                                   "claude-haiku-4-5", "claude-opus-5"])
def test_no_model_we_can_select_runs_unpriced(model):
    """An unpriced model records a cost of None, which the Usage page shows as "not recorded" - and a
    model nobody priced is a model whose spend nobody sees."""
    from app.ai.config import PRICES_PER_MTOK

    assert model in PRICES_PER_MTOK, model
    price_in, price_out = PRICES_PER_MTOK[model]
    assert price_in > 0 and price_out > 0


def test_a_long_prompt_is_priced_at_the_long_prompt_rate():
    """Haiku 5.5 is priced by prompt length, and the step is FIVE TIMES at 100,000 tokens, with the whole
    request repriced rather than only the tokens past the line. A flat table would under-report such a
    call five-fold, which on a cost page is worse than reporting nothing."""
    from app.ai.config import LONG_PROMPT_THRESHOLD, estimate_cost_usd

    short = estimate_cost_usd("claude-haiku-5-5", {"input_tokens": LONG_PROMPT_THRESHOLD - 1,
                                                   "output_tokens": 1000})
    long_ = estimate_cost_usd("claude-haiku-5-5", {"input_tokens": LONG_PROMPT_THRESHOLD + 1,
                                                   "output_tokens": 1000})
    assert long_ / short == pytest.approx(5.0, abs=0.01), long_ / short


def test_a_prompt_that_reaches_the_threshold_through_cache_still_counts_as_long():
    """A 150,000-token prompt served mostly from cache is still a long prompt and still priced as one."""
    from app.ai.config import LONG_PROMPT_THRESHOLD, prompt_tokens

    usage = {"input_tokens": 500, "cache_read_input_tokens": LONG_PROMPT_THRESHOLD}
    assert prompt_tokens(usage) > LONG_PROMPT_THRESHOLD


def test_a_model_with_no_tier_falls_back_to_its_flat_price():
    from app.ai.config import LONG_PROMPT_THRESHOLD, estimate_cost_usd

    short = estimate_cost_usd("claude-sonnet-5", {"input_tokens": 1000, "output_tokens": 100})
    scaled = estimate_cost_usd("claude-sonnet-5", {"input_tokens": LONG_PROMPT_THRESHOLD + 1000,
                                                   "output_tokens": 100})
    assert scaled > short      # more tokens cost more
    assert scaled / short < 110  # but not a tier jump: sonnet has one price


# ---- the style rules ---------------------------------------------------------------------------------

def test_an_internal_id_in_reader_text_is_refused():
    from app.rashifal.generate import style_problems

    page = {"headline": "A steady week", "overview": "The week turns on e3, which asks for patience.",
            "sections": {}, "key_dates": [], "tip": ""}
    assert any("internal id" in p for p in style_problems(page, "en"))


def test_an_event_id_in_its_own_field_is_not_refused():
    """THE DISTINCTION THAT MATTERS. event_id is how the SERVER finds an event's real date in the brief;
    the template renders the date, the event and the note, and never the id. A check that read it would
    reject every correct page - and my own review file printed it, which is how two external reviewers
    came to report a live-site bug that was never on the site."""
    from app.rashifal.generate import style_problems

    page = {"headline": "A steady week", "overview": "Patience pays this week.", "sections": {},
            "key_dates": [{"event_id": "e3", "note": "A good day to talk to colleagues."}], "tip": ""}
    assert not [p for p in style_problems(page, "en") if "internal id" in p]


def test_an_opening_that_restates_the_headline_is_refused():
    from app.rashifal.generate import style_problems

    page = {"headline": "Patience with money this week",
            "overview": "Patience with money this week is what the chart asks of you.",
            "sections": {}, "key_dates": [], "tip": ""}
    assert any("repeats" in p for p in style_problems(page, "en"))


def test_a_remedy_must_name_a_graha_the_reading_discusses():
    from app.rashifal.generate import style_problems

    unrelated = {"headline": "A week of paperwork",
                 "overview": "Guru in your 2nd house and Shani in the 12th ask for care with contracts.",
                 "sections": {}, "key_dates": [],
                 "tip": "Offer water to Surya every morning."}
    assert any("remedy must follow" in p for p in style_problems(unrelated, "en"))
    related = dict(unrelated, tip="Offer water to Guru's day, Thursday, with a little turmeric.")
    assert not [p for p in style_problems(related, "en") if "remedy must follow" in p]


def test_the_same_year_after_every_date_is_refused():
    from app.rashifal.generate import style_problems

    page = {"headline": "The week ahead", "overview": "x", "sections": {},
            "key_dates": [{"event_id": f"e{n}", "note": f"On 2{n} October 2026 something happens."}
                          for n in range(1, 7)], "tip": ""}
    assert any("appears" in p and "2026" in p for p in style_problems(page, "en"))


def test_counting_grahas_not_their_spellings():
    """English house style names each graha twice - "Sun (Surya)", "Mercury (Budha)" - and that is
    correct. Counting distinct STRINGS turned three grahas into six and fired this rule on 28 drafts
    this checker had already accepted: 27% of the sample, which would have roughly doubled the refusal
    rate and the bill."""
    from app.rashifal.generate import grahas_in

    assert grahas_in("Sun (Surya), Mercury (Budha) and Venus (Shukra) sit in Libra") == {
        "Sun", "Mercury", "Venus"}
    assert grahas_in("शनी आणि शनि") == {"Saturn"}


def test_listing_the_whole_chart_in_one_sentence_is_refused():
    from app.rashifal.generate import style_problems

    page = {"headline": "x",
            "overview": "Surya, Chandra, Mangal, Budha, Guru and Shukra all bear on the week.",
            "sections": {}, "key_dates": [], "tip": ""}
    assert any("names" in p and "grahas" in p for p in style_problems(page, "en"))


def test_a_normal_sentence_naming_three_grahas_is_left_alone():
    """Across 168 drafts this checker accepted, three grahas in a sentence is the NORM (111 of them) and
    four is common (21). A threshold below five would reject ordinary writing."""
    from app.rashifal.generate import style_problems

    page = {"headline": "x",
            "overview": "Mercury (Budha) in your 5th favours written work, while Mars (Mangal) and "
                        "Jupiter (Guru) in your 2nd counsel restraint with spending.",
            "sections": {}, "key_dates": [], "tip": ""}
    assert not [p for p in style_problems(page, "en") if "grahas" in p]


def test_the_rules_do_not_fire_on_most_accepted_drafts():
    """THE MEASUREMENT THAT DECIDES WHETHER A RULE IS SAFE. Every one of these rejects a draft and buys a
    rewrite, so a rule that fires on good writing is a bill. Measured against the 168 drafts four models
    produced in the trials, which this checker had already passed: the first version of these rules fired
    on 27% of them, and the fault was mine twice over. It is under 15% now, and the cases that remain are
    real - a remedy for a graha the reading never mentions, the year printed after all six dates."""
    from app.rashifal.generate import style_problems

    folder = pathlib.Path("var/model-trial-2")
    drafts = []
    for name in ("drafts-haiku55.json", "drafts-luna.json", "mr-drafts-sonnet5.json",
                 "mr-drafts-haiku55.json"):
        path = folder / name
        if path.exists():
            drafts += [r for r in json.loads(path.read_text(encoding="utf-8")) if r.get("page")]
    if len(drafts) < 50:
        pytest.skip(f"the trial drafts are scratch data and not in git; found {len(drafts)}")
    fired = sum(1 for r in drafts if style_problems(r["page"], r["language"]))
    assert fired / len(drafts) < 0.15, f"{fired}/{len(drafts)} = {fired / len(drafts):.0%}"


# ---- the Hindi language rules ------------------------------------------------------------------------

@pytest.mark.parametrize("text, why", [
    ("यह महीना चंद्रबळ के कारण अच्छा है।", "chandrabaL carries the Marathi letter"),
    ("मंगळ आपके भाव में है।", "mangaL is the Marathi spelling"),
    ("आपकी राशिफल अच्छा है।", "rashifal is masculine"),
    ("आपका छठे भाव में शनि है।", "the oblique ordinal takes aapke"),
    ("इस महीने मध्ये काम होगा।", "madhye is Marathi"),
])
def test_marathi_and_agreement_faults_in_hindi_are_refused(text, why):
    from app.ai import language

    assert language.language_findings(text, "hi"), why


def test_correct_hindi_passes_and_correct_marathi_is_not_judged_as_hindi():
    from app.ai import language

    assert not language.language_findings(
        "आपके राशिफल में चंद्र बल अच्छा है, आपके छठे भाव पर ध्यान दें।", "hi")
    assert not language.language_findings("तुमच्या राशीत चंद्रबळ चांगले आहे.", "mr")


def test_the_letter_rule_catches_spellings_nobody_listed():
    """A word list only ever catches the words somebody already noticed. ळ is not a letter of standard
    Hindi, so one rule covers चंद्रबळ, मंगळ, तूळ, वेळ and the next one too."""
    from app.ai import language

    for word in ("तूळ", "वेळ", "जवळ", "काळ"):
        assert language.language_findings(f"इस सप्ताह {word} पर ध्यान दें।", "hi"), word
