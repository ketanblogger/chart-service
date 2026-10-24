"""GET /api/blog/options: what a writing client is told before it writes.

THE POINT OF THIS FILE IS DRIFT. The forbidden-phrase list is written by hand, because turning the
checker's regexes into readable phrases automatically produces either noise or a lie and a writer can
act on neither. A hand-written list is only worth having while it is TRUE, and a list that quietly
stops matching the rules is worse than no list at all - a client trusts it, writes to it, and gets
blocked anyway.

So: every phrase advertised is run through the real checker here, and every blocking rule has to have
an entry. The two cannot drift apart without this file failing.

Invented people only; `tests/` is published.
"""

import pytest
from fastapi.testclient import TestClient

from app.blog import api, config, safety
from app.main import app
from tests import blog_fixture as fixture

client = TestClient(app)
TOKEN = "an-invented-publishing-token"


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv("BLOG_API_TOKEN", TOKEN)
    monkeypatch.setattr(config, "_TOKEN_FILE", "")


def options() -> dict:
    response = client.get("/api/blog/options", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_options_carry_the_forbidden_phrases_and_the_rules():
    data = options()
    assert isinstance(data["forbidden_phrases"], list)
    assert all(isinstance(phrase, str) for phrase in data["forbidden_phrases"])
    assert len(data["forbidden_phrases"]) >= 30
    assert isinstance(data["forbidden_rules"], list)
    for rule in data["forbidden_rules"]:
        assert set(rule) == {"category", "blocks", "phrases", "instead"}, rule
        assert isinstance(rule["blocks"], bool)
        assert rule["instead"].strip(), rule["category"]


@pytest.mark.parametrize("rule", [r for r in safety.FORBIDDEN if r["blocks"]],
                         ids=lambda r: r["category"])
def test_every_phrase_advertised_as_blocking_really_blocks(rule):
    """THE ANTI-DRIFT TEST. A phrase in this list that the checker does not actually catch is a
    client writing around a rule that was never there."""
    for phrase in rule["phrases"]:
        if rule["category"] == "placeholder" and phrase.startswith("{any_"):
            continue            # the example token, deliberately generic
        post = fixture.post(slug="a-draft-for-the-phrase-check",
                            body_md=f"## A heading\n\nA sentence that says {phrase} in it. "
                                    + ("Filler to clear the word floor. " * 60))
        blocking, warnings = safety.content_problems(post)
        assert blocking, f"{rule['category']}: {phrase!r} is advertised as blocking but passes"


@pytest.mark.parametrize("rule", [r for r in safety.FORBIDDEN if not r["blocks"]],
                         ids=lambda r: r["category"])
def test_a_phrase_advertised_as_a_warning_does_not_block(rule):
    """The other direction, and the one that costs money: telling a client something is forbidden
    when it is merely recorded makes it write around a rule that would not have stopped it."""
    for phrase in rule["phrases"]:
        post = fixture.post(slug="a-draft-for-the-warning-check",
                            body_md=f"## A heading\n\nA sentence that says {phrase} in it. "
                                    + ("Filler to clear the word floor. " * 60))
        blocking, warnings = safety.content_problems(post)
        assert not blocking, f"{rule['category']}: {phrase!r} is advertised as a warning but blocks"


def test_an_honest_negated_guarantee_is_not_in_the_forbidden_list_as_blocking():
    """The sentences this site WANTS written. Eleven drafts were once held back for them."""
    for sentence in ("No reading can guarantee an outcome.",
                     "A high score does not guarantee a happy marriage.",
                     "Nothing here is guaranteed."):
        post = fixture.post(slug="an-honest-draft",
                            body_md=f"## A heading\n\n{sentence} " + ("Filler words here. " * 70))
        blocking, _ = safety.content_problems(post)
        assert not blocking, f"{sentence!r} was blocked: {blocking}"


def test_every_blocking_rule_in_the_checker_has_an_entry():
    """The coverage direction: a rule added to the checker with no entry here is a rule a client
    cannot know about."""
    advertised = {rule["category"] for rule in safety.FORBIDDEN}
    for expected in ("guarantee", "certainty", "reader_harm", "impersonal_harm",
                     "personal_prediction", "gem_fear", "html", "placeholder"):
        assert expected in advertised, expected


def test_fact_check_warnings_is_advertised_as_accepted_and_non_blocking():
    """An unknown field is a 422 here, so a client has no way to discover one by trying."""
    field = options()["accepted_fields"]["fact_check_warnings"]
    assert field["type"] == "list[str]"
    assert field["blocks"] is False
    assert field["max_items"] >= 1 and field["max_chars"] >= 1


def test_a_post_with_fact_check_warnings_is_accepted_and_does_not_block():
    body = fixture.api_body(slug="a-draft-with-fact-check-warnings",
                            fact_check_warnings=["The 1986 date could not be verified.",
                                                 "The quoted verse was not traced to a source."])
    response = client.post("/api/blog/posts", json=body,
                           headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["fact_check_warnings"] == body["fact_check_warnings"]
    assert not data["checks"]["blocking"], data["checks"]["blocking"]


def test_the_warnings_reach_the_admin_page():
    from app.blog import store

    body = fixture.api_body(slug="a-draft-whose-warnings-are-shown",
                            fact_check_warnings=["An unverified claim about a date."])
    client.post("/api/blog/posts", json=body, headers={"Authorization": f"Bearer {TOKEN}"})
    post = store.get("a-draft-whose-warnings-are-shown")
    assert post["fact_check_warnings"] == ["An unverified claim about a date."]


def test_the_accepted_fields_are_really_accepted():
    """Advertising a field that the model then refuses with a 422 is worse than not advertising it."""
    for field, value in (("key_points", ["One", "Two", "Three"]),
                         ("fact_check_warnings", ["Unverified."]),
                         ("language", "en")):
        body = fixture.api_body(slug=f"a-draft-testing-{field.replace('_', '-')}", **{field: value})
        response = client.post("/api/blog/posts", json=body,
                               headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 201, f"{field}: {response.text}"


# ---- "100%" is a qualifier to delete, not a draft to refuse ---------------------------------------------


@pytest.mark.parametrize("before,after", [
    ("100% accurate predictions.", "Accurate predictions."),
    ("This is 100 per cent accurate.", "This is accurate."),
    ("A hundred per cent accurate reading.", "An accurate reading."),
    ("A 100% accurate forecast.", "An accurate forecast."),
    ("We offer a 100% refund within seven days.", "We offer a refund within seven days."),
])
def test_the_qualifier_is_dropped_and_the_sentence_still_reads(before, after):
    """On its own "100%" is a boast, not a promise, and blocking a whole draft for it costs a post to
    save a word. The article comes back as a or an according to what the deletion leaves behind -
    without that, this rule fixed a boast and introduced "a accurate reading"."""
    from app.blog import autofix

    assert autofix.deterministic(before)[0] == after


@pytest.mark.parametrize("text", [
    "Our kundli tool is 100% free.",
    "100% free and always will be.",
    "The chart is 100 per cent free to generate.",
])
def test_a_hundred_per_cent_free_is_left_alone(text):
    """It is true. Every tool behind that phrase costs nothing, and deleting the qualifier there
    removes a fact rather than a boast.

    THE LOOKAHEAD HAS TO COME BEFORE THE WHITESPACE. `\\s*` backtracks to nothing, so a `(?!free)`
    placed after it was tested against " free" rather than "free", passed, and deleted the qualifier
    anyway - leaving a double space where the fact had been."""
    from app.blog import autofix

    assert autofix.deterministic(text)[0] == text


def test_the_qualifier_alone_no_longer_blocks_a_draft():
    body = "## A heading\n\n100% accurate predictions. " + ("Filler words here. " * 60)
    fixed, fixes = _repaired(body)
    post = fixture.post(slug="a-draft-with-a-qualifier", body_md=fixed)
    blocking, _ = safety.content_problems(post)
    assert not blocking, blocking
    assert any("100%" in fix["what"] for fix in fixes)


def test_a_guarantee_still_blocks_after_the_qualifier_is_dropped():
    """"100% guaranteed results" becomes "guaranteed results" and is still refused - by the guarantee
    rule, which is the rule that should have been refusing it all along."""
    body = "## A heading\n\n100% guaranteed results for every reader. " + ("Filler words. " * 60)
    fixed, _ = _repaired(body)
    post = fixture.post(slug="a-draft-with-a-guarantee", body_md=fixed)
    blocking, _ = safety.content_problems(post)
    assert blocking and any("guarantee" in problem for problem in blocking), blocking


def test_a_guarantee_elsewhere_in_the_sentence_is_not_hidden_by_the_fix():
    body = "## A heading\n\nWe guarantee 100% satisfaction. " + ("Filler words here. " * 60)
    fixed, _ = _repaired(body)
    post = fixture.post(slug="a-draft-guaranteeing-satisfaction", body_md=fixed)
    blocking, _ = safety.content_problems(post)
    assert blocking, "the guarantee survived the qualifier being removed and must still block"


def test_the_fix_is_recorded_so_the_admin_page_can_show_it():
    """Every repair is stored with its before and after; a deletion is still a change to somebody
    else's words."""
    _, fixes = _repaired("## H\n\n100% accurate. " + ("Filler words here. " * 60))
    dropped = [fix for fix in fixes if "100%" in fix["what"]]
    assert dropped and dropped[0]["before"] and dropped[0]["by"] == "rules"


def test_the_options_no_longer_advertise_100_percent_as_blocking():
    """It is in `instead` as guidance, not in `phrases` as a thing that stops a post."""
    guarantee = next(r for r in options()["forbidden_rules"] if r["category"] == "guarantee")
    assert "100%" not in guarantee["phrases"]
    assert "100%" in guarantee["instead"], "the behaviour still has to be explained"


def _repaired(body: str):
    from app.blog import autofix

    return autofix.deterministic(body)
