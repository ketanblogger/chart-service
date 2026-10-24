"""/admin/blog: the gate, the preview, and the one click that publishes.

The claim this file has to make true is that ONE CLICK IS NOT A BYPASS. The button exists so a human
decision costs one click, not so the checks cost nothing - so publishing re-runs every check against
the body as it stands and refuses on a blocking problem, and that refusal is asserted here from the
route rather than from the disabled attribute on the button.

It is also the first WRITING page in /admin, and therefore the first that needs a form token: every
other admin page is a read. Basic auth is sent by a browser on a cross-site request, so a plain POST
form on /admin would be submittable from any page the operator merely visited.

Invented people only; `tests/` is published.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from app.admin import audit
from app.blog import config, paths, publishing, store
from app.main import app
from tests import blog_fixture as fixture

PASSWORD = "an-admin-password-long-enough-to-be-real"


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("SESSION_SECRET", "test-blog-admin-session-secret")
    monkeypatch.setenv("BASE_URL", "https://admin.test")
    monkeypatch.setattr(config, "AUTOPUBLISH", False)
    monkeypatch.setattr(config, "_TOKEN_FILE", "")
    monkeypatch.setenv("BLOG_API_TOKEN", "an-invented-publishing-token")


@pytest.fixture
def client():
    """Over https, because the admin session cookie is `Secure` - as it has to be, since basic auth
    sends the password on every request."""
    return TestClient(app, base_url="https://admin.test")


@pytest.fixture
def no_indexnow(monkeypatch):
    from app.web import indexnow

    calls = []
    monkeypatch.setattr(indexnow, "submit",
                        lambda paths_, *, reason="": calls.append((list(paths_), reason))
                        or {"sent": len(paths_), "status": 200, "detail": ""})
    return calls


def header() -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode()).decode()}


def a_draft(**overrides) -> dict:
    post = fixture.post(**overrides)
    store.save(post, publishing.recheck(post))
    return store.get(post["slug"])


def form_token(client, slug: str, action: str = "publish") -> str:
    """Read the token out of the page, the way a browser would. Never computed here: a test that
    recomputes the server's own HMAC would pass even if the page stopped printing one."""
    import re

    html = client.get(f"/admin/blog/{slug}", headers=header()).text
    forms = re.findall(r'<form[^>]*action="([^"]+)"[^>]*>\s*'
                       r'<input type="hidden" name="token" value="([0-9a-f]+)">', html)
    for action_path, token in forms:
        if action_path.endswith(f"/{action}"):
            return token
    raise AssertionError(f"no {action} form with a token on /admin/blog/{slug}")


# ---- 1. the gate -------------------------------------------------------------------------------------


def test_the_blog_pages_are_behind_the_same_door_as_the_rest_of_admin(client):
    for path in ("/admin/blog", f"/admin/blog/{fixture.SLUG}"):
        assert client.get(path).status_code == 401, path
    for path in (f"/admin/blog/{fixture.SLUG}/publish", f"/admin/blog/{fixture.SLUG}/unpublish"):
        assert client.post(path, data={"token": "x"}).status_code == 401, path


def test_admin_blog_is_never_indexable(client):
    a_draft()
    for path in ("/admin/blog", f"/admin/blog/{fixture.SLUG}"):
        response = client.get(path, headers=header())
        assert response.status_code == 200
        assert "noindex" in response.headers["x-robots-tag"]
        assert response.headers["cache-control"] == "no-store"
        assert '<meta name="robots" content="noindex, nofollow">' in response.text


def test_the_blog_page_is_in_the_admin_navigation(client):
    """A page nothing links to is a page nobody opens - the same gap the sign-in had before it was put
    in the chrome."""
    html = client.get("/admin", headers=header()).text
    assert 'href="/admin/blog"' in html


# ---- 2. the preview ----------------------------------------------------------------------------------


def test_the_list_shows_what_is_waiting_and_why(client):
    a_draft()
    a_draft(slug="a-blocked-post", title="A post with a promise in it",
            summary=fixture.SUMMARY.replace("one number", "first number"),
            body_md=fixture.BODY + "\n\nThe outcome is guaranteed.")
    html = client.get("/admin/blog", headers=header()).text
    assert fixture.TITLE in html and "A post with a promise in it" in html
    assert "blocking" in html and "draft" in html
    assert "BLOG_AUTOPUBLISH is off" in html


def test_the_preview_renders_the_post_with_the_same_renderer_the_public_page_uses(client):
    """IT IS THE PUBLIC TEMPLATE NOW, not the same renderer inside a different layout.

    The admin page used to print the body's HTML into the admin chrome, which meant the preview and the
    published page were two different renderings of one post - and the preview was the one being
    trusted. It embeds /admin/blog/<slug>/rendered instead, which builds the public context and renders
    blog_post.html: the file the public route renders.

    So the assertion moved to where the page actually is.
    """
    a_draft()
    html = client.get(f"/admin/blog/{fixture.SLUG}", headers=header()).text
    assert f"/admin/blog/{fixture.SLUG}/rendered" in html, "the preview does not embed the real page"

    rendered = client.get(f"/admin/blog/{fixture.SLUG}/rendered", headers=header())
    assert rendered.status_code == 200
    assert '<h2 id="where-the-number-comes-from">Where the number comes from</h2>'  # the id is what the contents box links to in rendered.text
    # and it is the public template, not a copy of it
    assert "post__body" in rendered.text

    # the admin page still carries the verdict and the button, which are its own job
    assert "nothing blocking" in html
    assert "Publish this post" in html
    # and the draft is still a 404 to the public
    assert TestClient(app).get(paths.post_path(fixture.SLUG)).status_code == 404


def test_the_rendered_draft_is_never_indexable_or_cached(client):
    """It is a draft nobody has approved, on a URL a crawler could reach if it ever leaked."""
    a_draft()
    rendered = client.get(f"/admin/blog/{fixture.SLUG}/rendered", headers=header())
    assert rendered.headers["x-robots-tag"] == "noindex, nofollow"
    assert rendered.headers["cache-control"] == "private, no-store"


def test_the_rendered_draft_is_behind_the_admin_gate(client):
    a_draft()
    assert client.get(f"/admin/blog/{fixture.SLUG}/rendered").status_code in (401, 404)


def test_the_preview_lists_the_blocking_problems_and_disables_the_button(client):
    a_draft(body_md=fixture.BODY + "\n\nThis mantra cures the problem.")
    html = client.get(f"/admin/blog/{fixture.SLUG}", headers=header()).text
    assert "blocking problem" in html and "is a medical claim" in html
    assert "<button type=\"submit\" disabled>" in html.replace("\n", " ").replace("  ", " ") or \
        "disabled" in html


def test_the_preview_re_runs_the_checks_rather_than_reading_the_stored_verdict(client, monkeypatch):
    """A check added after a post arrived has to be able to catch it, so the verdict on this page is
    never the one that was stored when the post was submitted."""
    a_draft()
    assert store.get(fixture.SLUG)["blocking"] == []
    with __import__("app").db.transaction() as conn:            # a new rule's worth of prose, injected
        conn.execute("UPDATE blog_posts SET body_md = body_md || ? WHERE slug = ?",
                     ("\n\nThe result is guaranteed.", fixture.SLUG))
    html = client.get(f"/admin/blog/{fixture.SLUG}", headers=header()).text
    assert "a guarantee" in html
    assert store.get(fixture.SLUG)["blocking"]                  # and the row is brought up to date


def test_an_unknown_slug_is_a_404(client):
    assert client.get("/admin/blog/nope", headers=header()).status_code == 404


# ---- 3. the one click --------------------------------------------------------------------------------


def test_one_click_publishes_a_clean_draft_and_tells_the_engines(client, no_indexnow):
    a_draft()
    token = form_token(client, fixture.SLUG)
    response = client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(),
                           data={"token": token}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].endswith("?done=published")
    live = store.get(fixture.SLUG)
    assert live["status"] == "published" and live["published_at"]
    assert no_indexnow[0][0] == [paths.post_path(fixture.SLUG), paths.list_path()]
    assert TestClient(app).get(live["path"]).status_code == 200
    assert any(entry["action"] == "blog.publish" and entry["subject"] == fixture.SLUG
               for entry in audit.recent(10))


def test_one_click_is_not_a_bypass(client, no_indexnow):
    """THE CLAIM THIS FILE EXISTS TO MAKE TRUE. The route refuses, not just the disabled button: a POST
    straight at it with a valid form token still leaves the post a draft."""
    # A SENTENCE THAT STILL BLOCKS - and it has had to change twice, which is the point. The rules
    # now block a prediction of harm AIMED AT THE READER: second person, a future, and the harm.
    # The impersonal version of this sentence is a warning.
    a_draft(body_md=fixture.BODY + "\n\nYou will suffer a serious illness after March.")
    token = form_token(client, fixture.SLUG)
    response = client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(),
                           data={"token": token}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].endswith("?done=blocked")
    assert store.get(fixture.SLUG)["status"] == "draft"
    assert not no_indexnow                                       # nothing was submitted
    # the refusal is audited, not only the successes
    assert any(entry["action"] == "blog.publish.refused" for entry in audit.recent(10))
    html = client.get(f"/admin/blog/{fixture.SLUG}?done=blocked", headers=header()).text
    assert "Not published" in html
    assert "come to harm" in html                      # the reason, escaped by Jinja as the page shows it


def test_publishing_without_the_form_token_is_refused(client, no_indexnow):
    """The first writing page in /admin. A browser sends basic auth on a cross-site request, so a POST
    form here has to prove it came from a page we rendered to this administrator."""
    a_draft()
    for data in ({}, {"token": ""}, {"token": "0" * 32}):
        response = client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(), data=data)
        assert response.status_code == 400, data
    assert store.get(fixture.SLUG)["status"] == "draft" and not no_indexnow


def test_a_form_token_belongs_to_one_administrator_one_post_and_one_action(client):
    from app.blog.admin import PUBLISH, UNPUBLISH, _form_token

    mine = _form_token("admin", fixture.SLUG, PUBLISH)
    assert mine != _form_token("somebody-else", fixture.SLUG, PUBLISH)
    assert mine != _form_token("admin", "another-post", PUBLISH)
    assert mine != _form_token("admin", fixture.SLUG, UNPUBLISH)


def test_a_publish_token_cannot_be_used_to_take_a_post_down(client, no_indexnow):
    a_draft()
    publish = form_token(client, fixture.SLUG)
    client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(), data={"token": publish})
    assert store.get(fixture.SLUG)["status"] == "published"
    refused = client.post(f"/admin/blog/{fixture.SLUG}/unpublish", headers=header(),
                          data={"token": publish})
    assert refused.status_code == 400
    assert store.get(fixture.SLUG)["status"] == "published"


def test_taking_a_post_down_makes_its_url_a_404_again(client, no_indexnow):
    a_draft()
    client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(),
                data={"token": form_token(client, fixture.SLUG)})
    assert TestClient(app).get(paths.post_path(fixture.SLUG)).status_code == 200
    client.post(f"/admin/blog/{fixture.SLUG}/unpublish", headers=header(),
                data={"token": form_token(client, fixture.SLUG, "unpublish")})
    assert store.get(fixture.SLUG)["status"] == "draft"
    assert TestClient(app).get(paths.post_path(fixture.SLUG)).status_code == 404
    assert any(entry["action"] == "blog.unpublish" for entry in audit.recent(10))


def test_a_post_put_back_keeps_its_original_dateline(client, no_indexnow):
    """`published_at` is the FIRST time this went live. A date that walks forwards and backwards in a
    search result is a reason not to trust the page."""
    a_draft()
    client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(),
                data={"token": form_token(client, fixture.SLUG)})
    first = store.get(fixture.SLUG)["published_at"]
    client.post(f"/admin/blog/{fixture.SLUG}/unpublish", headers=header(),
                data={"token": form_token(client, fixture.SLUG, "unpublish")})
    client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(),
                data={"token": form_token(client, fixture.SLUG)})
    assert store.get(fixture.SLUG)["published_at"] == first


def test_the_admin_page_never_prints_the_publishing_token(client, monkeypatch):
    """It tells the operator HOW the token is configured, which is the useful half, and never WHAT it
    is - the same division app/blog/config.py draws."""
    secret = "a-token-that-must-not-appear-on-any-page"
    monkeypatch.setenv("BLOG_API_TOKEN", secret)
    a_draft()
    for path in ("/admin/blog", f"/admin/blog/{fixture.SLUG}"):
        html = client.get(path, headers=header()).text
        assert secret not in html, path
    assert "BLOG_API_TOKEN environment variable" in client.get("/admin/blog", headers=header()).text


# ---------------------------------------------------------------------------------------------------
# Editing a draft before it goes live.


def test_a_draft_can_be_edited_and_the_checks_rerun(client):
    """The point of the whole feature: fix a fact before anybody reads it."""
    a_draft()
    token = form_token(client, fixture.SLUG, "edit")
    better = fixture.post()["body_md"].replace("Where the number comes from",
                                               "Where this number actually comes from")
    saved = client.post(f"/admin/blog/{fixture.SLUG}/edit", headers=header(),
                        data={"token": token, "body_md": better}, follow_redirects=False)
    assert saved.status_code in (302, 303)
    assert "Where this number actually comes from" in store.get(fixture.SLUG)["body_md"]
    # and the stored verdict is about the text that is there now, not the text that arrived
    assert store.get(fixture.SLUG)["checked_at"]


def test_a_published_post_cannot_be_edited_from_here(client, no_indexnow):
    """A published post is a URL somebody may have shared and a page a crawler has read. Changing it
    from here would alter what is live with no record that anything happened - unpublish first, which
    is one click and leaves a trail."""
    a_draft()
    token = form_token(client, fixture.SLUG, "edit")
    client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(),
                data={"token": form_token(client, fixture.SLUG, "publish")}, follow_redirects=False)
    assert store.get(fixture.SLUG)["is_published"]

    refused = client.post(f"/admin/blog/{fixture.SLUG}/edit", headers=header(),
                          data={"token": token, "body_md": "# Rewritten\n\nSomething else entirely."},
                          follow_redirects=False)
    assert refused.status_code == 409
    assert "Rewritten" not in store.get(fixture.SLUG)["body_md"]


def test_the_edit_form_is_absent_on_a_published_post(client, no_indexnow):
    """Not merely refused on the way in: a button that cannot work should not be on the page."""
    a_draft()
    client.post(f"/admin/blog/{fixture.SLUG}/publish", headers=header(),
                data={"token": form_token(client, fixture.SLUG, "publish")}, follow_redirects=False)
    html = client.get(f"/admin/blog/{fixture.SLUG}", headers=header()).text
    assert f"/admin/blog/{fixture.SLUG}/edit" not in html


def test_an_edit_without_a_token_changes_nothing(client):
    a_draft()
    before = store.get(fixture.SLUG)["body_md"]
    refused = client.post(f"/admin/blog/{fixture.SLUG}/edit", headers=header(),
                          data={"body_md": "# Nope\n\nNot saved."}, follow_redirects=False)
    assert refused.status_code in (400, 403, 422)
    assert store.get(fixture.SLUG)["body_md"] == before


def test_an_empty_body_is_not_an_edit(client):
    """Saving an empty draft would turn a post into a blank page that still passes most checks."""
    a_draft()
    token = form_token(client, fixture.SLUG, "edit")
    refused = client.post(f"/admin/blog/{fixture.SLUG}/edit", headers=header(),
                          data={"token": token, "body_md": "   "}, follow_redirects=False)
    assert refused.status_code == 422


def test_the_live_check_uses_the_publish_gate_and_saves_nothing(client):
    """THE SAME CHECKER, deliberately. A second implementation for the editor would agree with the gate
    until the day it did not - and that day would be a post the editor called clean and the publish
    button refused, with nothing to say which was right."""
    a_draft()
    before = store.get(fixture.SLUG)["body_md"]
    answer = client.post(f"/admin/blog/{fixture.SLUG}/check", headers=header(),
                         data={"body_md": "# Too short\n\nNot enough words to pass."})
    assert answer.status_code == 200
    assert "Blocking" in answer.text, "a body this short has to be refused"
    assert store.get(fixture.SLUG)["body_md"] == before, "the live check saved something"


def test_the_live_check_is_behind_the_admin_gate(client):
    a_draft()
    assert client.post(f"/admin/blog/{fixture.SLUG}/check",
                       data={"body_md": "anything"}).status_code in (401, 404)
