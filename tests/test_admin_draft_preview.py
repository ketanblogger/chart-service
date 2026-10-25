"""The admin preview is the public page, and the one place framing is relaxed to make that possible.

A PREVIEW THAT CAN DISAGREE WITH THE PAGE IS WORSE THAN NO PREVIEW, because it is trusted. The admin
used to print the post's body HTML into the admin layout: the same markdown, a different template,
different CSS, no chrome. "It looked right in preview" and "it looks right published" were two
different renderings of one post.

It now embeds /admin/blog/<slug>/rendered, which builds the PUBLIC context through
app/blog/pages.post_context() and renders blog_post.html - the file the public route renders.
"""
from __future__ import annotations

import re

import pytest

# `admin_env` is autouse IN ITS OWN MODULE only, so importing the client without it gave every request
# the public 404 page and the assertions failed on markup from a completely different template.
from tests.test_blog_admin import (  # noqa: F401
    a_draft, admin_env, client, header, no_indexnow)
from tests import blog_fixture as fixture

SLUG = fixture.SLUG


def test_the_preview_embeds_the_real_page(client):
    a_draft()
    html = client.get(f"/admin/blog/{SLUG}", headers=header()).text
    assert f"/admin/blog/{SLUG}/rendered" in html
    # two frames: the phone width and the full width, because a post reads differently at each
    assert html.count(f"/admin/blog/{SLUG}/rendered") >= 2


def test_the_rendered_route_uses_the_public_template(client):
    """Not a copy of it. One builder, one template, so the two cannot drift."""
    a_draft()
    rendered = client.get(f"/admin/blog/{SLUG}/rendered", headers=header()).text
    assert "post__body" in rendered          # the public template's own class
    assert '<h2 id="where-the-number-comes-from">Where the number comes from</h2>'  # the id is what the contents box links to in rendered


def test_exactly_one_route_may_be_framed(client):
    """THE SITE-WIDE RULE STAYS. Every page is served `X-Frame-Options: DENY` and
    `frame-ancestors 'none'`; the preview arrived blank because of it, and the fix was to narrow the
    exception rather than widen the rule."""
    a_draft()
    framed = client.get(f"/admin/blog/{SLUG}/rendered", headers=header())
    assert framed.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in framed.headers["content-security-policy"]

    for path in (f"/admin/blog/{SLUG}", "/admin/blog"):
        other = client.get(path, headers=header())
        assert other.headers["x-frame-options"] == "DENY", path
        assert "frame-ancestors 'none'" in other.headers["content-security-policy"], path


def test_no_public_page_can_relax_its_framing(client):
    """The exception is bounded to /admin/ in app/hardening.py, so a public route cannot opt out of
    DENY however it sets its own headers."""
    from fastapi.testclient import TestClient

    from app.main import app

    public = TestClient(app)
    for path in ("/", "/blog", "/birth-chart"):
        response = public.get(path)
        assert response.headers["x-frame-options"] == "DENY", path
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"], path


def test_the_editor_script_is_a_file_and_not_inline(client):
    """`script-src 'self'` blocks inline scripts outright. The first version of the editor was inline,
    so the live checks never ran and the only sign was a console line nobody was reading."""
    a_draft()
    html = client.get(f"/admin/blog/{SLUG}", headers=header()).text
    assert "/static/js/blog-editor.js" in html
    body = html[html.index("<h2>Edit</h2>"):]
    assert "<script>" not in body, "an inline script would be blocked by the policy"


def test_the_admin_page_may_frame_its_own_origin(client):
    """The other half: the page DOING the framing needs frame-src, and only 'self' is added."""
    a_draft()
    policy = client.get(f"/admin/blog/{SLUG}", headers=header()).headers["content-security-policy"]
    frame_src = re.search(r"frame-src [^;]*", policy)
    assert frame_src and "'self'" in frame_src.group(0)

    from fastapi.testclient import TestClient

    from app.main import app

    public_policy = TestClient(app).get("/blog").headers["content-security-policy"]
    public_frame = re.search(r"frame-src [^;]*", public_policy)
    assert public_frame and "'self'" not in public_frame.group(0), \
        "a public page gained the ability to frame same-origin content"


def test_the_rendered_draft_is_never_indexed_or_cached(client):
    a_draft()
    rendered = client.get(f"/admin/blog/{SLUG}/rendered", headers=header())
    assert rendered.headers["x-robots-tag"] == "noindex, nofollow"
    assert rendered.headers["cache-control"] == "private, no-store"
