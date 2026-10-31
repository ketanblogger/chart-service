"""The last resort: delete what is still blocking, if the post survives it.

IT RUNS ONLY AFTER THE ORDINARY RULES HAVE FAILED, and it is cruder than any of them - it does not
rewrite a sentence, it removes it. That is the trade the proprietor chose: a post with one sentence
missing is worth more than a post nobody publishes. It is also why the guard rails matter more than
the surgery, and most of this file is about them.

Nothing is written. No model is asked and no sentence is invented to replace one.

Invented people only; `tests/` is published.
"""

import pytest

from app.blog import autofix, config, markdown, safety
from tests import blog_fixture as fixture

FILLER = ("Saturn moves slowly through this sign and the tradition reads it as a season of "
          "consolidation rather than of sudden change. ")
BAD_BODY = "This remedy is guaranteeing results."
BAD_SUMMARY = "This reading will cure your illness and set everything right for you at last."


def _recheck(post):
    blocking, warnings = safety.content_problems(post)
    return {"blocking": blocking, "warnings": warnings}


def _repair(post):
    return autofix.repair(post, _recheck)


def test_a_blocking_sentence_in_the_body_is_removed_and_the_post_publishes():
    post = fixture.post(slug="a-draft-with-one-bad-sentence",
                        body_md="## A heading\n\n" + FILLER * 35 + BAD_BODY + " " + FILLER * 5)
    assert safety.content_problems(post)[0], "the fixture must start blocked"
    fixed, fixes = _repair(post)
    assert not safety.content_problems(fixed)[0]
    assert BAD_BODY not in fixed["body_md"]
    assert [f for f in fixes if f["by"] == "last-resort"]


def test_only_the_offending_sentence_goes():
    """The neighbours are somebody's work and there is nothing wrong with them."""
    keeper = "Jupiter changes sign in June and the house it lands in is what the tradition reads."
    post = fixture.post(slug="a-draft-whose-neighbours-survive",
                        body_md="## A heading\n\n" + FILLER * 35 + keeper + " " + BAD_BODY + " " + FILLER * 5)
    fixed, _ = _repair(post)
    assert keeper in fixed["body_md"]
    assert BAD_BODY not in fixed["body_md"]


def test_a_blocking_summary_is_rebuilt_from_the_body_not_emptied():
    """A post needs a meta description, and the body's opening is prose that already passed."""
    post = fixture.post(slug="a-draft-with-a-bad-summary", summary=BAD_SUMMARY,
                        body_md="## A heading\n\n" + FILLER * 40)
    fixed, fixes = _repair(post)
    assert not safety.content_problems(fixed)[0]
    assert fixed["summary"] != BAD_SUMMARY
    assert config.MIN_SUMMARY_CHARS <= len(fixed["summary"]) <= config.MAX_SUMMARY_CHARS
    assert any("summary" in f["what"] for f in fixes)


def test_a_blocking_title_is_left_blocked():
    """A title is the one line that cannot be rebuilt from something else, and a post whose own title
    promises a cure should be read by a person."""
    post = fixture.post(slug="a-draft-with-a-bad-title", title="A guaranteed cure for your troubles",
                        body_md="## A heading\n\n" + FILLER * 40)
    fixed, fixes = _repair(post)
    assert safety.content_problems(fixed)[0], "it must stay blocked"
    assert not [f for f in fixes if f["by"] == "last-resort"]


def test_a_post_cut_below_the_word_floor_is_left_blocked():
    """A body cut to 280 words is a thin page, which is the thing the floor exists to prevent. Saving
    it that way would trade one defect for the one the site already has enough of."""
    post = fixture.post(slug="a-draft-too-short-to-cut",
                        body_md="## A heading\n\n" + FILLER * 2 + BAD_BODY)
    fixed, fixes = _repair(post)
    assert safety.content_problems(fixed)[0]
    assert not [f for f in fixes if f["by"] == "last-resort"]


def test_a_failed_attempt_changes_nothing_and_claims_nothing():
    """THE RULE THAT MAKES THE REST SAFE. If the deletion did not clear every check, the original
    post comes back untouched - not a half-cut one, and not a fix list saying work was done."""
    post = fixture.post(slug="a-draft-that-cannot-be-saved",
                        title="A guaranteed cure", summary=BAD_SUMMARY,
                        body_md="## A heading\n\n" + FILLER * 2 + BAD_BODY)
    fixed, fixes = _repair(post)
    assert fixed["body_md"] == post["body_md"] or BAD_BODY in fixed["body_md"]
    assert fixed["summary"] == post["summary"]
    assert not [f for f in fixes if f["by"] == "last-resort"]


def test_what_was_removed_is_recorded_with_its_own_words():
    """It is shown on /admin/blog beside every other repair. Deleting somebody's sentence without
    saying which one is the version of this feature nobody could audit."""
    post = fixture.post(slug="a-draft-whose-cut-is-logged",
                        body_md="## A heading\n\n" + FILLER * 35 + BAD_BODY + " " + FILLER * 5)
    _, fixes = _repair(post)
    cut = [f for f in fixes if f["by"] == "last-resort"]
    assert cut and BAD_BODY in cut[0]["before"]
    assert cut[0]["after"] == ""
    assert "removed" in cut[0]["what"]


def test_headings_and_list_items_are_never_half_deleted():
    """A heading is not prose, and half a list reads worse than the sentence that was in it."""
    body = ("## A heading that survives\n\n" + FILLER * 35 + BAD_BODY + "\n\n"
            "- a list item that survives\n- another one\n\n" + FILLER * 5)
    post = fixture.post(slug="a-draft-with-structure", body_md=body)
    fixed, _ = _repair(post)
    assert "## A heading that survives" in fixed["body_md"]
    assert "- a list item that survives" in fixed["body_md"]
    assert "- another one" in fixed["body_md"]


def test_a_danda_ends_a_sentence_in_the_devanagari_trees():
    """। is a full stop in Hindi and Marathi. Splitting only on "." would treat a whole paragraph as
    one sentence and delete all of it to remove one claim."""
    assert len(autofix._sentences("पहला वाक्य। दूसरा वाक्य। तीसरा वाक्य।")) == 3
    assert len(autofix._sentences("One. Two. Three.")) == 3


def test_it_does_not_run_on_a_post_the_ordinary_rules_already_saved():
    """It deletes rather than rewrites, so it must never touch a post that did not need it."""
    post = fixture.post(slug="a-draft-the-rules-can-fix",
                        body_md="## A heading\n\n100% accurate predictions. " + FILLER * 40)
    fixed, fixes = _repair(post)
    assert not safety.content_problems(fixed)[0]
    assert not [f for f in fixes if f["by"] == "last-resort"], "the ordinary rules should have sufficed"


def test_nothing_is_invented_to_replace_what_went():
    """The deterministic fallback removes; it never writes. The summary is the one thing rebuilt, and
    it is rebuilt out of the body's own sentences rather than composed."""
    post = fixture.post(slug="a-draft-with-a-bad-summary-2", summary=BAD_SUMMARY,
                        body_md="## A heading\n\n" + FILLER * 40)
    fixed, _ = _repair(post)
    assert fixed["summary"] in markdown.plain_text(fixed["body_md"])


def test_the_word_floor_is_measured_after_the_cut_not_before():
    post = fixture.post(slug="a-draft-just-above-the-floor",
                        body_md="## A heading\n\n" + FILLER * 20 + BAD_BODY)
    fixed, _ = _repair(post)
    if not safety.content_problems(fixed)[0]:
        assert markdown.word_count(fixed["body_md"]) >= config.MIN_BODY_WORDS
