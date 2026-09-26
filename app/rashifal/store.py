"""Content store for the 60 rashifal pages + the refresh lease. SQLite (`var/app.db`, app/db.py).

One row per permanent URL, keyed by (rashi slug, period slug). `save_page` replaces the row inside one
BEGIN IMMEDIATE transaction, so a reader sees either the old page or the new one - never a mix, never an
empty page - and the version being replaced is kept in `previous_json` (see `rollback`). The URL is the
key, so re-running the refresh can only ever change content.
"""

import datetime as dt
import json
import os
import socket
import time
import uuid

from app import db

from .periods import PERIOD_SLUGS, RASHI_SLUGS

db.register_schema("rashifal", """
CREATE TABLE IF NOT EXISTS rashifal_pages (
    rashi TEXT NOT NULL,
    period TEXT NOT NULL,
    period_start TEXT NOT NULL,          -- ISO date, first day of the window (IST)
    period_end TEXT NOT NULL,            -- ISO date, last day of the window (IST)
    generated_at TEXT NOT NULL,          -- ISO datetime, UTC
    first_published_at TEXT NOT NULL,    -- ISO datetime, UTC; survives refreshes
    model TEXT NOT NULL,
    brief_hash TEXT NOT NULL,
    languages TEXT NOT NULL,             -- comma-separated codes present in content_json
    content_json TEXT NOT NULL,          -- {"en": {...}, "mr": {...}, "hi": {...}}
    brief_json TEXT NOT NULL,            -- the engine brief the content was written from
    meta_json TEXT NOT NULL,             -- attempts, usage, cost, warnings ...
    previous_json TEXT,                  -- the row this one replaced (same fields, without its own previous)
    PRIMARY KEY (rashi, period)
);
DELETE FROM rashifal_pages WHERE period = '3-months';  -- the MVP's quarterly period was replaced by 'monthly'
CREATE TABLE IF NOT EXISTS rashifal_lease (
    name TEXT PRIMARY KEY,
    holder TEXT NOT NULL,
    expires_at REAL NOT NULL
);
""")

_FIELDS = ("period_start", "period_end", "generated_at", "first_published_at", "model", "brief_hash",
           "languages", "content_json", "brief_json", "meta_json")


def _check_key(rashi: str, period: str) -> None:
    if rashi not in RASHI_SLUGS or period not in PERIOD_SLUGS:
        raise ValueError(f"not a rashifal page: {rashi!r}/{period!r}")


def _page(row) -> dict:
    return {
        "rashi": row["rashi"],
        "period": row["period"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "generated_at": row["generated_at"],
        "first_published_at": row["first_published_at"],
        "model": row["model"],
        "brief_hash": row["brief_hash"],
        "languages": [code for code in row["languages"].split(",") if code],
        "content": json.loads(row["content_json"]),
        "brief": json.loads(row["brief_json"]),
        "meta": json.loads(row["meta_json"]),
        "has_previous": row["previous_json"] is not None,
    }


def get_page(rashi: str, period: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM rashifal_pages WHERE rashi = ? AND period = ?", (rashi, period)).fetchone()
    return _page(row) if row else None


def list_pages() -> dict[tuple[str, str], dict]:
    """Light listing (no content / brief) for index pages, the sitemap and the check script."""
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT rashi, period, period_start, period_end, generated_at, first_published_at, model, brief_hash, languages "
            "FROM rashifal_pages").fetchall()
    return {(row["rashi"], row["period"]): {**dict(row), "languages": [c for c in row["languages"].split(",") if c]}
            for row in rows}


def save_page(rashi: str, period: str, *, period_start: str, period_end: str, generated_at: str, model: str,
              brief_hash: str, content: dict, brief: dict, meta: dict, merge: bool = False,
              merge_run_id: str | None = None) -> list[str]:
    """Atomically replace the page; the replaced version becomes `previous`. Returns the stored languages.

    `merge=True` ADDS the given languages to a stored page that was written from the very same brief (same
    window, same brief hash) instead of replacing it: that is how a language that failed its checks is filled
    in later, and how per-language jobs of one run assemble a page. With `merge_run_id` the stored page must also
    come from that run (a forced run must replace, not top up, what an earlier run wrote). Otherwise: replace.
    """
    _check_key(rashi, period)
    if not content or not all(content.values()):
        raise ValueError("refusing to store empty rashifal content")
    with db.transaction() as conn:
        old = conn.execute("SELECT * FROM rashifal_pages WHERE rashi = ? AND period = ?", (rashi, period)).fetchone()
        mergeable = merge and old and old["period_start"] == period_start and old["brief_hash"] == brief_hash
        if mergeable and merge_run_id is not None:
            mergeable = json.loads(old["meta_json"]).get("run_id") == merge_run_id
        if mergeable:
            merged = {**json.loads(old["content_json"]), **content}
            order = [code for code in ("en", "hi", "mr") if code in merged] + [c for c in merged if c not in ("en", "hi", "mr")]
            merged = {code: merged[code] for code in order}
            old_meta = json.loads(old["meta_json"])
            meta = {**meta, "merged_from": (old_meta.get("merged_from") or []) + [
                {key: old_meta.get(key) for key in ("run_id", "attempts", "usage", "cost_estimate_usd", "languages_written")}]}
            conn.execute(
                "UPDATE rashifal_pages SET generated_at = ?, model = ?, languages = ?, content_json = ?, meta_json = ? "
                "WHERE rashi = ? AND period = ?",
                (generated_at, model, ",".join(merged), json.dumps(merged, ensure_ascii=False),
                 json.dumps(meta, ensure_ascii=False), rashi, period))
            return list(merged)
        previous = json.dumps({name: old[name] for name in _FIELDS}, ensure_ascii=False) if old else None
        values = {
            "period_start": period_start, "period_end": period_end, "generated_at": generated_at,
            "first_published_at": old["first_published_at"] if old else generated_at,
            "model": model, "brief_hash": brief_hash, "languages": ",".join(content),
            "content_json": json.dumps(content, ensure_ascii=False),
            "brief_json": json.dumps(brief, ensure_ascii=False, sort_keys=True),
            "meta_json": json.dumps(meta, ensure_ascii=False),
        }
        conn.execute(
            f"INSERT OR REPLACE INTO rashifal_pages (rashi, period, {', '.join(_FIELDS)}, previous_json) "
            f"VALUES (?, ?, {', '.join('?' for _ in _FIELDS)}, ?)",
            (rashi, period, *(values[name] for name in _FIELDS), previous),
        )
    return list(content)


def hub_rows(period: str) -> dict[str, dict]:
    """{rashi: {period_start, period_end, generated_at, languages, summaries{lang}, headlines{lang}}} for a hub page."""
    if period not in PERIOD_SLUGS:
        raise ValueError(f"unknown period {period!r}")
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT rashi, period_start, period_end, generated_at, languages, content_json "
                            "FROM rashifal_pages WHERE period = ?", (period,)).fetchall()
    result = {}
    for row in rows:
        content = json.loads(row["content_json"])
        result[row["rashi"]] = {
            "period_start": row["period_start"], "period_end": row["period_end"], "generated_at": row["generated_at"],
            "languages": [code for code in row["languages"].split(",") if code],
            "summaries": {code: page.get("summary", "") for code, page in content.items()},
            "headlines": {code: page.get("headline", "") for code, page in content.items()},
        }
    return result


def rollback(rashi: str, period: str) -> bool:
    """Put the previous version back (operator's undo for a page that reads badly). False if there is none."""
    _check_key(rashi, period)
    with db.transaction() as conn:
        row = conn.execute("SELECT previous_json FROM rashifal_pages WHERE rashi = ? AND period = ?",
                           (rashi, period)).fetchone()
        if not row or not row["previous_json"]:
            return False
        old = json.loads(row["previous_json"])
        conn.execute(
            f"UPDATE rashifal_pages SET {', '.join(f'{name} = ?' for name in _FIELDS)}, previous_json = NULL "
            "WHERE rashi = ? AND period = ?",
            (*(old[name] for name in _FIELDS), rashi, period),
        )
    return True


# ---- lease: one refresh at a time, across uvicorn workers, the CLI and systemd timers -------------


def new_holder() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def acquire_lease(name: str, holder: str, ttl_seconds: float, now: float | None = None) -> bool:
    """True if `holder` now owns the lease: it was free, expired, or already ours (then it is extended)."""
    now = time.time() if now is None else now
    with db.transaction() as conn:
        row = conn.execute("SELECT holder, expires_at FROM rashifal_lease WHERE name = ?", (name,)).fetchone()
        if row and row["holder"] != holder and row["expires_at"] > now:
            return False
        conn.execute("INSERT OR REPLACE INTO rashifal_lease (name, holder, expires_at) VALUES (?, ?, ?)",
                     (name, holder, now + ttl_seconds))
    return True


def release_lease(name: str, holder: str) -> None:
    with db.transaction() as conn:
        conn.execute("DELETE FROM rashifal_lease WHERE name = ? AND holder = ?", (name, holder))


def lease_info(name: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT holder, expires_at FROM rashifal_lease WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    return {"holder": row["holder"],
            "expires_at": dt.datetime.fromtimestamp(row["expires_at"], dt.timezone.utc).isoformat(timespec="seconds")}
