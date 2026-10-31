"""/admin/blog: read a draft exactly as the public page would render it, and publish it in one click.

It follows app/admin: its own `APIRouter(prefix="/admin", include_in_schema=False)`, the same
`require_admin` gate, the same `_page` helper (so the nav, the IST clock, the insecure-transport warning
and the `no-store` headers are the dashboard's and not a second version of them), and the same
self-contained layout with no JavaScript on the page.

ONE CLICK IS NOT A BYPASS. Publishing re-runs every check against the body as it stands and refuses on a
blocking problem - `app/blog/publishing.go_live` is the only door, and `app/blog/store.publish` is the
only writer of `status = 'published'`. The button is there so that a human decision costs one click, not
so that the checks cost nothing.

THE FIRST WRITING PAGE IN /admin, AND THEREFORE THE FIRST THAT NEEDS A FORM TOKEN. Every other admin
page is a read. HTTP basic auth is sent by the browser on a cross-site request, and the session cookie
is `samesite=strict` but is not the only credential here, so a plain POST form on /admin would be
submittable from a page the operator merely visited. Each button therefore carries an HMAC over the
actor, the slug and the action, signed with the secret app/admin/auth.py already uses - so a form can
only have come from a page we rendered to this administrator. It is not a session: it does not expire,
because what it proves is origin rather than freshness.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin import audit
from app.admin.auth import require_admin


def templates():
    """The app's own Jinja environment, so the preview renders with the same filters and globals the
    public page does. Imported lazily for the reason _page() is: app.web.routes imports this package's
    parent at module level."""
    from app.web.routes import templates as jinja

    return jinja


def _page(*args, **kwargs):
    """app.admin.routes._page, imported WHEN CALLED rather than at module import.

    A module-level `from app.admin.routes import _page` closes an import cycle: app.admin.routes imports
    app.web, which builds the URL registry at import time, which lists published blog posts, which imports
    this package - and app.admin.routes is still half-initialised, so `_page` does not exist yet and the
    whole application fails to start. It is only ever called from inside a request handler, by which time
    every module is loaded.
    """
    from app.admin.routes import _page as render  # noqa: PLC0415 - deliberate; see above

    return render(*args, **kwargs)

from . import config, images, paths, publishing, safety, store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", include_in_schema=False)

PUBLISH = "blog.publish"
UNPUBLISH = "blog.unpublish"
REFUSED = "blog.publish.refused"
DELETE = "blog.delete"
HOLD = "blog.hold"
RELEASE = "blog.release"


def _form_token(actor: str, slug: str, action: str) -> str:
    from app.admin.auth import _secret

    payload = f"blog\x1f{actor}\x1f{slug}\x1f{action}"
    return hmac.new(_secret(), payload.encode(), "sha256").hexdigest()[:32]


def _check_form_token(actor: str, slug: str, action: str, supplied: str) -> None:
    if not hmac.compare_digest(supplied or "", _form_token(actor, slug, action)):
        log.warning("/admin/blog: a %s form for %s did not carry this administrator's token", action, slug)
        raise HTTPException(status_code=400, detail="this form did not come from your dashboard")


#: One hex string is the whole body of either form. Anything larger is not one of our forms.
_MAX_FORM_BYTES = 1024


async def _token_from(request: Request) -> str:
    """The form's own token, read out of the urlencoded body with the standard library.

    DELIBERATELY NOT FastAPI's `Form(...)` NOR Starlette's `request.form()`: both require
    `python-multipart`, which this project does not install - and these two buttons are the only form
    POSTs in the whole application, each sending one field of hex. Adding a dependency, and a deploy
    step for it, to read thirty-two characters would be the wrong trade. (The image upload avoids
    multipart for a stronger reason than convenience; see app/blog/images.py.)

    `parse_qsl` over a bounded body is the entire parser. It is read from the stream and cut off at the
    limit rather than buffered first with `request.body()`, because an admin route is still a route
    anybody can POST to, and a megabyte of nothing should not become a megabyte in this process.
    """
    from urllib.parse import parse_qsl

    media = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if media != "application/x-www-form-urlencoded":
        return ""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > _MAX_FORM_BYTES:
            return ""       # not one of our two forms, so there is no token in it to find
    fields = dict(parse_qsl(body.decode("utf-8", "replace")))
    return fields.get("token", "")


async def _fields_from(request: Request, limit: int) -> dict[str, str]:
    """An urlencoded body as a dict, bounded, with the standard library.

    THE SAME REASONING AS _token_from, with a bigger ceiling: the editor posts a whole Markdown body,
    not a token. `python-multipart` is still not a dependency of this project, and adding one - plus a
    deploy step for it - so that one admin textarea can be read would be the wrong trade when parse_qsl
    reads it in a line.

    Bounded by reading the stream rather than buffering it: an admin route is still a route anybody can
    POST to, and a body past the limit is refused rather than held in memory while it arrives.
    """
    from urllib.parse import parse_qsl

    media = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if media != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="send the form urlencoded")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise HTTPException(status_code=413, detail="that body is larger than an edit can be")
    return dict(parse_qsl(body.decode("utf-8", "replace")))


#: Enough for the longest body the API itself accepts, plus the token and urlencoding's overhead.
_MAX_EDIT_BYTES = config.MAX_BODY_CHARS * 3 + 4096


def _row_view(post: dict) -> dict:
    return {**post, "categories_view": [safety.CATEGORIES.get(name, name) for name in post["categories"]],
            "words": publishing.preview(post)["words"]}


@router.get("/blog", response_class=HTMLResponse)
def blog_list(request: Request, actor: str = Depends(require_admin),
              done: str = "") -> HTMLResponse:
    """Drafts first, then what is live. The count that matters is "how many are waiting for me"."""
    posts = [_row_view(post) for post in store.all_posts()]
    return _page(request, actor, "blog", "blog.html", {
        "posts": posts,
        "drafts": [post for post in posts if not post["is_published"]],
        "held": [post for post in posts if post.get("is_held") and not post["is_published"]],
        "done": done,
        "live": [post for post in posts if post["is_published"]],
        "blocked": [post for post in posts if post["blocking"]],
        "autopublish": config.autopublish(),
        "token_note": config.how_the_token_is_configured(),
        "config_problems": config.problems(),
        "registered": paths.registered(),
        "blog_path": paths.list_path(),
        "image_count": store.image_count(),
    })


@router.get("/blog/{slug}", response_class=HTMLResponse)
def blog_preview(request: Request, slug: str, actor: str = Depends(require_admin),
                 done: str = "") -> HTMLResponse:
    """The draft, rendered by the SAME renderer the public page uses, with the check report beside it.

    The checks are re-run on every view rather than read from the row: a check that was added after the
    post arrived has to be able to catch it, and a preview that shows a stale verdict is worse than one
    that shows none.
    """
    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="no such post")
    report = publishing.recheck(post)
    store.record_checks(slug, report)
    view = publishing.preview(post)
    return _page(request, actor, "blog", "blog_preview.html", {
        "post": _row_view(store.get(slug)),
        "view": view,
        "report": report,
        "done": done,
        "public_path": paths.post_path(slug),
        "blog_path": paths.list_path(),
        "hero_url": (paths.media_path(post["hero_image"])
                     if post.get("hero_image") and images.file_for(post["hero_image"]) else None),
        "edit_token": _form_token(actor, slug, EDIT),
        "publish_token": _form_token(actor, slug, PUBLISH),
        "unpublish_token": _form_token(actor, slug, UNPUBLISH),
        "hold_token": _form_token(actor, slug, HOLD),
        "autopublish": config.autopublish(),
    })


EDIT = "edit"


@router.post("/blog/{slug}/edit")
async def edit_post(request: Request, slug: str,
                    actor: str = Depends(require_admin)) -> RedirectResponse:
    """Save an edited draft body, then re-check it.

    DRAFTS ONLY. A published post is a URL somebody may already have shared and a page a search engine
    has already read; editing it from here would change what is live with no record that anything
    happened. Unpublish it first - that is one click, and it leaves a trail.

    The checks are re-run and stored on the way out, so the preview the editor lands back on reflects
    the text they just wrote rather than the text that arrived from the API.
    """
    form = await _fields_from(request, _MAX_EDIT_BYTES)
    _check_form_token(actor, slug, EDIT, form.get("token", ""))

    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="no such post")
    if post["is_published"]:
        raise HTTPException(status_code=409, detail="unpublish before editing")

    body = form.get("body_md", "")
    if not body.strip():
        raise HTTPException(status_code=422, detail="an empty body is not an edit")

    updated = {**post, "body_md": body,
               "categories": [name for name in (post.get("categories") or ())]}
    report = publishing.recheck(updated)
    store.save(updated, report, source="admin")
    # The audit line carries WHAT CHANGED in the only terms that survive: how long the body is now and
    # whether the checks still refuse it. The body itself is not written to the log - the audit trail is
    # read by people looking for who did what, not for a copy of every draft.
    audit.record(actor, "blog.edit", slug,
                 f"{len(body)} chars, {len(report.get('blocking') or ())} blocking", request=request)
    return _back(slug, "edited")


@router.post("/blog/{slug}/check", response_class=HTMLResponse)
async def check_draft(request: Request, slug: str,
                      actor: str = Depends(require_admin)) -> HTMLResponse:
    """Run the checks against a body WITHOUT saving it. For the editor's live feedback.

    THE SAME CHECKER THE PUBLISH GATE USES, deliberately. A second implementation for the editor would
    agree with the gate right up until the day it did not, and the day it did not would be a post that
    the editor called clean and the publish button refused - with nothing to say which was right.
    """
    form = await _fields_from(request, _MAX_EDIT_BYTES)
    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="no such post")
    report = publishing.recheck({**post, "body_md": form.get("body_md", "")})
    return HTMLResponse(_check_fragment(report), headers={"Cache-Control": "no-store"})


def _check_fragment(report: dict) -> str:
    """The check report as a small block of HTML the editor swaps in. Plain markup, no JSON contract:
    one reader, one writer, and the shape can change without a version negotiation."""
    import html as _html

    blocking = list(report.get("blocking") or ())
    warnings = list(report.get("warnings") or ())
    if not blocking and not warnings:
        return '<p class="ok">Nothing blocking, nothing to warn about.</p>'
    parts = []
    if blocking:
        parts.append("<p class=\"bad\"><strong>Blocking</strong> - cannot be published:</p><ul>"
                     + "".join(f"<li>{_html.escape(str(item))}</li>" for item in blocking) + "</ul>")
    if warnings:
        parts.append("<p class=\"warn\"><strong>Warnings</strong>:</p><ul>"
                     + "".join(f"<li>{_html.escape(str(item))}</li>" for item in warnings) + "</ul>")
    return "".join(parts)


@router.get("/blog/{slug}/rendered", response_class=HTMLResponse)
def blog_rendered(request: Request, slug: str, actor: str = Depends(require_admin)) -> HTMLResponse:
    """The draft through the PUBLIC template, exactly as a reader would get it.

    THE PREVIEW USED TO BE ITS OWN TEMPLATE, which meant "it looked right in preview" and "it looks
    right published" were two different renderings of the same post - and a preview that can disagree
    with the page is worth less than no preview, because it is trusted.

    This builds the public context through pages.post_context() and renders blog_post.html, the file
    the public route renders. The admin page embeds it in an iframe, so what an editor approves is the
    page itself rather than an impression of it.

    NEVER INDEXABLE AND NEVER CACHED. It is an admin route behind the same gate as the rest of this
    module, and it carries a draft - a crawler that found it would index a post nobody has approved.
    """
    from app.blog import pages as blog_pages

    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="no such post")
    language = post.get("language") or paths.LANG
    context = blog_pages.post_context(request, post, language)
    response = templates().TemplateResponse(request, "blog_post.html", context)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"

    # FRAMEABLE BY THIS SITE ONLY, and only this route. Every page here is served with
    # `X-Frame-Options: DENY` and `frame-ancestors 'none'`, which is correct and stays - the preview
    # arrived blank because of it, and the fix is to narrow the exception rather than widen the rule.
    #
    # SAMEORIGIN, not ALLOWALL: the only page that may frame this one is the admin page next to it, and
    # the route is behind the admin gate anyway, so a third party cannot reach it to frame it even if
    # they could. The site-wide header is untouched for every other URL.
    # The CSP's frame-ancestors is rewritten to match by app/hardening.py, which owns that header -
    # the policy is long and two copies of it would mean one going stale. This states the intent.
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@router.post("/blog/{slug}/publish")
async def publish_post(request: Request, slug: str,
                       actor: str = Depends(require_admin)) -> RedirectResponse:
    """One click. Re-checks, publishes, tells the engines, and writes an audit line either way.

    THE AUDIT LINE FOR A REFUSAL IS WRITTEN TOO. A log that only records successful publishes is a log
    that hides the interesting ones - the same reasoning app/admin/chat_access.py gives for recording an
    authorisation before the read it authorises.
    """
    _check_form_token(actor, slug, PUBLISH, await _token_from(request))
    if store.get(slug) is None:
        raise HTTPException(status_code=404, detail="no such post")
    try:
        result = publishing.go_live(slug, actor=actor, reason="published from /admin/blog")
    except store.Blocked as blocked:
        audit.record(actor, REFUSED, slug, f"{len(blocked.blocking)} blocking: {blocked.blocking[0]}",
                     request)
        return _back(slug, "blocked")
    audit.record(actor, PUBLISH, slug,
                 f"indexnow: {result['indexnow'].get('detail') or result['indexnow'].get('status')}",
                 request)
    return _back(slug, "published")


@router.post("/blog/{slug}/unpublish")
async def unpublish_post(request: Request, slug: str,
                         actor: str = Depends(require_admin)) -> RedirectResponse:
    """Back to a draft. The URL starts answering 404, which is the honest answer for a page that is no
    longer published; see `publishing.take_down` for why IndexNow is not called."""
    _check_form_token(actor, slug, UNPUBLISH, await _token_from(request))
    if store.get(slug) is None:
        raise HTTPException(status_code=404, detail="no such post")
    publishing.take_down(slug, actor=actor)
    audit.record(actor, UNPUBLISH, slug, "taken down from /admin/blog", request)
    return _back(slug, "unpublished")


@router.post("/blog/{slug}/hold")
async def hold_post(request: Request, slug: str,
                    actor: str = Depends(require_admin)) -> RedirectResponse:
    """Hold a draft out of the autopublish queue, or let it back in. One button, both directions.

    IT DOES NOT STOP A MANUAL PUBLISH, and that is the point of it. Holding a post is a decision about
    the queue running unattended at 09:30 - "not this one, not yet" - not a doubt about whether the
    post is fit to go out. Somebody standing on this page with the post in front of them can still
    publish it, and the button says so.
    """
    _check_form_token(actor, slug, HOLD, await _token_from(request))
    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="no such post")
    if post["is_published"]:
        # Nothing to hold: the queue only ever looks at drafts.
        return _back(slug, "nothing-to-hold")
    held = not post["is_held"]
    store.set_held(slug, held, actor=actor)
    audit.record(actor, HOLD if held else RELEASE, slug,
                 "held out of the autopublish queue" if held else "released into the queue", request)
    return _back(slug, "held" if held else "released")


@router.get("/blog/{slug}/delete", response_class=HTMLResponse)
def confirm_delete(request: Request, slug: str,
                   actor: str = Depends(require_admin)) -> HTMLResponse:
    """The confirmation step, as a page rather than a dialog.

    THESE PAGES CARRY NO JAVASCRIPT - `_back` says so and the rest of the admin keeps to it - so a
    `confirm()` would be the only script in the dashboard, and one that silently does nothing wherever
    script is blocked. A page can also say what a dialog cannot: the title, how long it has been here,
    and what else points at it.
    """
    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="no such post")
    return _page(request, actor, "blog", "blog_delete.html", {
        "post": _row_view(post),
        "translations": store.posts_translating(slug),
        "delete_token": _form_token(actor, slug, DELETE),
        "blog_path": paths.list_path(),
    })


@router.post("/blog/{slug}/delete")
async def delete_post(request: Request, slug: str,
                      actor: str = Depends(require_admin)) -> RedirectResponse:
    """Delete a draft for good. DRAFTS ONLY - take a published post down first.

    The audit line carries the TITLE, not only the slug. A deleted row cannot be looked up afterwards
    to find out what it was, so whatever the trail does not say is gone with it.
    """
    _check_form_token(actor, slug, DELETE, await _token_from(request))
    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="no such post")
    try:
        deleted = store.delete(slug)
    except store.StillPublished:
        audit.record(actor, REFUSED, slug, "delete refused: the post is published", request)
        return _back(slug, "still-published")
    unlinked = len(store.posts_translating(slug))
    audit.record(actor, DELETE, slug,
                 f"deleted draft {deleted['title']!r} ({deleted.get('language') or 'en'})"
                 + (f", unlinked {unlinked} translation(s)" if unlinked else ""), request)
    response = RedirectResponse("/admin/blog?done=deleted", status_code=303)
    response.headers.update({"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
                             "Referrer-Policy": "no-referrer"})
    return response


def _back(slug: str, done: str) -> RedirectResponse:
    """303 back to the preview. The outcome rides in the query string rather than in a flash cookie:
    these pages carry no JavaScript and no session state beyond the admin cookie, and a one-word
    `?done=` is readable in the address bar, which is its own kind of honesty."""
    response = RedirectResponse(f"/admin/blog/{slug}?done={done}", status_code=303)
    response.headers.update({"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
                             "Referrer-Policy": "no-referrer"})
    return response
