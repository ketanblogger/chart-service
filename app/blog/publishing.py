"""The one path from "a post exists" to "a post is public", shared by the API and the admin page.

TWO CALLERS, ONE DOOR. `app/blog/api.py` reaches this only when `BLOG_AUTOPUBLISH` is on; `app/blog/
admin.py` reaches it when somebody clicks Publish. Both go through `go_live`, which re-runs every check
against the body AS IT STANDS and refuses on a blocking problem - so the one-click publish is a decision
rather than a bypass, which is the whole point of it existing.

INDEXNOW IS CALLED, NOT WORKED AROUND. `app/web/indexnow.py` returns "not submitted" off production by
design: a developer regenerating pages on a laptop was spending the site's real submission quota, and
the 429 that came back is how it was noticed. So this calls it unconditionally and reports what it said,
including the off-production refusal - which is information, not a failure. Nothing waits on it and
nothing fails because of it.
"""

from __future__ import annotations

import logging

from . import autofix, config, markdown, paths, safety, store

log = logging.getLogger(__name__)


def recheck(post: dict) -> dict:
    """Run every check against a post (a stored row or a fresh submission) as it stands right now.

    The stored report is never trusted for a publish decision: it is evidence about the text that was
    submitted, and what matters is the text about to go public.
    """
    return safety.check(post, known_slugs=store.slug_status(), taken_titles=store.taken_titles())


#: AT MOST THIS MANY POSTS GO LIVE BY THEMSELVES IN ONE IST DAY. The rest queue, oldest first.
#:
#: A writer that produces thirty good posts on a Tuesday is not a reason to publish thirty on a
#: Tuesday: a site that does that looks like what it is, and the whole value of the blog is that it
#: does not. Two a day is also a readable amount for somebody checking what went out under their name.
AUTOPUBLISH_PER_DAY = 2


def repair_and_check(post: dict, *, client=None) -> tuple[dict, dict, list[dict]]:
    """Fix what can be fixed, then check. Returns (post, report, fixes).

    THE ORDER IS THE POINT. Rules first, then at most two model rounds, then the checks decide - so
    what a check sees is the text as it will be published, not as it arrived. A post that still has a
    blocking problem after all of that stays a draft, which is the outcome auto-fix is allowed to
    reach and the only one it is allowed to reach by itself.
    """
    fixed, fixes = autofix.repair(post, recheck, client=client)
    return fixed, recheck(fixed), fixes


def may_autopublish(post: dict, report: dict) -> tuple[bool, str]:
    """(may it, why not). Every condition in one place, so none is lost in a later edit."""
    if not config.autopublish():
        return False, ("BLOG_AUTOPUBLISH is off on this install, so `publish: true` is a request "
                       "rather than an instruction: a post goes live when somebody publishes it on "
                       "/admin/blog")
    if report.get("blocking"):
        return False, (f"{len(report['blocking'])} check(s) must be fixed first. See `checks.blocking`")
    # HELD BY A PERSON. Deliberately checked AFTER the blocking checks, so a held post that also fails
    # a check still reports the check: the hold is a decision about timing and the check is a fact
    # about the post, and hiding the second behind the first would make the post look ready.
    if post.get("held"):
        return False, ("this post is held out of the queue from /admin/blog. It will not publish "
                       "itself until somebody releases it; publishing it by hand still works")
    # FACT-CHECK WARNINGS NO LONGER HOLD A POST BACK. They did, for about an hour, and the proprietor
    # reversed it: cost matters more than perfection, and a post waiting for somebody's evening is a
    # post not published. They are recorded on the row, shown on /admin/blog and logged at publish
    # time, so the claim is still auditable - it is just auditable AFTER rather than before.
    published_today = store.published_count_today()
    if published_today >= AUTOPUBLISH_PER_DAY:
        return False, (f"{published_today} posts have already gone live automatically today, which is "
                       f"the daily limit of {AUTOPUBLISH_PER_DAY}. This one is queued and the oldest "
                       "waiting post goes first tomorrow")
    return True, ""


def publish_queue(limit: int = 20) -> list[dict]:
    """Drafts that would publish themselves, oldest first - the queue, as it stands.

    Oldest first because a post that has waited two days should not be overtaken by one that arrived
    this morning, and because "oldest first" is a rule somebody can predict without reading code.
    """
    waiting = []
    for post in store.drafts():
        if post.get("held"):
            continue            # held out by a person; see may_autopublish
        report = recheck(post)
        if not report["blocking"]:
            waiting.append(post)
    waiting.sort(key=lambda post: post.get("created_at") or 0)
    return waiting[:limit]


def release_due(*, actor: str = "autopublish", limit: int | None = None) -> list[dict]:
    """Publish what the day's allowance permits, oldest first. Returns what went live.

    Called by whatever runs on a timer; safe to call repeatedly, because the allowance is counted from
    what is already published today rather than from anything this function remembers.
    """
    allowance = AUTOPUBLISH_PER_DAY - store.published_count_today()
    if limit is not None:
        allowance = min(allowance, limit)
    done = []
    for post in publish_queue():
        if allowance <= 0:
            break
        try:
            done.append(go_live(post["slug"], actor=actor, reason="autopublish queue")["post"])
            allowance -= 1
        except store.Blocked as exc:                 # it changed under us, or a check now disagrees
            log.info("blog: %s stayed a draft on release (%s)", post["slug"], exc)
    return done


def go_live(slug: str, *, actor: str, reason: str = "") -> dict:
    """Publish a post. Raises `store.Blocked` with the reasons if it still has any.

    Returns {"post", "checks", "indexnow"}. The IndexNow result is handed back rather than logged and
    dropped, so /admin/blog can show the operator what the engines were actually told.
    """
    from app.web import indexnow

    post = store.get(slug)
    if post is None:
        raise KeyError(slug)
    report = recheck(post)
    live = store.publish(slug, report)                 # raises store.Blocked while anything is blocking
    submitted = indexnow.submit([paths.post_path(slug), paths.list_path()],
                               reason=reason or f"blog post published by {actor}")
    # SAID OUT LOUD AT THE MOMENT IT GOES PUBLIC. Warnings no longer hold a post back, so the log is
    # where an unverified claim becomes findable - with the slug, on the line that records the
    # publish, rather than only on a page somebody has to think to open.
    for warning in post.get("fact_check_warnings") or ():
        log.warning("blog: %s published with an unverified claim: %s", slug, warning)
    log.info("blog: %s published by %s; indexnow: %s", slug, actor,
             submitted.get("detail") or f"{submitted.get('sent')} url(s), status {submitted.get('status')}")
    return {"post": live, "checks": report, "indexnow": submitted}


def take_down(slug: str, *, actor: str) -> dict | None:
    """Back to a draft. IndexNow is deliberately NOT called: the protocol is for "this URL changed", and
    what has happened is that a URL stopped existing. The 404 is what tells a crawler that, on its next
    visit, and inviting it back to read a 404 sooner is not a kindness to anybody."""
    post = store.unpublish(slug)
    log.info("blog: %s taken down by %s", slug, actor)
    return post


def preview(post: dict) -> dict:
    """A post rendered for the admin preview: the same HTML the public page would print."""
    html, problems = markdown.render(post.get("body_md") or "")
    return {"html": html, "render_problems": problems,
            "words": markdown.word_count(post.get("body_md") or ""),
            "tool": paths.tool_link(post.get("tool") or ""),
            "categories": [safety.CATEGORIES.get(name, name) for name in (post.get("categories") or ())]}
