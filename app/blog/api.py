"""The publishing API an external writer ("Blogauto") posts to. Documented in docs/BLOG_API.md.

    POST   /api/blog/posts          create a post        -> 201
    PUT    /api/blog/posts/{slug}   replace a post       -> 200
    GET    /api/blog/posts/{slug}   read one back        -> 200
    POST   /api/blog/images         upload one image     -> 201

**POSTS ARRIVE AS DRAFTS.** `publish: true` in the body is a REQUEST, never an instruction: with
`BLOG_AUTOPUBLISH` off - which is the default and what ships - the answer is always a draft and the
response says so in words. That is not a limitation to be configured away later by whoever is in a
hurry; it is the only reason an API that accepts prose from outside this codebase is safe to expose at
all. The checks in app/blog/safety.py decide what *can* go live; a human on /admin/blog decides what
does.

THE TOKEN IS NEVER LOGGED, ECHOED OR RETURNED. `app/blog/config.py` holds it, compares it in constant
time and hands out a boolean. Nothing in this file reads its value, no error body contains any part of
it, and the log lines below name the slug and the outcome and nothing else. A box with no token
configured answers 404 to every route here, for the reason app/admin/auth.py answers 404 rather than
401: a 401 announces that there is something worth guessing at.

WHY `extra="forbid"`. A field name the spec does not list is a 422 rather than a silently ignored key.
The writer is a separate codebase being built against docs/BLOG_API.md; a typo that is quietly dropped
is a post that arrives wrong and looks fine.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from . import config, images, paths, publishing, safety, store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/blog")

NO_STORE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}


# ---- the gate ----------------------------------------------------------------------------------------


def _ip_key(request: Request) -> str:
    from app.admin import audit

    return audit.ip_key_of(request)


def _failures(ip_key: str) -> list[float]:
    """Recent failed attempts from this network. A READ of `rate_events`, whose one writer is
    `app.ai.chat_store.check_rate` - app/admin/auth.py reads it the same way and for the same reason,
    so there is one sliding-window implementation on this box and this is not a second."""
    from app.admin.auth import _failures_in_window

    return _failures_in_window(f"blog-api:{ip_key}", config.LOGIN_WINDOW_MINUTES * 60)


def _note_failure(ip_key: str) -> None:
    from app.ai.chat_store import RateLimited, check_rate

    try:
        check_rate(f"blog-api:{ip_key}", config.LOGIN_MAX_FAILURES, config.LOGIN_WINDOW_MINUTES * 60)
    except RateLimited:
        pass        # the attempt that trips the limit has already been refused; `_failures` decides


def require_token(request: Request) -> str:
    """The gate on every route here. Returns a caller label for the log, never the token.

    Order: configured? -> locked out? -> compare. The lock is checked before anything is compared, so a
    locked-out caller gets no timing signal about whether its guess was close.
    """
    if not config.configured():
        log.info("/api/blog: no publishing token is configured - answering 404")
        raise HTTPException(status_code=404, detail="not found")

    ip_key = _ip_key(request)
    window = config.LOGIN_WINDOW_MINUTES * 60
    recent = _failures(ip_key)
    if len(recent) >= config.LOGIN_MAX_FAILURES:
        import time

        wait = max(1, int(recent[0] + window - time.time()) + 1)
        raise HTTPException(status_code=429, detail={"error": "locked_out", "message":
                            f"too many failed attempts; try again in {wait} seconds"},
                            headers={"Retry-After": str(wait), **NO_STORE})

    header = request.headers.get("authorization") or ""
    scheme, _, supplied = header.partition(" ")
    if scheme.lower() != "bearer" or not config.matches(supplied.strip()):
        _note_failure(ip_key)
        # The refusal says nothing about the token - not its length, not whether the scheme was right.
        log.warning("/api/blog: refused a request with a bad or missing token")
        raise HTTPException(status_code=401, detail={"error": "unauthorised", "message":
                            "a valid bearer token is required; see docs/BLOG_API.md"},
                            headers={"WWW-Authenticate": "Bearer", **NO_STORE})
    return "blogauto"


# ---- shapes ------------------------------------------------------------------------------------------


class PostIn(BaseModel):
    """A post as the writer sends it. The limits here are a shape guard; the REAL limits, with messages
    that name the fix, are in app/blog/safety.py - a 422 from pydantic cannot explain why a summary has
    to be 50-230 characters, and that explanation is the useful half."""

    model_config = ConfigDict(extra="forbid")

    slug: str | None = Field(default=None, max_length=200, description=(
        "Lowercase words joined by hyphens. Omitted, it is derived from the title."))
    title: str = Field(min_length=1, max_length=400)
    summary: str = Field(min_length=1, max_length=1000, description="The page's meta description.")
    body_markdown: str = Field(min_length=1, max_length=config.MAX_BODY_CHARS + 2000, description=(
        "Markdown, in the subset docs/BLOG_API.md lists. HTML is refused, not sanitised."))
    tool: str = Field(min_length=1, max_length=60, description=(
        "Registry key of the free tool this post is about. GET /api/blog/options lists them."))
    categories: list[str] = Field(default_factory=list, max_length=10)
    hero_image_id: str | None = Field(default=None, max_length=64)
    author: str | None = Field(default=None, max_length=80, description=(
        "A byline. It must be the publication's own name - never a private individual's."))
    fact_check_warnings: list[str] = Field(default_factory=list, max_length=20, description=(
        "Anything the writer could not verify. OPTIONAL, and the one field that stops a post "
        "publishing itself however clean its checks are: a claim nobody has stood behind is exactly "
        "what a person should read before it goes out. Leave it empty when there is nothing to say."))
    key_points: list[str] = Field(default_factory=list, max_length=5, description=(
        "Three to five short takeaways, shown as a 'Key points' box above the post. Optional - a post "
        "without them gets a contents box built from its own headings instead, which is a smaller "
        "claim: a heading says what a section is about, a takeaway says what to conclude."))
    language: str = Field(default="en", description=(
        "Which tree the post belongs to: en, hi or mr. A post lives in ONE tree - the language it was "
        "written in - and is not shown in the others. Default en, so a caller that never sends this "
        "keeps behaving exactly as before."))
    translation_of: str | None = Field(default=None, max_length=200, description=(
        "The slug of the post this one translates, if any. It is what links the two as hreflang "
        "alternates; the translation keeps its own slug. Omit for an original."))
    publish: bool = Field(default=False, description=(
        "A REQUEST to go live. Honoured only when BLOG_AUTOPUBLISH is on AND nothing is blocking; "
        "otherwise the post is a draft and the response says so."))


def _check_language(value: str) -> str:
    """A tree that exists, or a refusal naming the ones that do.

    Accepting an unknown language would write a post nothing ever lists: no route serves that tree, so
    it would be live, invisible, and look like a publishing bug rather than a typo.
    """
    language = (value or paths.LANG).strip().lower()
    if language not in paths.LANGS:
        raise HTTPException(status_code=422, detail={
            "error": "unknown_language", "given": value,
            "known": list(paths.LANGS),
            "message": "A post belongs to one language tree. Known trees: " + ", ".join(paths.LANGS)})
    return language


def _check_key_points(points: list[str]) -> list[str]:
    """Three to five, each short enough to read at a glance, or none at all.

    REFUSED RATHER THAN TRIMMED. A caller that sends eight takeaways meant eight; silently keeping five
    would publish a box that misrepresents what they wrote, and they would never know. Two is refused
    for the same reason a one-item list is not a list: a box with two lines in it reads as an omission.
    """
    cleaned = [str(point).strip() for point in points if str(point).strip()]
    if not cleaned:
        return []
    if not 3 <= len(cleaned) <= 5:
        raise HTTPException(status_code=422, detail={
            "error": "key_points_count", "given": len(cleaned),
            "message": "Send between 3 and 5 key points, or none at all."})
    too_long = [point for point in cleaned if len(point) > 120]
    if too_long:
        raise HTTPException(status_code=422, detail={
            "error": "key_point_too_long", "message": (
                "A key point is one line somebody reads at a glance - 120 characters at most. "
                f"This one is {len(too_long[0])}.")})
    return cleaned


def _submission(body: PostIn, slug: str | None = None) -> dict:
    return {
        "slug": (slug or body.slug or paths.slugify(body.title)).strip().lower(),
        "title": body.title.strip(),
        "summary": body.summary.strip(),
        "body_md": body.body_markdown,
        "tool": body.tool.strip(),
        "categories": [name.strip().lower() for name in body.categories if name.strip()],
        "hero_image": (body.hero_image_id or "").strip() or None,
        "author": (body.author or "").strip(),
        "language": _check_language(body.language),
        "key_points": _check_key_points(body.key_points),
        "fact_check_warnings": [str(w).strip()[:300] for w in body.fact_check_warnings if str(w).strip()],
        "translation_of": (body.translation_of or "").strip().lower() or None,
    }


def _view(post: dict, report: dict, *, asked_to_publish: bool) -> dict:
    """The response body. It says what happened AND why, which is the difference between an API a
    separate codebase can be built against and one whose behaviour has to be reverse-engineered."""
    blocking = list(report.get("blocking") or ())
    if post["is_published"]:
        message = "published"
    elif asked_to_publish:
        # THE GATE EXPLAINS ITSELF. One function decides, and the caller is told which condition it
        # was - a writer who cannot see why a post stayed a draft files a bug about the wrong thing.
        _allowed, message = publishing.may_autopublish(post, report)
        message = f"saved as a draft: {message}"
    elif blocking:
        message = (f"saved as a draft: {len(blocking)} check(s) must be fixed before it can be published. "
                   "See `checks.blocking`")
    else:
        message = "saved as a draft, and it passes every check. It goes live when somebody publishes it"
    return {
        "slug": post["slug"],
        "status": post["status"],
        "url": post["path"],
        "autopublish": config.autopublish(),
        "published_at": store.iso_moment(post.get("published_at")) or None,
        "updated_at": store.iso_moment(post.get("updated_at")) or None,
        "checks": {"blocking": blocking, "warnings": list(report.get("warnings") or ())},
        # WHAT WE CHANGED, handed straight back. A writer whose prose was edited on the way in should
        # be able to see every edit from the response that accepted it, not by opening the admin page.
        "fixes": list(post.get("fixes") or ()),
        "fact_check_warnings": list(post.get("fact_check_warnings") or ()),
        "message": message,
    }


def _save(submission: dict, *, asked_to_publish: bool, caller: str) -> dict:
    if submission["hero_image"] and images.file_for(submission["hero_image"]) is None:
        raise HTTPException(status_code=422, detail={"error": "unknown_image", "message":
                            f"there is no image {submission['hero_image']!r}. Upload it with "
                            "POST /api/blog/images and use the `id` that comes back"})
    # REPAIRED BEFORE IT IS CHECKED. Deterministic fixes, then at most two model rounds, then the
    # checks run against the text as it will be published rather than as it arrived. Every repair is
    # kept with its before and after so /admin/blog can show what we changed to somebody else's prose.
    submission, report, fixes = publishing.repair_and_check(submission)
    submission = {**submission, "fixes": fixes}
    post = store.save(submission, report, source="api")     # always a draft; `store.save` cannot publish

    # THE ONE PLACE THE FLAG IS APPLIED. Every condition lives in `may_autopublish`, so none of them
    # can be lost in a later edit here: the install allows it, nothing is blocking, the writer
    # attached no fact-check warnings, and the day's allowance is not spent.
    if asked_to_publish and not post["is_published"]:
        allowed, _why = publishing.may_autopublish(post, report)
        if allowed:
            try:
                post = publishing.go_live(post["slug"], actor=caller, reason="blog autopublish")["post"]
            except store.Blocked as blocked:
                # Unreachable while the gate holds; if it is ever reached, the post stays a draft and
                # the reasons are recorded against it, which is the safe direction to fall.
                log.error("blog: %s asked to autopublish but its re-check refused: %s",
                          post["slug"], "; ".join(blocked.blocking)[:200])
                post = store.get(post["slug"])
    log.info("blog: %s saved by %s as %s (%d blocking, %d warning(s))", post["slug"], caller,
             post["status"], len(report["blocking"]), len(report["warnings"]))
    return _view(post, report, asked_to_publish=asked_to_publish)


# ---- routes ------------------------------------------------------------------------------------------


@router.get("/options")
def options(caller: str = Depends(require_token)) -> Response:
    """The vocabularies a post has to use, so the writer never has to hardcode ours."""
    return _json({
        "tools": [{"key": key, "path": paths.tool_link(key)["path"], "label": paths.TOOLS[key]}
                  for key in paths.tool_keys()],
        "categories": [{"key": key, "label": label} for key, label in safety.CATEGORIES.items()],
        "limits": {
            "title_chars": [config.MIN_TITLE_CHARS, config.MAX_TITLE_CHARS],
            "summary_chars": [config.MIN_SUMMARY_CHARS, config.MAX_SUMMARY_CHARS],
            "body_words_min": config.MIN_BODY_WORDS,
            "body_chars_max": config.MAX_BODY_CHARS,
            "categories_max": config.MAX_CATEGORIES,
            "image_bytes_max": config.MAX_IMAGE_BYTES,
            "image_types": list(images.ACCEPTED),
        },
        "autopublish": config.autopublish(),
        "language": paths.LANG,
        # WHAT THE CHECKER BLOCKS, BEFORE A WRITER WRITES. A generating client puts these in its own
        # prompt and checks its own text, so a blocked draft is caught where it can still be changed
        # cheaply rather than arriving here and waiting for somebody.
        # `forbidden_phrases` is the flat list for a prompt; `forbidden_rules` groups them with what
        # to write instead and whether each one blocks or is merely recorded.
        "forbidden_phrases": safety.forbidden_phrases(),
        "forbidden_rules": safety.forbidden_rules(),
        # THE OPTIONAL FIELDS A POST MAY CARRY. Advertised because an unknown field is a 422 here, so
        # a client has no way to discover one by trying. `fact_check_warnings` is information only: it
        # is stored, shown on /admin/blog, and logged at publish time, and it never blocks a post.
        "accepted_fields": {
            "fact_check_warnings": {
                "type": "list[str]",
                "max_items": 20,
                "max_chars": 300,
                "blocks": False,
                "what": ("What the writer could not verify. Recorded against the post and shown to "
                         "whoever reads it on /admin/blog. It never holds a post back - a claim "
                         "nobody stood behind is worth knowing about, but waiting for somebody's "
                         "evening costs more than it saves."),
            },
            "key_points": {"type": "list[str]", "max_items": 5, "blocks": False,
                           "what": "Three to five short takeaways, shown above the article."},
            "language": {"type": "str", "blocks": False,
                         "what": "Which tree the post lives in: en, hi or mr. Defaults to en."},
            "translation_of": {"type": "str|null", "blocks": False,
                               "what": "The slug of the post this one translates, for hreflang."},
        },
    })


@router.post("/posts", status_code=201)
def create_post(body: PostIn, caller: str = Depends(require_token)) -> Response:
    submission = _submission(body)
    if store.get(submission["slug"]) is not None:
        raise HTTPException(status_code=409, detail={"error": "slug_taken", "message":
                            f"a post with the slug {submission['slug']!r} already exists. Update it with "
                            f"PUT /api/blog/posts/{submission['slug']}, or choose another slug"})
    return _json(_save(submission, asked_to_publish=body.publish, caller=caller), status=201)


@router.put("/posts/{slug}")
def update_post(slug: str, body: PostIn, caller: str = Depends(require_token)) -> Response:
    """A full replacement of the editable fields. There is no PATCH: a partial update of prose that is
    about to be checked as a whole is an invitation to check half of it."""
    if store.get(slug) is None:
        raise HTTPException(status_code=404, detail={"error": "no_such_post", "message":
                            f"there is no post with the slug {slug!r}"})
    if body.slug and body.slug.strip().lower() != slug:
        # A slug is a published URL. Changing it silently would leave the old one 404ing with no
        # redirect, so it is refused and the writer is told what to do instead.
        raise HTTPException(status_code=409, detail={"error": "slug_immutable", "message":
                            "a slug cannot be changed: it is the post's public URL, and moving it would "
                            "leave the old one answering 404. Create a new post and take this one down"})
    return _json(_save({**_submission(body, slug=slug)}, asked_to_publish=body.publish, caller=caller))


@router.get("/posts/{slug}")
def read_post(slug: str, caller: str = Depends(require_token)) -> Response:
    """Read one back - its state, and why it is still a draft if it is."""
    post = store.get(slug)
    if post is None:
        raise HTTPException(status_code=404, detail={"error": "no_such_post", "message":
                            f"there is no post with the slug {slug!r}"})
    return _json({**_view(post, {"blocking": post["blocking"], "warnings": post["warnings"]},
                          asked_to_publish=False),
                  "title": post["title"], "summary": post["summary"], "tool": post["tool"],
                  "categories": post["categories"], "hero_image_id": post["hero_image"],
                  "checked_at": store.iso_moment(post.get("checked_at")) or None})


@router.post("/images", status_code=201)
async def upload_image(request: Request, caller: str = Depends(require_token)) -> Response:
    """One image, as the RAW REQUEST BODY - not a multipart form.

    The body is the file. There is no `filename` in the protocol, so there is no name to sanitise; the
    type is read from the bytes rather than from `Content-Type`; and the size is counted while reading
    rather than taken from `Content-Length`. app/blog/images.py explains each of those, and
    docs/BLOG_API.md gives the curl line.
    """
    try:
        data = await images.read_body_within_limit(request)
        row = images.save(data, sent_as=request.headers.get("x-blog-image-label", ""))
    except images.UploadRefused as refused:
        raise HTTPException(status_code=refused.status,
                            detail={"error": "image_refused", "message": refused.message}) from None
    log.info("blog: image %s accepted from %s (%d bytes, %s)", row["id"], caller, row["bytes_len"],
             row["media_type"])
    return _json({"id": row["id"], "url": row["url"], "media_type": row["media_type"],
                  "bytes": row["bytes_len"],
                  "note": "nothing here decodes the image, so its dimensions are not reported"},
                 status=201)


def _json(payload: dict, status: int = 200) -> Response:
    import json

    return Response(json.dumps(payload, ensure_ascii=False), status_code=status,
                    media_type="application/json", headers=NO_STORE)
