"""The publishing API: the gate, the draft rule, and what an upload is allowed to be.

The three things this file is really for:

1. **POSTS ARRIVE AS DRAFTS.** `publish: true` is a request, not an instruction. With
   `BLOG_AUTOPUBLISH` off - the default, and what ships - the answer is always a draft, and the
   response says why in words. Asserted from both sides: the flag off, and the flag on with something
   blocking.
2. **The token is never logged, echoed or returned.** Asserted mechanically, over the response bodies
   AND over everything the application logged during the request, because "we were careful" is not a
   property a reader can check.
3. **An upload is the most hostile input this application takes.** Size, type and emptiness, each
   refused with its own status code.

No real person, no real address. The token below is invented and the post is about the ayanamsa.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.blog import config, images, paths, store
from app.main import app
from tests import blog_fixture as fixture

TOKEN = "an-invented-publishing-token-long-enough-to-be-real"
client = TestClient(app)


@pytest.fixture(autouse=True)
def token_in_the_environment(monkeypatch):
    """The env-var route, which is the fallback; the file route is asserted separately below."""
    monkeypatch.setattr(config, "_TOKEN_FILE", "")
    monkeypatch.setenv("BLOG_API_TOKEN", TOKEN)
    monkeypatch.setattr(config, "AUTOPUBLISH", False)


def auth(token: str = TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def no_indexnow(monkeypatch):
    """IndexNow, recorded rather than called. It already refuses off production by design; this is so a
    test can assert that publishing DID submit, which is the half that could silently stop happening."""
    from app.web import indexnow

    calls = []

    def fake(payload, *, reason=""):
        calls.append((list(payload), reason))
        return {"sent": len(payload), "status": 200, "detail": ""}

    monkeypatch.setattr(indexnow, "submit", fake)
    return calls


# ---- 1. the gate -------------------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", [
    ("get", "/api/blog/options"), ("post", "/api/blog/posts"), ("put", "/api/blog/posts/x"),
    ("get", "/api/blog/posts/x"), ("post", "/api/blog/images"),
])
def test_with_no_token_configured_the_api_does_not_exist(method, path, monkeypatch):
    """404 AND NOT 401, for the reason app/admin/auth.py answers 404: a 401 announces that there is
    something here worth guessing at. It also means a half-finished deploy cannot accept a post."""
    monkeypatch.delenv("BLOG_API_TOKEN", raising=False)
    response = client.request(method.upper(), path, headers=auth(), json=fixture.api_body())
    assert response.status_code == 404


@pytest.mark.parametrize("headers", [
    {}, {"Authorization": "Bearer wrong-token"}, {"Authorization": TOKEN},
    {"Authorization": f"Basic {TOKEN}"}, {"Authorization": "Bearer "},
])
def test_a_missing_or_wrong_token_is_a_401_that_says_nothing_about_the_token(headers):
    response = client.get("/api/blog/options", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    body = response.text
    assert TOKEN not in body and "wrong-token" not in body
    assert "length" not in body.lower()      # not even a hint about the shape of the right one


def test_the_token_is_never_echoed_or_logged(caplog):
    caplog.set_level(logging.DEBUG)
    for headers in (auth(), auth("a-wrong-guess-at-the-token")):
        client.post("/api/blog/posts", headers=headers, json=fixture.api_body())
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert TOKEN not in logged and "a-wrong-guess-at-the-token" not in logged
    assert "/api/blog: refused a request with a bad or missing token" in logged


def test_enough_wrong_guesses_locks_the_caller_out(monkeypatch):
    monkeypatch.setattr(config, "LOGIN_MAX_FAILURES", 3)
    for _ in range(3):
        assert client.get("/api/blog/options", headers=auth("nope")).status_code == 401
    # Locked: the RIGHT token is not even compared now, which is the point - a locked-out caller gets no
    # timing signal about whether its guess was close.
    locked = client.get("/api/blog/options", headers=auth())
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) >= 1
    assert locked.json()["detail"]["error"] == "locked_out"


def test_a_token_file_with_loose_permissions_is_ignored(tmp_path, monkeypatch, caplog):
    """A token file the whole box can read is not a secret. Using it anyway would hide that from
    whoever set it up, so it is refused - and the MODE is logged, never the contents."""
    caplog.set_level(logging.ERROR)
    path = tmp_path / "token"
    path.write_text(TOKEN)
    path.chmod(0o644)
    monkeypatch.setattr(config, "_TOKEN_FILE", str(path))
    assert not config.configured()
    assert client.get("/api/blog/options", headers=auth()).status_code == 404
    assert TOKEN not in "\n".join(record.getMessage() for record in caplog.records)

    path.chmod(0o600)
    assert config.configured() and client.get("/api/blog/options", headers=auth()).status_code == 200


def test_the_options_endpoint_hands_over_our_vocabularies():
    """So the writer never hardcodes a tool key, a category or a limit of ours."""
    body = client.get("/api/blog/options", headers=auth()).json()
    assert {tool["key"] for tool in body["tools"]} == set(paths.tool_keys())
    assert body["language"] == "en" and body["autopublish"] is False
    assert body["limits"]["summary_chars"] == [config.MIN_SUMMARY_CHARS, config.MAX_SUMMARY_CHARS]
    assert body["limits"]["image_types"] == list(images.ACCEPTED)


# ---- 2. posts arrive as drafts -----------------------------------------------------------------------


def test_a_clean_post_is_created_as_a_draft():
    response = client.post("/api/blog/posts", headers=auth(), json=fixture.api_body())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["url"] == paths.post_path(fixture.SLUG)
    assert body["checks"] == {"blocking": [], "warnings": []}
    assert body["published_at"] is None
    assert "goes live when somebody publishes it" in body["message"]
    assert client.get(body["url"]).status_code == 404      # a draft is a 404 on the public site


def test_publish_true_is_a_request_and_not_an_instruction():
    """THE WHOLE POINT OF THE FLAG. With BLOG_AUTOPUBLISH off, a caller asking to publish is told, in
    words, that the post is a draft and where it goes live from."""
    body = client.post("/api/blog/posts", headers=auth(),
                       json=fixture.api_body(publish=True)).json()
    assert body["status"] == "draft" and body["autopublish"] is False
    assert "BLOG_AUTOPUBLISH is off" in body["message"] and "/admin/blog" in body["message"]
    assert store.get(fixture.SLUG)["status"] == "draft"


def test_with_autopublish_on_a_clean_post_goes_live_and_the_engines_are_told(monkeypatch, no_indexnow):
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    body = client.post("/api/blog/posts", headers=auth(), json=fixture.api_body(publish=True)).json()
    assert body["status"] == "published" and body["published_at"]
    assert client.get(body["url"]).status_code == 200
    assert no_indexnow and no_indexnow[0][0] == [paths.post_path(fixture.SLUG), paths.list_path()]
    assert "autopublish" in no_indexnow[0][1]


def test_with_autopublish_on_a_post_that_fails_a_check_still_stays_a_draft(monkeypatch, no_indexnow):
    """The flag decides whether a CLEAN post may go live. It is not a way round the checks, and the
    reason is written down with the post so /admin/blog can say why."""
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    # THE PROBLEM IS IN THE TITLE, because the last resort can save one in the body: it deletes the
    # offending sentence and publishes what is left, which is what it is for. A title cannot be
    # rebuilt from anything else, so it is the case that still proves the gate.
    bad = fixture.api_body(publish=True, title="The outcome is guaranteed for everyone")
    body = client.post("/api/blog/posts", headers=auth(), json=bad).json()
    assert body["status"] == "draft"
    assert any("a guarantee" in problem for problem in body["checks"]["blocking"])
    # The message now names WHICH condition of the autopublish gate stopped it, rather than
    # restating that something is blocking - a writer who cannot see why a post stayed a draft
    # files a bug about the wrong thing.
    assert "must be fixed first" in body["message"]
    assert "checks.blocking" in body["message"]
    assert not no_indexnow                                   # nothing was submitted
    stored = store.get(fixture.SLUG)
    assert stored["status"] == "draft" and stored["blocking"]      # the reason survives a restart


def test_autopublish_does_not_apply_to_a_caller_that_did_not_ask(monkeypatch, no_indexnow):
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    body = client.post("/api/blog/posts", headers=auth(), json=fixture.api_body()).json()
    assert body["status"] == "draft" and not no_indexnow


# ---- 3. the rest of the lifecycle --------------------------------------------------------------------


def test_a_repeated_slug_is_a_409_that_names_the_way_forward():
    client.post("/api/blog/posts", headers=auth(), json=fixture.api_body())
    again = client.post("/api/blog/posts", headers=auth(), json=fixture.api_body())
    assert again.status_code == 409
    assert again.json()["detail"]["error"] == "slug_taken"
    assert f"PUT /api/blog/posts/{fixture.SLUG}" in again.json()["detail"]["message"]


def test_an_update_replaces_the_prose_and_re_runs_every_check():
    client.post("/api/blog/posts", headers=auth(), json=fixture.api_body())
    better = fixture.api_body(title="What the ayanamsa is, exactly")
    response = client.put(f"/api/blog/posts/{fixture.SLUG}", headers=auth(), json=better)
    assert response.status_code == 200
    assert store.get(fixture.SLUG)["title"] == "What the ayanamsa is, exactly"
    assert response.json()["checks"]["blocking"] == []


def test_a_slug_cannot_be_changed_by_an_update():
    """A slug is a published URL. Moving it silently would leave the old one answering 404 with no
    redirect behind it."""
    client.post("/api/blog/posts", headers=auth(), json=fixture.api_body())
    response = client.put(f"/api/blog/posts/{fixture.SLUG}", headers=auth(),
                          json=fixture.api_body(slug="a-different-slug"))
    assert response.status_code == 409 and response.json()["detail"]["error"] == "slug_immutable"


def test_updating_a_live_post_into_a_problem_marks_it_rather_than_taking_it_down(monkeypatch,
                                                                                no_indexnow):
    """A live URL vanishing is the more damaging of the two failures, and the admin page shows the
    problem in red the moment it is opened. Taking it down is a decision somebody makes with the reason
    in front of them."""
    monkeypatch.setattr(config, "AUTOPUBLISH", True)
    client.post("/api/blog/posts", headers=auth(), json=fixture.api_body(publish=True))
    # In the TITLE, for the reason above: a cure in the body is now deleted and the post publishes.
    broken = fixture.api_body(title="This mantra cures it at the root")
    body = client.put(f"/api/blog/posts/{fixture.SLUG}", headers=auth(), json=broken).json()
    assert body["status"] == "published"
    assert any("medical claim" in problem for problem in body["checks"]["blocking"])
    assert store.get(fixture.SLUG)["blocking"]


def test_an_unknown_slug_is_a_404_on_update_and_on_read():
    assert client.put("/api/blog/posts/nope", headers=auth(), json=fixture.api_body(slug="nope")
                      ).status_code == 404
    assert client.get("/api/blog/posts/nope", headers=auth()).status_code == 404


def test_reading_a_post_back_says_why_it_is_still_a_draft():
    bad = fixture.api_body(summary="Too short.")
    client.post("/api/blog/posts", headers=auth(), json=bad)
    body = client.get(f"/api/blog/posts/{fixture.SLUG}", headers=auth()).json()
    assert body["status"] == "draft" and body["tool"] == fixture.TOOL
    assert any("the summary is" in problem for problem in body["checks"]["blocking"])


def test_a_field_the_spec_does_not_list_is_refused_rather_than_ignored():
    """The writer is a separate codebase built against docs/BLOG_API.md. A typo that is quietly dropped
    is a post that arrives wrong and looks fine."""
    response = client.post("/api/blog/posts", headers=auth(),
                           json={**fixture.api_body(), "publsh": True})
    assert response.status_code == 422
    assert "publsh" in response.text


def test_a_slug_is_derived_from_the_title_when_the_caller_does_not_choose_one():
    body = fixture.api_body()
    body.pop("slug")
    response = client.post("/api/blog/posts", headers=auth(), json=body)
    assert response.status_code == 201
    assert response.json()["slug"] == "what-the-ayanamsa-actually-is"


def test_a_hero_image_that_was_never_uploaded_is_refused():
    response = client.post("/api/blog/posts", headers=auth(),
                           json={**fixture.api_body(), "hero_image_id": "f" * 32})
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unknown_image"


# ---- 4. images ---------------------------------------------------------------------------------------


def test_an_image_is_uploaded_as_the_raw_body_and_comes_back_with_its_url():
    response = client.post("/api/blog/images", headers={**auth(), "Content-Type": "image/png",
                                                        "X-Blog-Image-Label": "hero shot.png"},
                           content=fixture.PNG_1PX)
    assert response.status_code == 201
    body = response.json()
    assert body["media_type"] == "image/png" and body["bytes"] == len(fixture.PNG_1PX)
    assert body["url"] == paths.media_path(body["id"])
    assert client.get(body["url"]).status_code == 200
    # it can then be a post's hero image
    created = client.post("/api/blog/posts", headers=auth(),
                          json={**fixture.api_body(), "hero_image_id": body["id"]})
    assert created.status_code == 201
    assert store.get(fixture.SLUG)["hero_image"] == body["id"]


def test_the_declared_content_type_is_not_believed():
    """The type is read from the bytes. A PNG announced as a JPEG is stored as the PNG it is; a script
    announced as a PNG is refused."""
    png = client.post("/api/blog/images", headers={**auth(), "Content-Type": "image/jpeg"},
                      content=fixture.PNG_1PX)
    assert png.status_code == 201 and png.json()["media_type"] == "image/png"

    lie = client.post("/api/blog/images", headers={**auth(), "Content-Type": "image/png"},
                      content=b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>")
    assert lie.status_code == 415 and lie.json()["detail"]["error"] == "image_refused"


def test_an_image_over_the_limit_is_refused_while_it_is_being_read(monkeypatch):
    monkeypatch.setattr(config, "MAX_IMAGE_BYTES", 256)
    monkeypatch.setattr(config, "MAX_IMAGE_KB", 1)
    response = client.post("/api/blog/images", headers={**auth(), "Content-Type": "image/png"},
                           content=fixture.PNG_1PX + b"\x00" * 600)
    assert response.status_code == 413
    assert store.image_count() == 0


def test_an_empty_body_is_refused_and_says_the_body_is_the_file():
    response = client.post("/api/blog/images", headers=auth(), content=b"")
    assert response.status_code == 400 and "body IS the image" in response.json()["detail"]["message"]


def test_every_api_response_is_marked_no_store_and_noindex():
    for response in (client.get("/api/blog/options", headers=auth()),
                     client.post("/api/blog/posts", headers=auth(), json=fixture.api_body()),
                     client.get("/api/blog/options", headers=auth("wrong"))):
        assert response.headers["cache-control"] == "no-store", response.status_code
        assert "noindex" in response.headers["x-robots-tag"], response.status_code
