"""/admin/blog: holding a draft out of the autopublish queue, and deleting one for good.

TWO BUTTONS THAT PULL IN OPPOSITE DIRECTIONS and must not be confused with each other. Holding is
reversible, changes nothing about the post, and is a decision about the 09:30 queue running
unattended. Deleting is final. The whole design question here is making the reversible one the
obvious choice, and the final one cost a second page.

The hold is deliberately NOT a veto on publishing. A person standing on the preview with the post in
front of them can still publish it - holding said "not by itself, not yet", which is a statement about
the unattended queue, not a doubt about the post.

Invented people only; `tests/` is published.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from app.admin import audit
from app.blog import config, publishing, store
from app.main import app
from tests import blog_fixture as fixture

PASSWORD = "an-admin-password-long-enough-to-be-real"


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("SESSION_SECRET", "test-blog-hold-session-secret")
    monkeypatch.setenv("BASE_URL", "https://admin.test")
    monkeypatch.setattr(config, "AUTOPUBLISH", False)
    monkeypatch.setattr(config, "_TOKEN_FILE", "")


@pytest.fixture
def client():
    return TestClient(app, base_url="https://admin.test")


def header() -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode()).decode()}


def a_draft(**overrides) -> dict:
    post = fixture.post(**overrides)
    store.save(post, publishing.recheck(post))
    return store.get(post["slug"])


def form_token(client, path: str, action: str) -> str:
    """Read the token off the page, as a browser would - never recomputed here."""
    import re

    html = client.get(path, headers=header()).text
    forms = re.findall(r'<form[^>]*action="([^"]+)"[^>]*>\s*'
                       r'<input type="hidden" name="token" value="([0-9a-f]+)">', html)
    for action_path, token in forms:
        if action_path.endswith(f"/{action}"):
            return token
    raise AssertionError(f"no {action} form with a token on {path}")


# ---- the gate ----------------------------------------------------------------------------------------


def test_both_new_routes_are_behind_the_same_door(client):
    draft = a_draft()
    for path in (f"/admin/blog/{draft['slug']}/hold", f"/admin/blog/{draft['slug']}/delete"):
        assert client.post(path, data={"token": "x"}).status_code == 401, path
    assert client.get(f"/admin/blog/{draft['slug']}/delete").status_code == 401


def test_neither_acts_without_this_administrator_s_token(client):
    """Basic auth is sent by the browser on a cross-site request, so the token is what makes a POST
    form on /admin not submittable from any page the operator merely visited."""
    draft = a_draft()
    for action in ("hold", "delete"):
        response = client.post(f"/admin/blog/{draft['slug']}/{action}",
                               data={"token": "0" * 32},
                               headers={**header(), "content-type": "application/x-www-form-urlencoded"})
        assert response.status_code == 400, action
    assert store.get(draft["slug"]) is not None, "the draft was deleted without a valid token"


# ---- hold --------------------------------------------------------------------------------------------


def test_holding_takes_a_draft_out_of_the_queue_and_releasing_puts_it_back(client, monkeypatch):
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    draft = a_draft()
    assert draft["slug"] in [post["slug"] for post in publishing.publish_queue()]

    token = form_token(client, f"/admin/blog/{draft['slug']}", "hold")
    client.post(f"/admin/blog/{draft['slug']}/hold", data={"token": token},
                headers={**header(), "content-type": "application/x-www-form-urlencoded"})
    assert store.get(draft["slug"])["is_held"] is True
    assert draft["slug"] not in [post["slug"] for post in publishing.publish_queue()]

    token = form_token(client, f"/admin/blog/{draft['slug']}", "hold")
    client.post(f"/admin/blog/{draft['slug']}/hold", data={"token": token},
                headers={**header(), "content-type": "application/x-www-form-urlencoded"})
    assert store.get(draft["slug"])["is_held"] is False
    assert draft["slug"] in [post["slug"] for post in publishing.publish_queue()]


def test_a_held_draft_is_not_released_by_the_timer(client, monkeypatch, no_indexnow=None):
    """The queue is what the 09:30 timer drains. A held post must survive it."""
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    from app.web import indexnow
    monkeypatch.setattr(indexnow, "submit",
                        lambda paths_, *, reason="": {"sent": 0, "status": 0, "detail": "test"})
    draft = a_draft()
    store.set_held(draft["slug"], True, actor="admin")
    went_live = publishing.release_due(actor="autopublish")
    assert draft["slug"] not in [post["slug"] for post in went_live]
    assert store.get(draft["slug"])["is_published"] is False


def test_may_autopublish_says_why_in_words_somebody_can_act_on(monkeypatch):
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    draft = a_draft()
    store.set_held(draft["slug"], True, actor="admin")
    post = store.get(draft["slug"])
    may, why = publishing.may_autopublish(post, publishing.recheck(post))
    assert may is False
    assert "held" in why and "/admin/blog" in why
    assert "by hand still works" in why, "it must say the hold is not a veto on publishing"


def test_a_blocking_check_is_still_reported_on_a_held_post(monkeypatch):
    """The hold is checked AFTER the checks on purpose. A held post that also fails a check must
    report the check - the hold is about timing and the check is a fact about the post, and hiding the
    second behind the first would make it look ready when it is not."""
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    draft = a_draft(body_md="")
    store.set_held(draft["slug"], True, actor="admin")
    post = store.get(draft["slug"])
    may, why = publishing.may_autopublish(post, publishing.recheck(post))
    assert may is False
    assert "check" in why, f"the check should be reported before the hold: {why}"


def test_holding_does_not_stop_a_person_publishing_it(client, monkeypatch):
    """THE POINT OF THE FEATURE. Holding says "not by itself, not yet"."""
    from app.web import indexnow
    monkeypatch.setattr(indexnow, "submit",
                        lambda paths_, *, reason="": {"sent": 0, "status": 0, "detail": "test"})
    draft = a_draft()
    store.set_held(draft["slug"], True, actor="admin")
    token = form_token(client, f"/admin/blog/{draft['slug']}", "publish")
    response = client.post(f"/admin/blog/{draft['slug']}/publish", data={"token": token},
                           headers={**header(), "content-type": "application/x-www-form-urlencoded"},
                           follow_redirects=False)
    assert response.status_code == 303, response.text[:200]
    assert store.get(draft["slug"])["is_published"] is True


def test_who_held_it_and_when_are_kept(client):
    """"Why is this one not going out?" is asked days later, usually by the person who held it."""
    draft = a_draft()
    store.set_held(draft["slug"], True, actor="someone")
    post = store.get(draft["slug"])
    assert post["held_by"] == "someone" and post["held_at"]
    store.set_held(draft["slug"], False, actor="someone")
    post = store.get(draft["slug"])
    assert post["held_by"] is None and post["held_at"] is None


def test_the_list_page_shows_a_held_draft_without_opening_it(client):
    draft = a_draft()
    store.set_held(draft["slug"], True, actor="admin")
    html = client.get("/admin/blog", headers=header()).text
    assert "held" in html


def test_holding_writes_an_audit_line_in_both_directions(client):
    draft = a_draft()
    for _ in range(2):
        token = form_token(client, f"/admin/blog/{draft['slug']}", "hold")
        client.post(f"/admin/blog/{draft['slug']}/hold", data={"token": token},
                    headers={**header(), "content-type": "application/x-www-form-urlencoded"})
    actions = [row["action"] for row in audit.recent(50)]
    assert "blog.hold" in actions and "blog.release" in actions


# ---- delete ------------------------------------------------------------------------------------------


def test_delete_asks_first_and_the_question_page_changes_nothing(client):
    draft = a_draft()
    page = client.get(f"/admin/blog/{draft['slug']}/delete", headers=header())
    assert page.status_code == 200
    assert "cannot be undone" in page.text
    assert draft["title"] in page.text, "the page must say WHAT is about to be deleted"
    assert store.get(draft["slug"]) is not None, "a GET deleted something"


def test_the_confirmation_is_a_page_not_a_script(client):
    """The admin dashboard carries no JavaScript, so a confirm() would be the only script in it - and
    one that silently does nothing wherever script is blocked, turning a guarded button into an
    unguarded one."""
    draft = a_draft()
    page = client.get(f"/admin/blog/{draft['slug']}/delete", headers=header()).text
    assert "<script" not in page.lower()
    assert "confirm(" not in page


def test_deleting_a_draft_removes_it(client):
    draft = a_draft()
    token = form_token(client, f"/admin/blog/{draft['slug']}/delete", "delete")
    response = client.post(f"/admin/blog/{draft['slug']}/delete", data={"token": token},
                           headers={**header(), "content-type": "application/x-www-form-urlencoded"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/blog?done=deleted"
    assert store.get(draft["slug"]) is None


def test_a_published_post_cannot_be_deleted(client, monkeypatch):
    """A published post is a URL somebody may have shared and a page a crawler has read. Deleting one
    would make it 404 with no trail and no way back."""
    from app.web import indexnow
    monkeypatch.setattr(indexnow, "submit",
                        lambda paths_, *, reason="": {"sent": 0, "status": 0, "detail": "test"})
    draft = a_draft()
    publishing.go_live(draft["slug"], actor="admin")
    assert store.get(draft["slug"])["is_published"] is True
    with pytest.raises(store.StillPublished):
        store.delete(draft["slug"])
    assert store.get(draft["slug"]) is not None


def test_the_route_refuses_a_published_post_too_and_says_so(client, monkeypatch):
    from app.web import indexnow
    monkeypatch.setattr(indexnow, "submit",
                        lambda paths_, *, reason="": {"sent": 0, "status": 0, "detail": "test"})
    draft = a_draft()
    token = form_token(client, f"/admin/blog/{draft['slug']}/delete", "delete")
    publishing.go_live(draft["slug"], actor="admin")
    response = client.post(f"/admin/blog/{draft['slug']}/delete", data={"token": token},
                           headers={**header(), "content-type": "application/x-www-form-urlencoded"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert "still-published" in response.headers["location"]
    assert store.get(draft["slug"]) is not None


def test_the_audit_line_carries_the_title_because_the_row_is_gone(client):
    """A deleted row cannot be looked up afterwards to find out what it was."""
    draft = a_draft()
    token = form_token(client, f"/admin/blog/{draft['slug']}/delete", "delete")
    client.post(f"/admin/blog/{draft['slug']}/delete", data={"token": token},
                headers={**header(), "content-type": "application/x-www-form-urlencoded"})
    lines = [row for row in audit.recent(50) if row["action"] == "blog.delete"]
    assert lines, "no audit line for a delete"
    assert draft["title"] in lines[0]["detail"]


def test_a_translation_is_unlinked_rather_than_deleted_with_its_original(client):
    """A translation is somebody's work too, and cascading from a slug would be a surprising amount of
    deleting for one button."""
    original = a_draft()
    other = a_draft(slug="a-translated-draft", language="hi", translation_of=original["slug"])
    assert store.posts_translating(original["slug"])[0]["slug"] == other["slug"]

    token = form_token(client, f"/admin/blog/{original['slug']}/delete", "delete")
    client.post(f"/admin/blog/{original['slug']}/delete", data={"token": token},
                headers={**header(), "content-type": "application/x-www-form-urlencoded"})
    assert store.get(original["slug"]) is None
    kept = store.get(other["slug"])
    assert kept is not None, "the translation was deleted with its original"
    assert kept["translation_of"] is None, "it still points at a slug that no longer exists"


def test_the_confirmation_page_warns_about_the_translations_it_will_unlink(client):
    original = a_draft()
    a_draft(slug="another-translated-draft", language="hi", translation_of=original["slug"])
    page = client.get(f"/admin/blog/{original['slug']}/delete", headers=header()).text
    assert "name this one as their original" in page
    assert "another-translated-draft" in page or "not deleted" in page


def test_deleting_something_that_is_not_there_is_a_404(client):
    assert client.get("/admin/blog/no-such-draft-at-all/delete",
                      headers=header()).status_code == 404


def test_the_two_translation_lookups_are_not_the_same_function():
    """`translations_of` answers hreflang and returns PUBLISHED alternates of a post; the delete page
    needs posts pointing at a slug INCLUDING drafts. The first version of the second one was called
    `translations_of` as well and shadowed the first - had they been defined the other way round,
    hreflang would have broken for every translated post on the site."""
    import inspect

    assert store.translations_of is not store.posts_translating
    hreflang = inspect.signature(store.translations_of).parameters
    delete_side = inspect.signature(store.posts_translating).parameters
    assert "post" in hreflang and "slug" in delete_side


def test_hreflang_still_only_sees_published_alternates():
    """The guard on the collision above: a DRAFT translation must not become an hreflang entry."""
    original = a_draft(slug="an-original-for-hreflang")
    a_draft(slug="a-draft-translation", language="hi", translation_of=original["slug"])
    assert store.translations_of(store.get(original["slug"])) == [], \
        "a draft reached hreflang"
    assert len(store.posts_translating(original["slug"])) == 1, \
        "the delete page must see the draft it would unlink"
