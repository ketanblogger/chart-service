"""Repairing a post on the way in, and the gate that decides whether it may publish itself.

THE POLICY CHANGED HERE, and it is worth saying plainly: selling is now allowed on the blog. A post
may recommend this site's own paid products with an honest description and a real price. The
`hard_sell` category of the shared screen is skipped FOR THE BLOG ONLY - the rashifal, the paid
reports and the consultation still refuse it, because none of them is a place to sell from.

What did not change: fear is still refused, a guaranteed outcome is still refused, and a post still
may not claim to have seen the reader's chart.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.blog import autofix, config, publishing, safety, store

BODY = ("A paragraph about what the ayanamsa is and what it changes for somebody reading it. " * 14
        + "\n\n## Where it comes from\n\n"
        + "More text under the heading, long enough to read as a section of a real post. " * 18)


def post(**extra) -> dict:
    base = {"slug": "fix-test", "title": "A post about the ayanamsa and signs", "summary": "s" * 90,
            "body_md": BODY, "tool": "sidereal", "categories": ["basics"], "hero_image": None,
            "author": "RashiKundli", "language": "en", "translation_of": None,
            "key_points": [], "fact_check_warnings": []}
    return {**base, **extra}


# ---- what may now be said, and what still may not ------------------------------------------------

def test_a_post_may_recommend_our_own_paid_product():
    """The change. A real price and an honest description is a thing we are allowed to write."""
    text = ("The detailed Kundali report is Rs 299 and includes the dasha timeline and remedies. "
            "The AI astrologer answers follow-up questions about your own chart.")
    blocking, _ = safety.content_problems(post(body_md=BODY + text))
    assert not blocking, blocking


def test_fear_is_still_refused():
    for text in ("You must wear this stone or your marriage will fail.",
                 "You must perform a puja immediately to avoid the loss."):
        blocking, _ = safety.content_problems(post(body_md=BODY + text))
        assert blocking, f"not blocked: {text!r}"


def test_a_guaranteed_outcome_is_still_refused():
    text = "This remedy guarantees marriage within a year."
    blocking, _ = safety.content_problems(post(body_md=BODY + text))
    assert blocking, "a guarantee got through"


def test_the_shared_screen_itself_was_not_loosened():
    """The rashifal, the paid reports and the consultation go through the same function. Skipping a
    category for the blog must not mean skipping it for them."""
    from app.ai.safety import screen_text

    hits = [hit.category for hit in screen_text("Consult an astrologer and book a paid puja.")]
    assert "hard_sell" in hits, "the shared screen stopped refusing hard sell"


# ---- the repairs ----------------------------------------------------------------------------------

def test_an_outside_astrologer_becomes_our_own():
    """It sells for a competitor from a page we pay to host. Rewritten, not refused: the writer meant
    "get this looked at properly", and we have the thing that does that."""
    fixed, fixes = autofix.deterministic("Consult an astrologer for a full reading.")
    assert "consult an astrologer" not in fixed.lower()
    assert "/ai-astrologer" in fixed
    assert fixes and fixes[0]["before"] and fixes[0]["after"]


def test_a_claim_about_the_readers_chart_becomes_a_general_one():
    fixed, _ = autofix.deterministic("Your kundli shows a strong Saturn.")
    assert "your kundli shows" not in fixed.lower()
    assert "chart" in fixed


def test_a_repair_at_the_start_of_a_sentence_keeps_its_capital():
    """"Consult an astrologer for a reading" became "[ask our AI astrologer](...) for a reading" - a
    lower-case letter opening a sentence, in a repair meant to be invisible."""
    fixed, _ = autofix.deterministic("Consult an astrologer first.")
    assert fixed.startswith("[Ask"), fixed


def test_a_known_wrong_path_is_mapped_through_the_registry():
    fixed, fixes = autofix.deterministic("See the [chart tool](/kundali) and [matching](/guna-milan).")
    assert "/kundali)" not in fixed and "/guna-milan" not in fixed
    assert len(fixes) == 2


def test_an_image_reference_is_only_repaired_when_the_image_exists():
    """Inventing a path to a picture nobody uploaded would turn a clear refusal into a broken image
    on a live page."""
    fixed, fixes = autofix.deterministic("![a chart](nosuchimage)")
    assert fixed == "![a chart](nosuchimage)"
    assert not fixes


def test_every_repair_is_recorded_with_its_before_and_after():
    _fixed, fixes = autofix.deterministic(
        "Consult an astrologer. Your kundli shows Saturn. See [this](/kundali).")
    assert len(fixes) == 3
    for fix in fixes:
        assert fix["what"] and fix["before"] and fix["after"]
        assert fix["by"] == "rules"


# ---- the model round ------------------------------------------------------------------------------

class _Model:
    def __init__(self, pairs):
        self.pairs, self.calls = pairs, 0

    def generate_json(self, *, system, user, schema):
        self.calls += 1

        class Result:
            data = {"replacements": self.pairs}
        return Result()


def test_the_model_may_only_replace_text_that_is_really_there():
    """A `find` the model invented means it is quoting something it did not read. Refused rather than
    guessed around."""
    model = _Model([{"find": "NOT PRESENT", "replace": "x", "why": "invented"}])
    body, fixes = autofix.ai_pass("A clean sentence.", ["something"], client=model)
    assert body == "A clean sentence."
    assert not fixes


def test_the_model_may_not_change_a_phrase_that_appears_twice():
    """One match or none: a phrase appearing twice would change a sentence nobody looked at."""
    model = _Model([{"find": "the same", "replace": "different", "why": "x"}])
    body, fixes = autofix.ai_pass("the same and the same", ["something"], client=model)
    assert body == "the same and the same" and not fixes


def test_the_model_is_not_called_when_nothing_is_blocking():
    model = _Model([])
    body, fixes = autofix.ai_pass("Fine.", [], client=model)
    assert model.calls == 0 and body == "Fine." and not fixes


def test_a_model_that_fails_leaves_the_post_exactly_as_it_was():
    """Auto-fix is a convenience, and a convenience that breaks a post is worse than none."""
    class Broken:
        def generate_json(self, **kwargs):
            raise RuntimeError("no")

    body, fixes = autofix.ai_pass("Original text.", ["a problem"], client=Broken())
    assert body == "Original text." and not fixes


def test_the_model_rounds_are_bounded():
    model = _Model([{"find": "A paragraph", "replace": "A para", "why": "x"}])
    publishing.repair_and_check(post(), client=model)
    assert model.calls <= autofix.MAX_AI_ROUNDS, model.calls


# ---- the gate ---------------------------------------------------------------------------------------

@pytest.fixture
def autopublish_on(monkeypatch):
    monkeypatch.setattr(config, "autopublish", lambda: True)


def test_nothing_publishes_itself_while_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(config, "autopublish", lambda: False)
    allowed, why = publishing.may_autopublish(post(), {"blocking": []})
    assert not allowed and "BLOG_AUTOPUBLISH" in why


def test_a_fact_check_warning_no_longer_holds_a_post_back(autopublish_on):
    """IT DID, FOR ABOUT AN HOUR, and the proprietor reversed it: cost matters more than perfection,
    and a post waiting for somebody's evening is a post not published.

    The claim is still auditable - recorded on the row, shown on /admin/blog, and logged at the
    moment the post goes public. It is auditable AFTER rather than before, which is the trade."""
    allowed, _why = publishing.may_autopublish(
        post(fact_check_warnings=["the 1947 figure is unverified"]), {"blocking": []})
    assert allowed


def test_an_unverified_claim_is_logged_when_the_post_goes_public(caplog):
    """Warnings no longer stop a post, so the log is where an unverified claim becomes findable."""
    import logging

    draft = post(slug="warned-publish", title="A post with an unverified claim in it",
                 summary="A post whose writer could not verify one of its claims, with a summary of "
                         "its own so it is not a duplicate of another post.",
                 fact_check_warnings=["the 1947 figure is unverified"])
    store.save(draft, publishing.recheck(draft))
    with caplog.at_level(logging.WARNING):
        try:
            publishing.go_live("warned-publish", actor="test")
        except store.Blocked as exc:
            pytest.skip(f"the fixture post is blocked for another reason: {exc}")
    assert any("unverified" in record.message for record in caplog.records), \
        "a post went public with an unverified claim and nothing said so"


def test_a_blocking_check_stops_it(autopublish_on):
    allowed, why = publishing.may_autopublish(post(), {"blocking": ["something"]})
    assert not allowed and "check(s)" in why


def test_a_clean_post_may_go(autopublish_on):
    allowed, why = publishing.may_autopublish(post(), {"blocking": []})
    assert allowed, why


def test_the_day_has_a_limit_and_the_rest_queue(autopublish_on, monkeypatch):
    """A writer that produces thirty good posts on a Tuesday is not a reason to publish thirty on a
    Tuesday."""
    monkeypatch.setattr(store, "published_count_today", lambda: publishing.AUTOPUBLISH_PER_DAY)
    allowed, why = publishing.may_autopublish(post(), {"blocking": []})
    assert not allowed
    assert "daily limit" in why and "queued" in why


def test_the_queue_is_oldest_first():
    """A post that has waited two days should not be overtaken by one that arrived this morning."""
    import inspect

    source = inspect.getsource(publishing.publish_queue)
    assert "created_at" in source and "sort" in source


# ---- images ---------------------------------------------------------------------------------------

def test_an_image_we_are_hosting_is_a_valid_link():
    """/blog/media/<id> is served by the blog's own route and is not in the URL registry, so the
    registry check refused every post that carried a picture."""
    from app.blog import images

    data = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    try:
        saved = images.save(data, sent_as="probe.png")
    except Exception:  # noqa: BLE001 - a sniffer that refuses the stub is not what is under test
        pytest.skip("the image store would not accept a stub file")
    body = BODY + f"\n\n![a chart](/blog/media/{saved['id']})\n"
    blocking, _ = safety.link_problems(post(body_md=body))
    assert not blocking, blocking


def test_an_image_nobody_uploaded_is_refused_and_says_so():
    blocking, _ = safety.link_problems(post(body_md=BODY + "\n\n![x](/blog/media/nosuchid)\n"))
    assert blocking and "media store" in blocking[0]


# ---- the morning digest ----------------------------------------------------------------------------

def test_the_digest_names_yesterdays_posts_with_their_links():
    """With autopublish on, a post can reach the public without anybody reading it. The morning read
    is the first human look at it, and a list with no links is a list nobody checks."""
    import datetime as dt

    from app.admin import daily

    published = store.published(None)
    if not published:
        pytest.skip("no published posts in this working copy")
    day = published[0]["published_on"]
    line = daily._blog_line(dt.date.fromisoformat(day))
    assert line.startswith("Blog posts")
    assert published[0]["path"] in line
    assert published[0]["title"] in line


def test_the_digest_says_nothing_on_a_day_with_no_posts():
    """A line of zeros every morning is noise, and noise is what stops a digest being read."""
    import datetime as dt

    from app.admin import daily

    assert daily._blog_line(dt.date(2019, 1, 1)) == ""


# ---- the one-off catch-up over existing drafts ------------------------------------------------------

def _seed_draft(slug: str, body: str) -> dict:
    """A draft with a summary OF ITS OWN.

    Every post here shared one summary at first, and a duplicate summary is a blocking check - two
    pages on this site may not carry the same meta description. So each seeded draft was refused for
    a reason that had nothing to do with what the test was about, and the one test that looked at the
    difference between publishable and blocked was the only one that noticed.
    """
    draft = post(slug=slug, title=f"A draft called {slug} about the ayanamsa",
                 summary=f"A draft seeded as {slug}, with a summary of its own so that it is not a "
                         f"duplicate of any other post on this site. " + "x" * 10,
                 body_md=body)
    store.save(draft, publishing.recheck(draft))
    return store.get(slug)


def _run_refix(*args) -> str:
    import subprocess
    import sys

    done = subprocess.run([sys.executable, "scripts/blog_refix.py", "--no-ai", *args],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-500:]
    return done.stdout


def test_the_catch_up_reports_without_writing_anything():
    """Drafts already in the database arrived before auto-fix existed. The dry run has to say what it
    WOULD do and change nothing while saying it."""
    needs_work = BODY + "\n\nConsult an astrologer for a full reading of this placement.\n"
    _seed_draft("refix-dry", needs_work)

    output = _run_refix("--slug", "refix-dry")
    assert "DRY RUN" in output
    assert "an outside astrologer became our own" in output
    assert "Nothing was written" in output
    assert "Consult an astrologer" in store.get("refix-dry")["body_md"], "the dry run wrote to the post"


def test_the_catch_up_applies_the_repairs_and_records_them():
    needs_work = BODY + "\n\nConsult an astrologer for a full reading of this placement.\n"
    _seed_draft("refix-apply", needs_work)

    _run_refix("--slug", "refix-apply", "--apply")
    after = store.get("refix-apply")
    assert "Consult an astrologer" not in after["body_md"]
    assert after["fixes"], "the repairs were applied but not recorded"


def test_the_catch_up_never_publishes_anything():
    """NOT WITH --apply, and not when a draft comes out perfectly clean. Publishing follows the same
    gate as a new post: the flag, the checks, the warnings and the two-a-day cap."""
    _seed_draft("refix-clean", BODY)
    before = store.published_count_today()

    output = _run_refix("--slug", "refix-clean", "--apply")
    assert store.get("refix-clean")["status"] == "draft"
    assert store.published_count_today() == before
    assert "NOTHING WAS PUBLISHED" in output


def test_the_catch_up_separates_publishable_from_still_blocked():
    _seed_draft("refix-ok", BODY)
    # STILL BLOCKED means the last resort could not save it either. A guarantee in a body sentence is
    # now deleted and the post publishes, so a draft that stays stuck is one whose body is too short
    # to lose a sentence - below the word floor, a cut post is a thin page rather than a saved one.
    _seed_draft("refix-stuck",
                "## A heading\n\nThis remedy guarantees a marriage within the year.\n")

    output = _run_refix()
    ok_line = output.split("refix-ok", 1)[1].split("refix-", 1)[0]
    stuck_line = output.split("refix-stuck", 1)[1].split("\n\n", 1)[0]
    assert "NOW PUBLISHABLE" in ok_line
    assert "STILL BLOCKED" in stuck_line


def test_a_draft_with_a_fact_check_warning_is_reported_as_waiting_not_publishable():
    draft = post(slug="refix-warned", title="A draft with a warning about the ayanamsa",
                 summary="A draft that carries a fact-check warning from its writer, with a summary "
                         "of its own so it is not a duplicate of another post.",
                 fact_check_warnings=["the 1947 figure is unverified"])
    store.save(draft, publishing.recheck(draft))

    output = _run_refix("--slug", "refix-warned")
    section = output.split("refix-warned", 1)[1]
    assert "waits for a person" in section
    assert "NOW PUBLISHABLE" not in section


# ---- somebody else's till --------------------------------------------------------------------------
#
# Skipping `hard_sell` for the blog removed the guard against THIRD-PARTY commerce along with the one
# against our own, because the category covered both. This is the narrower rule that replaced it: our
# products may be sold, a stranger's may not, and the tradition's free remedies are untouched.

@pytest.mark.parametrize("text", [
    "The detailed Kundali report is Rs 299 and covers the dasha timeline.",
    "Ask our AI astrologer about this placement.",
    "The matching report is Rs 119 and scores all 36 gunas.",
])
def test_our_own_paid_products_are_allowed(text):
    blocking, _ = safety.content_problems(post(body_md=BODY + text))
    assert not blocking, blocking


@pytest.mark.parametrize("text", [
    "Visit a Shani temple on Saturday and offer oil.",
    "Give food to the needy on Saturdays.",
    "Chant the Shani mantra 108 times.",
    "Many people fast on Saturdays during this period.",
    "Light a lamp before sunset at home.",
])
def test_free_traditional_practice_is_allowed(text):
    """The tradition is full of remedies that cost nothing. Refusing to mention them would be this
    site pretending the only answer is a purchase, which is the opposite of the point."""
    blocking, _ = safety.content_problems(post(body_md=BODY + text))
    assert not blocking, blocking


@pytest.mark.parametrize("text", [
    "You can book a puja with any temple priest.",
    "Order a homa through the temple office.",
    "Buy a yantra from a reputed seller.",
    "Purchase a rudraksha online for this dosha.",
    "Hire an astrologer to read the chart in detail.",
    "A paid consultation will clarify the dasha.",
])
def test_third_party_paid_services_are_recorded(text):
    """A blog post we host and pay for is not a shopfront for a trade we have no sight of - but this
    is a WARNING now, not a refusal, and the repair rule rewrites the common phrasings before anybody
    sees it. What reaches here is a phrasing the rule did not match: written down, and published."""
    blocking, warnings = safety.content_problems(post(body_md=BODY + text))
    assert not blocking, f"a phrasing should not block a post any more: {blocking}"
    assert warnings, f"not even recorded: {text!r}"


@pytest.mark.parametrize("before,expect", [
    ("You can book a puja with any temple priest.", "temple"),
    ("Buy a yantra from a reputed seller.", "temple"),
    ("Hire an astrologer to read the chart.", "/ai-astrologer"),
    ("A paid consultation will clarify this.", "/ai-astrologer"),
])
def test_third_party_selling_is_rewritten_rather_than_only_refused(before, expect):
    """Most of the time the writer meant "do something about this", and the tradition has answers
    that cost nothing. A paid READING becomes ours, because that reader wanted a chart looked at."""
    after, fixes = autofix.deterministic(before)
    assert expect in after, after
    assert fixes and fixes[0]["before"] and fixes[0]["after"]


def test_the_rewrite_takes_the_whole_phrase_with_it():
    """Replacing only the verb leaves "visit a temple with any temple priest" on the page."""
    after, _ = autofix.deterministic("You can book a puja with any temple priest.")
    assert "priest" not in after, after


def test_a_post_full_of_third_party_selling_passes_after_the_repairs():
    """The round trip: blocked on arrival, repaired, and then publishable."""
    body = (BODY + "\n\nYou can book a puja with any temple priest. Buy a yantra from a reputed "
            "seller. Hire an astrologer if you want more detail.\n" + "Filler sentence. " * 30)
    fixed, report, fixes = publishing.repair_and_check(post(body_md=body))
    assert len(fixes) >= 3
    assert not report["blocking"], report["blocking"]
    assert "priest" not in fixed["body_md"]


# ---- the policy, stated as tests ------------------------------------------------------------------
#
# "Block only what breaks the site or the law." These five are the whole blocking list; everything
# else is repaired where a rule exists and published with a warning where one does not.

@pytest.mark.parametrize("text,why", [
    ("This remedy guarantees a marriage within the year.", "a guarantee"),
    # THE LINE MOVED, ON PURPOSE. These two passed with a warning for about an hour: the rule asked
    # for second person, and neither has one. They are still predictions of harm, and the
    # proprietor moved the line to cover harm predicted for a family or for "people with this
    # placement" as well as for the reader.
    ("This period can bring a serious illness to the family.", "impersonal harm"),
    ("Saturn here has been linked to an untimely end.", "harm attributed to a placement"),
    ("People with this placement often face a serious illness.", "harm predicted for a group"),
    ("You must wear this stone or your marriage will fail.", "fear selling"),
    ("You must perform a puja immediately to avoid the loss.", "compulsion"),
])
def test_these_five_still_stop_a_post(text, why):
    blocking, _ = safety.content_problems(post(body_md=BODY + text))
    assert blocking, f"{why} got through"


@pytest.mark.parametrize("text,why", [
    ("A divorce is common under this transit.", "catastrophe"),
    ("Wear a blue sapphire for this placement.", "gemstone talk"),
    ("Your chart reveals a strong Saturn.", "a phrasing the repair rule did not match"),
    ("Invest in these stocks during this dasha.", "financial"),
])
def test_everything_else_is_recorded_and_published(text, why):
    """The cost argument: a post held back for a phrasing nobody would notice costs a person's
    evening, and the posts this blog exists to publish are worth more than the phrasings are worth
    avoiding."""
    blocking, warnings = safety.content_problems(post(body_md=BODY + text))
    assert not blocking, f"{why} should not stop a post: {blocking}"
    assert warnings, f"{why} was not even recorded"


def test_a_link_that_points_at_nothing_never_blocks_a_post():
    """It is repaired instead - the link is dropped and the words survive."""
    body = BODY + "\n\nSee the [matching tool](/no-such-page) for more.\n"
    report = safety.check(post(body_md=body))
    assert not report["blocking"], report["blocking"]

    fixed, fixes = autofix.deterministic(body)
    assert "/no-such-page" not in fixed
    assert "matching tool" in fixed, "the writer's words were deleted along with the link"
    assert fixes


def test_a_missing_image_is_dropped_rather_than_refused():
    body = BODY + "\n\n![a chart](/blog/media/nothere)\n"
    assert not safety.check(post(body_md=body))["blocking"]
    fixed, _ = autofix.deterministic(body)
    assert "nothere" not in fixed


def test_the_model_is_off_unless_somebody_turns_it_on():
    """The deterministic rules do the repairs. The model costs money per post for a result nobody
    asked to be perfect."""
    assert config.ai_fix() is False

    class Model:
        calls = 0

        def generate_json(self, **kwargs):
            Model.calls += 1
            raise AssertionError("the model was called with the flag off")

    publishing.repair_and_check(post(body_md=BODY + "A divorce is common."), client=Model())
    assert Model.calls == 0


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_post_carries_the_disclaimer_in_its_own_language(lang):
    """Appended at render time rather than stored: it says what this whole section of the site is, so
    no single post gets to leave it out - and with autopublish on, a post can reach a reader before
    anybody here has."""
    from app.blog import pages as blog_pages

    words = blog_pages.copy_for(lang)
    assert words["disclaimer"].strip()
    assert "not a personal reading" in words["disclaimer"] or lang != "en"
    template = Path("app/web/templates/blog_post.html").read_text(encoding="utf-8")
    assert "words.disclaimer" in template


def test_there_is_no_rejected_status_and_nothing_regenerates():
    """A post is a draft or it is published. Nothing here asks a model to write one again."""
    assert set(dir(store)) >= {"DRAFT", "PUBLISHED"}
    assert not hasattr(store, "REJECTED")
    for module in (safety, publishing, autofix):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "regenerate" not in source.lower(), module.__name__


# ---- the queue actually moves ----------------------------------------------------------------------

def test_nothing_published_the_queue_until_a_caller_existed():
    """THE GAP THIS CLOSES. Autopublish fired only when a post ARRIVED through the API. A draft
    already in the database - predating the checks, or unblocked by the catch-up - had nothing to
    pick it up, ever. The queue and the two-a-day cap were built and nothing called them, which was
    discovered by turning the flag on in production and watching eleven ready drafts not move."""
    import subprocess
    import sys
    from pathlib import Path

    unit = Path("deploy/systemd/blog-release.timer").read_text(encoding="utf-8")
    assert "OnCalendar" in unit and "Asia/Kolkata" in unit
    assert "Persistent=true" in unit, "a missed day would push the whole queue back a day, silently"

    service = Path("deploy/systemd/blog-release.service").read_text(encoding="utf-8")
    assert "blog_release.py --apply" in service

    done = subprocess.run([sys.executable, "scripts/blog_release.py"],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-400:]


def test_the_release_respects_the_cap_and_is_safe_to_run_twice(monkeypatch):
    """Counted from what is already live TODAY, so a manual publish earlier reduces the automatic
    allowance rather than adding to it - and a second run in the same day publishes nothing."""
    monkeypatch.setattr(config, "autopublish", lambda: True)
    body = ("A paragraph about guna milan and what the eight kootas measure between two charts. " * 30)
    for n in (1, 2, 3):
        draft = post(slug=f"rel-{n}", title=f"A queued post number {n} about guna milan",
                     summary=f"A queued draft number {n} with a summary of its own so that it is "
                             f"not a duplicate of any other post on this site.",
                     body_md=body)
        store.save(draft, publishing.recheck(draft))

    first = publishing.release_due(actor="test")
    assert len(first) == publishing.AUTOPUBLISH_PER_DAY, [p["slug"] for p in first]
    assert publishing.release_due(actor="test") == [], "the cap did not hold on a second run"
    assert any(p["slug"] == "rel-3" for p in publishing.publish_queue()), "the third was lost"


# ---- the legal rules, made precise ------------------------------------------------------------------
#
# ELEVEN DRAFTS WERE BLOCKED ON FALSE POSITIVES. The rules matched words, not claims: "there is no
# guarantee" is the site being honest, and "the eighth house rules longevity and death" is what an
# astrology blog is FOR. Both were refused. A rule that fires on good writing costs a rewrite every
# time somebody writes well.

@pytest.mark.parametrize("text,why", [
    ("This is a traditional reading and there is no guarantee of any outcome.", "a negated guarantee"),
    ("A high score does not guarantee a happy marriage.", "a negated guarantee"),
    ("We cannot guarantee a result from any remedy.", "a negated guarantee"),
    ("The eighth house rules longevity and death in classical texts.", "information about a house"),
    ("A muhurat for surgery is chosen away from the dagdha yogas.", "a muhurat, not a prediction"),
    ("You will find the dates in the table below.", "a future with no harm in it"),
])
def test_honest_and_informational_writing_is_not_refused(text, why):
    blocking, _ = safety.content_problems(post(body_md=BODY + text))
    assert not blocking, f"{why} was refused: {blocking}"


@pytest.mark.parametrize("text,why", [
    ("This remedy guarantees a marriage within the year.", "a positive guarantee"),
    ("The result is guaranteed for every chart.", "a positive guarantee"),
    ("You will suffer a serious illness after March.", "harm predicted at the reader"),
    ("You may suffer an accident during this transit.", "harm predicted at the reader"),
    ("Your father may face a heart attack this year.", "harm predicted at the reader's family"),
    ("You are at risk of surgery during this dasha.", "harm predicted at the reader"),
])
def test_a_real_promise_or_a_prediction_of_harm_still_stops_a_post(text, why):
    """Two of these - "you may suffer an accident" and "your father may face a heart attack" - were
    only WARNINGS under the old word-matching rule. Making it precise made it stricter where it
    matters, not only looser where it did not."""
    blocking, _ = safety.content_problems(post(body_md=BODY + text))
    assert blocking, f"{why} got through"


def test_the_subject_is_still_recorded_even_when_it_is_allowed():
    """Nothing stops being visible. The topic is a warning on an informational mention, so a reader
    of /admin/blog still sees that a post talks about death - they are simply not stopped by it."""
    _blocking, warnings = safety.content_problems(
        post(body_md=BODY + "The eighth house rules longevity and death in classical texts."))
    assert any("death" in warning for warning in warnings), warnings
