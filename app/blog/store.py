"""The `blog_posts` and `blog_images` tables, and the draft -> published lifecycle.

TWO STATES AND ONE DOOR. A post is `draft` or `published`; it arrives as a draft, and the ONLY code that
writes `published` is `publish()` below, which refuses to do it while the post has a blocking problem
recorded against it. The API cannot set the state directly - it hands this module a checked post and the
module decides - so "posts arrive as drafts" is a property of the schema's one writer rather than a rule
every caller has to remember.

WHAT IS KEPT AND WHY. The body is stored exactly as it arrived, in Markdown, and rendered on the way out
(`app/blog/markdown.py`). Storing the rendered HTML instead would mean a fix to the renderer - a new
`rel`, a tightened link rule - reaching only the posts written after it, which is the shape of defect
this codebase has been bitten by elsewhere: the thing you cannot re-run is the thing that stays wrong.
The check report is stored with the post, so /admin/blog can say WHY a draft is a draft without
re-running anything, and so a refusal survives a restart.

NO PERSONAL DATA IN HERE. `author` is a byline the writer sends, and docs/BLOG_API.md says plainly that
it must be the publication's own name and never a private individual's. There is no reader-facing table
in this package at all.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import time

from app import db

from . import paths, safety

log = logging.getLogger(__name__)
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

DRAFT = "draft"
PUBLISHED = "published"

db.register_schema("blog", """
CREATE TABLE IF NOT EXISTS blog_posts (
    slug         TEXT PRIMARY KEY,         -- also the URL segment; app/blog/paths.py owns its shape
    -- WHICH TREE THE POST LIVES IN. Default 'en' so every post written before this column existed is
    -- the English one it was, with no backfill and no guess.
    language     TEXT NOT NULL DEFAULT 'en',
    -- THE POST THIS ONE TRANSLATES, by slug, or NULL for an original. It is what makes hreflang
    -- possible: two posts are alternates of each other when they share a group, and a group is "this
    -- slug plus everything pointing at it". A translation keeps its OWN slug, because a Hindi URL
    -- reading like an English one helps nobody who types it.
    translation_of TEXT,
    key_points   TEXT,                     -- JSON list of 3-5 short strings, or NULL
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,            -- the page's meta description, 50-230 characters
    body_md      TEXT NOT NULL,            -- Markdown, exactly as it arrived. Never HTML
    categories   TEXT NOT NULL DEFAULT '', -- comma-separated keys from app/blog/safety.CATEGORIES
    tool         TEXT NOT NULL,            -- the registry key of the tool this post is about
    hero_image   TEXT,                     -- a blog_images.id, or NULL
    author       TEXT NOT NULL DEFAULT '', -- a byline, never a private individual
    source       TEXT NOT NULL DEFAULT '', -- which caller sent it ("api" / "admin")
    status       TEXT NOT NULL DEFAULT 'draft',   -- draft | published. Only publish() writes 'published'
    blocking     TEXT NOT NULL DEFAULT '[]',      -- why it cannot be published, as JSON. [] = it can
    warnings     TEXT NOT NULL DEFAULT '[]',
    checked_at   REAL,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    published_at REAL                      -- first time it went live; NULL for a post that never has
);
CREATE INDEX IF NOT EXISTS blog_posts_status ON blog_posts(status, published_at);

CREATE TABLE IF NOT EXISTS blog_images (
    id         TEXT PRIMARY KEY,           -- our own hex id. A caller's file name NEVER reaches the disk
    media_type TEXT NOT NULL,              -- sniffed from the bytes, not from the upload's own claim
    extension  TEXT NOT NULL,
    bytes_len  INTEGER NOT NULL,
    sha256     TEXT NOT NULL,
    sent_as    TEXT NOT NULL DEFAULT '',   -- the name the caller used, kept for the admin page only
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS blog_images_sha ON blog_images(sha256);
""")

# COLUMNS FOR A TABLE THAT ALREADY EXISTS. CREATE TABLE IF NOT EXISTS does nothing to a database that
# already has blog_posts, so the two columns above would be in the DDL and absent from every database
# written before them - which is exactly how this failed the first time it was read.
db.register_columns("blog_posts", {
    "language": "TEXT NOT NULL DEFAULT 'en'",
    "translation_of": "TEXT",
    # Three to five short takeaways, as JSON. OPTIONAL: a post without them shows the contents box
    # built from its own headings instead, which is a different and more modest claim.
    "key_points": "TEXT",
    # What the WRITER could not verify, as JSON. Not our checks - theirs. A post arrives with these
    # attached and they are the one thing that stops it publishing itself, because a claim nobody has
    # stood behind is exactly what a human should read before it goes out under our name.
    "fact_check_warnings": "TEXT",
    # Every repair made on the way in, as JSON: [{"what", "before", "after", "by"}]. Kept so the
    # admin page can show what was changed rather than only what arrived.
    "fixes": "TEXT",
    # HELD BACK FROM THE AUTOPUBLISH QUEUE, by a person, deliberately. Not a check and not a verdict
    # about the post: the checks say whether it MAY publish itself, and this says whether we want it
    # to yet. A held draft is still publishable by hand from /admin/blog, because holding it is about
    # the queue running unattended, not about doubting the post.
    "held": "INTEGER NOT NULL DEFAULT 0",
    "held_at": "REAL",
    "held_by": "TEXT",
})



class StillPublished(Exception):
    """Raised when something that is only true of drafts is asked of a published post."""


def set_held(slug: str, held: bool, *, actor: str) -> dict | None:
    """Hold a draft out of the autopublish queue, or let it back in.

    WHO AND WHEN ARE STORED, not just the flag. "Why is this one not going out?" is a question asked
    days later, usually by the person who held it, and a bare boolean cannot answer it.
    """
    import time

    with db.transaction() as conn:
        row = conn.execute("SELECT status FROM blog_posts WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE blog_posts SET held = ?, held_at = ?, held_by = ? WHERE slug = ?",
            (1 if held else 0, time.time() if held else None, actor if held else None, slug))
    return get(slug)


def delete(slug: str) -> dict | None:
    """Delete a DRAFT, returning what was deleted so the caller can record it.

    DRAFTS ONLY, for the reason the edit route already gives: a published post is a URL somebody may
    have shared and a page a crawler has read. Deleting one would make it 404 with no trail and no way
    back. Take it down first - that is one click and it leaves a record.

    Any post naming this one as its original keeps its own text and loses the link, rather than being
    deleted along with it. A translation is somebody's work too, and cascading from a slug would be a
    surprising amount of deleting for one button.
    """
    post = get(slug)
    if post is None:
        return None
    if post["is_published"]:
        raise StillPublished(slug)
    with db.transaction() as conn:
        conn.execute("UPDATE blog_posts SET translation_of = NULL WHERE translation_of = ?", (slug,))
        conn.execute("DELETE FROM blog_posts WHERE slug = ?", (slug,))
    return post


def posts_translating(slug: str) -> list[dict]:
    """Posts naming this one as their original, published or not - what a delete would unlink.

    NOT `translations_of`, which already exists below and answers a different question: that one is
    for hreflang and returns only PUBLISHED alternates of a post. This one has to see drafts, because
    the thing being deleted is a draft and so are the posts most likely to point at it. The first
    version of this was called `translations_of` too and quietly shadowed the other; had the two been
    defined the other way round, hreflang would have broken for every translated post on the site.
    """
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM blog_posts WHERE translation_of = ? ORDER BY language",
                            (slug,)).fetchall()
    return [_row(row) for row in rows]


# ---- reads -------------------------------------------------------------------------------------------


def get(slug: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM blog_posts WHERE slug = ?", (slug,)).fetchone()
    return _row(row) if row else None


def all_posts(status: str | None = None) -> list[dict]:
    """Every post, drafts first and then by when it was last touched - the order /admin/blog wants."""
    sql = "SELECT * FROM blog_posts"
    args: tuple = ()
    if status:
        sql += " WHERE status = ?"
        args = (status,)
    sql += " ORDER BY CASE status WHEN 'draft' THEN 0 ELSE 1 END, updated_at DESC"
    with db.transaction(write=False) as conn:
        return [_row(row) for row in conn.execute(sql, args)]


def published(language: str | None = None) -> list[dict]:
    """The live posts, newest first. What a list page shows and what its Blog JSON-LD describes.

    `language` narrows it to one tree. A list page passes its own: a Hindi index showing English posts
    would be a list of pages that reader cannot read. None means every tree, which is what the admin
    and the link check want.
    """
    with db.transaction(write=False) as conn:
        if language is None:
            rows = conn.execute(
                "SELECT * FROM blog_posts WHERE status = ? ORDER BY published_at DESC, created_at DESC",
                (PUBLISHED,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM blog_posts WHERE status = ? AND COALESCE(language, 'en') = ? "
                "ORDER BY published_at DESC, created_at DESC", (PUBLISHED, language)).fetchall()
    return [_row(row) for row in rows]


def translations_of(post: dict) -> list[dict]:
    """The published posts that are alternates of this one: {language, slug, path, title}.

    A TRANSLATION GROUP IS "THIS SLUG PLUS EVERYTHING POINTING AT IT". The original has
    `translation_of` NULL and each translation names the original's slug, so the group is found from
    either end without a second table. Two posts are alternates because they SAY they are - never
    because they happen to sit in different trees with similar titles.

    Drafts are left out: an hreflang pointing at a 404 is worse than no hreflang.
    """
    from app.blog import paths

    root = post.get("translation_of") or post["slug"]
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT slug, language, title FROM blog_posts WHERE status = ? "
            "AND (slug = ? OR translation_of = ?) ORDER BY language", (PUBLISHED, root, root)).fetchall()
    return [{"language": row["language"] or "en", "slug": row["slug"], "title": row["title"],
             "path": paths.post_path(row["slug"], row["language"] or "en")}
            for row in rows if row["slug"] != post["slug"]]


def drafts() -> list[dict]:
    """Every post that is not published, oldest first."""
    return sorted(all_posts("draft"), key=lambda post: post.get("created_at") or 0)


def published_count_today() -> int:
    """How many posts went live today, IST.

    COUNTED FROM THE ROWS, not from a tally this module keeps. A counter would have to survive a
    restart, a manual publish from /admin/blog and a post taken back down, and it would be wrong
    after any of them; the published_at timestamps already know.
    """
    today = _ist_date(time.time())
    with db.transaction(write=False) as conn:
        stamps = conn.execute(
            "SELECT published_at FROM blog_posts WHERE status = ? AND published_at IS NOT NULL",
            (PUBLISHED,)).fetchall()
    # Compared as IST CALENDAR DATES rather than with a timestamp range, because that is what
    # `_ist_date` already means everywhere else here and a range would be a second definition of
    # "today" in the same file.
    return sum(1 for row in stamps if _ist_date(row["published_at"]) == today)


def published_on(day: str) -> list[dict]:
    """Posts published on one IST day, for the morning digest."""
    return [post for post in all_posts(PUBLISHED)
            if post.get("published_at") and _ist_date(post["published_at"]) == day]


def slug_status() -> dict[str, str]:
    """{slug: status} - what the link check needs to tell a 404 from a link to a draft."""
    with db.transaction(write=False) as conn:
        return {row["slug"]: row["status"] for row in conn.execute("SELECT slug, status FROM blog_posts")}


def taken_titles() -> dict[str, str]:
    """{normalised title or summary: the slug using it}, for the site-wide uniqueness check."""
    taken: dict[str, str] = {}
    with db.transaction(write=False) as conn:
        for row in conn.execute("SELECT slug, title, summary FROM blog_posts"):
            for value in (row["title"], row["summary"]):
                taken[safety._normalise(value)] = row["slug"]  # noqa: SLF001 - one normaliser, one place
    return taken


def published_slugs() -> tuple[tuple[str, str], ...]:
    """(slug, language) for every live post, for the sitemap - and the one function here that may run at
    import time.

    IT MUST NEVER CREATE THE DATABASE AND MUST NEVER RAISE. `app/web/i18n.py` builds its reverse lookup
    table at import, by walking `all_pages()`, so the moment the blog joins that walk this function runs
    during `import app.main` - before any test has pointed `APP_DB` at a throwaway file, and on a fresh
    box before the database exists at all. The root `conftest.py` in this repo exists because a scratch
    script once wrote a live order row into the real `var/app.db`; a sitemap helper that silently created
    and migrated that file at import would be the same mistake wearing a different hat.

    So this opens its own READ-ONLY connection with `mode=ro`, which fails rather than creating the file
    and cannot write a byte - deliberately not `db.transaction`, whose `_connect` applies every
    registered schema to whatever database it is handed. It is the only read in this package that does
    not go through `app/db.py`, and that is the reason.
    """
    path = db.db_path()
    try:
        if not path.exists():
            return ()
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            # `language` may not exist yet on a database written before the column did, and this runs
            # at import on whatever file it finds - so it is read defensively and defaults to English,
            # which is what every row predating the column is.
            try:
                rows = conn.execute("SELECT slug, language FROM blog_posts WHERE status = ? "
                                    "ORDER BY published_at DESC, created_at DESC",
                                    (PUBLISHED,)).fetchall()
            except sqlite3.OperationalError:
                rows = [(row[0], "en") for row in conn.execute(
                    "SELECT slug FROM blog_posts WHERE status = ? "
                    "ORDER BY published_at DESC, created_at DESC", (PUBLISHED,)).fetchall()]
        finally:
            conn.close()
        return tuple((row[0], row[1] or "en") for row in rows)
    except Exception as exc:  # noqa: BLE001 - a sitemap must never be the thing that fails to import
        log.warning("blog: published_slugs() could not read %s (%s); the sitemap lists no posts", path, exc)
        return ()


# ---- writes ------------------------------------------------------------------------------------------


def save(post: dict, report: dict, *, source: str = "api") -> dict:
    """Create or replace a post from a checked submission. Returns the stored row.

    `report` is `safety.check`'s result. THIS FUNCTION CANNOT PUBLISH ANYTHING. A new post is a draft,
    whatever the caller asked for and whatever the flag says; `publish()` below is the only writer of
    `status = 'published'`, and `app/blog/publishing.py` is the only caller of it. There is deliberately
    no `publish_now` argument here - an argument that could make a save go live is an argument somebody
    will eventually pass by accident.

    A post that is ALREADY published and is updated into a blocking problem is NOT taken down. It is
    marked and left live, because a live URL vanishing is the more damaging of the two failures and the
    admin page shows the problem in red the moment it is opened. Taking it down is a decision somebody
    makes on /admin/blog with the reason in front of them.
    """
    now = time.time()
    blocking = list(report.get("blocking") or ())
    existing = get(post["slug"])
    status = PUBLISHED if (existing and existing["status"] == PUBLISHED) else DRAFT
    published_at = (existing or {}).get("published_at")
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO blog_posts (slug, title, summary, body_md, categories, tool, hero_image,
                                       author, source, status, blocking, warnings, checked_at,
                                       created_at, updated_at, published_at, language, translation_of,
                                       key_points, fact_check_warnings, fixes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                   title = excluded.title, summary = excluded.summary, body_md = excluded.body_md,
                   categories = excluded.categories, tool = excluded.tool,
                   hero_image = excluded.hero_image, author = excluded.author,
                   source = excluded.source, status = excluded.status,
                   blocking = excluded.blocking, warnings = excluded.warnings,
                   checked_at = excluded.checked_at, updated_at = excluded.updated_at,
                   published_at = excluded.published_at,
                   -- A post does not change tree on an update unless the caller says so. An edit that
                   -- omitted the field would otherwise silently move a Hindi post into /blog.
                   language = excluded.language, translation_of = excluded.translation_of,
                   key_points = excluded.key_points,
                   fact_check_warnings = excluded.fact_check_warnings,
                   fixes = excluded.fixes""",
            (post["slug"], post["title"], post["summary"], post["body_md"],
             ",".join(post.get("categories") or ()), post["tool"], post.get("hero_image"),
             post.get("author") or "", source, status,
             json.dumps(blocking), json.dumps(list(report.get("warnings") or ())), now,
             (existing or {}).get("created_at") or now, now, published_at,
             post.get("language") or (existing or {}).get("language") or "en",
             post.get("translation_of") or (existing or {}).get("translation_of"),
             _points_json(post, existing),
             _list_json(post, existing, "fact_check_warnings"),
             _list_json(post, existing, "fixes")))
    return get(post["slug"])  # read back, so a caller can never disagree with the table


def record_checks(slug: str, report: dict) -> None:
    """Re-run results, written against an existing post without touching its prose or its state."""
    with db.transaction() as conn:
        conn.execute("UPDATE blog_posts SET blocking = ?, warnings = ?, checked_at = ? WHERE slug = ?",
                     (json.dumps(list(report.get("blocking") or ())),
                      json.dumps(list(report.get("warnings") or ())), time.time(), slug))


def publish(slug: str, report: dict) -> dict:
    """Put a post live. THE ONLY WRITER OF `status = 'published'`, and it refuses a blocked post.

    The check report is passed in rather than read from the row on purpose: whoever publishes has just
    re-run the checks against the body as it stands now, and a stored report from an earlier submission
    is not evidence about the text that is about to go public.
    """
    blocking = list(report.get("blocking") or ())
    record_checks(slug, report)
    if blocking:
        raise Blocked(blocking)
    now = time.time()
    with db.transaction() as conn:
        # COALESCE: `published_at` is the FIRST time this went live. A post taken down and put back is
        # not a new post, and its Article dateline must not move - a date that walks backwards and
        # forwards in a search result is a reason not to trust the page.
        conn.execute("UPDATE blog_posts SET status = ?, published_at = COALESCE(published_at, ?), "
                     "updated_at = ? WHERE slug = ?", (PUBLISHED, now, now, slug))
    return get(slug)


def unpublish(slug: str) -> dict | None:
    """Back to a draft. `published_at` is kept: see the note in `publish`."""
    with db.transaction() as conn:
        conn.execute("UPDATE blog_posts SET status = ?, updated_at = ? WHERE slug = ?",
                     (DRAFT, time.time(), slug))
    return get(slug)


class Blocked(Exception):
    """A publish refused because the post still has blocking problems."""

    def __init__(self, blocking: list[str]):
        super().__init__("; ".join(blocking)[:400])
        self.blocking = blocking


# ---- images ------------------------------------------------------------------------------------------


def add_image(image_id: str, *, media_type: str, extension: str, bytes_len: int, sha256: str,
              sent_as: str) -> dict:
    with db.transaction() as conn:
        conn.execute("INSERT INTO blog_images (id, media_type, extension, bytes_len, sha256, sent_as, "
                     "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (image_id, media_type, extension, bytes_len, sha256, sent_as, time.time()))
    return image(image_id)


def image(image_id: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM blog_images WHERE id = ?", (image_id,)).fetchone()
    return dict(row) if row else None


def image_count() -> int:
    with db.transaction(write=False) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM blog_images").fetchone()[0])


def image_by_digest(sha256: str) -> dict | None:
    """The same bytes uploaded twice are the same image: a retrying writer does not fill var/."""
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM blog_images WHERE sha256 = ? ORDER BY created_at LIMIT 1",
                           (sha256,)).fetchone()
    return dict(row) if row else None


# ---- row view ----------------------------------------------------------------------------------------


def _list_json(post: dict, existing: dict | None, field: str) -> str | None:
    """A JSON list column, from the submission or from what is already stored.

    ALWAYS A STRING OR NONE, for the reason `_points_json` spells out below: `_row` turns these back
    into lists on the way out, and SQLite refuses to bind one.
    """
    value = post.get(field)
    if value:
        return json.dumps(list(value), ensure_ascii=False)
    kept = (existing or {}).get(field)
    if not kept:
        return None
    return kept if isinstance(kept, str) else json.dumps(list(kept), ensure_ascii=False)


def _points_json(post: dict, existing: dict | None) -> str | None:
    """key_points as JSON for the column, from the submission or from what is already stored.

    ALWAYS A STRING OR NONE. `_row` turns the column back into a LIST on the way out, so a post read
    from the database and saved again carried a list here - and SQLite refuses to bind one. The admin
    editor hit it on every save of a draft with no key points, which is most of them.
    """
    if post.get("key_points"):
        return json.dumps(list(post["key_points"]), ensure_ascii=False)
    kept = (existing or {}).get("key_points")
    if not kept:
        return None
    return kept if isinstance(kept, str) else json.dumps(list(kept), ensure_ascii=False)


def _row(row) -> dict:
    post = dict(row)
    post["categories"] = [name for name in (post.get("categories") or "").split(",") if name]
    post["blocking"] = _json_list(post.get("blocking"))
    post["warnings"] = _json_list(post.get("warnings"))
    post["path"] = paths.post_path(post["slug"], post.get("language") or paths.LANG)
    post["key_points"] = _json_list(post.get("key_points"))
    post["fact_check_warnings"] = _json_list(post.get("fact_check_warnings"))
    post["fixes"] = _json_list(post.get("fixes"), strings=False)
    post["is_published"] = post["status"] == PUBLISHED
    post["is_held"] = bool(post.get("held"))
    post["held_on"] = _ist_date(post.get("held_at"))
    post["published_on"] = _ist_date(post.get("published_at"))
    post["updated_on"] = _ist_date(post.get("updated_at"))
    post["created_on"] = _ist_date(post.get("created_at"))
    return post


def _json_list(value, *, strings: bool = True) -> list:
    """A JSON list column, decoded. `strings=False` keeps the items as they were stored.

    The default coerces to str because the two oldest callers hold lists of sentences and a number
    where a sentence belongs is a bug worth flattening. `fixes` holds OBJECTS - what was changed,
    before, after, by whom - and coercing those gave a list of Python reprs that rendered as
    "{'what': 'phrase', ...}" on the admin page.
    """
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed] if strings else parsed


def _ist_date(stamp) -> str:
    """The IST calendar date of a moment, as ISO. Everything dated on this site is dated in IST."""
    if stamp is None:
        return ""
    return dt.datetime.fromtimestamp(float(stamp), dt.timezone.utc).astimezone(IST).date().isoformat()


def iso_moment(stamp) -> str:
    """An IST timestamp as ISO-8601 with its offset, for the Article JSON-LD and the sitemap."""
    if stamp is None:
        return ""
    return dt.datetime.fromtimestamp(float(stamp), dt.timezone.utc).astimezone(IST)\
        .isoformat(timespec="seconds")
