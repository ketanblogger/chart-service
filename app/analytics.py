"""What the site is doing, counted - without keeping anything that identifies a person.

TWO TABLES AND ONE RULE. `site_visits` answers "how many people, on what pages, in what language" and
`site_events` answers "what did the software do, did it work, what did it cost". The rule is that neither
holds anything a person could be picked out of later: no raw IP, no user agent, no query strings, and no
chat text ever.

A VISITOR IS A DAILY SALTED HASH of IP and user agent. The salt is derived from the day, so the same
browser is one visitor within a day and an unrelated one tomorrow - which is what makes "unique visitors"
a useful number and a useless identifier. There is nothing to reverse: the IP is hashed with a key this
process holds and then discarded.

ADMIN USAGE IS RECORDED AND SEPARATED, never dropped. An administrator with no limits would otherwise
quietly inflate every number on their own dashboard; `is_admin` is on every row so the dashboard can show
both and default to neither being mixed in.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import time

from app import db

log = logging.getLogger(__name__)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Registered at import, like every other table here: `db` runs the DDL once per database and nothing has
# to remember to call an `_ensure()` first. The first version did have one, and `executescript` issues its
# own COMMIT - inside `db.transaction()` that leaves no transaction to commit and the write fails.
db.register_schema("analytics", """
CREATE TABLE IF NOT EXISTS site_visits (
    id           INTEGER PRIMARY KEY,
    ts           REAL NOT NULL,
    day          TEXT NOT NULL,          -- IST date, so a "day" means what a person in India means
    visitor      TEXT NOT NULL,          -- daily-salted hash of IP + user agent; NOT an identifier
    path         TEXT NOT NULL,          -- path only, never the query string
    lang         TEXT NOT NULL DEFAULT '',
    is_admin     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS site_visits_day ON site_visits(day);
CREATE INDEX IF NOT EXISTS site_visits_visitor ON site_visits(day, visitor);

CREATE TABLE IF NOT EXISTS site_events (
    id           INTEGER PRIMARY KEY,
    ts           REAL NOT NULL,
    day          TEXT NOT NULL,
    account_id   TEXT NOT NULL DEFAULT '',   -- the hashed account id, never an address
    is_admin     INTEGER NOT NULL DEFAULT 0,
    feature      TEXT NOT NULL,              -- kundali | muhurta | chat | report | auth | error ...
    action       TEXT NOT NULL,              -- search | pdf | question | sold | refund | sign-in ...
    ok           INTEGER NOT NULL DEFAULT 1,
    cost_inr     REAL NOT NULL DEFAULT 0,    -- what WE paid: model tokens, render time, e-mail
    revenue_inr  REAL NOT NULL DEFAULT 0,    -- what the customer paid, for the margin
    lang         TEXT NOT NULL DEFAULT '',
    detail       TEXT NOT NULL DEFAULT ''    -- short and structural; NEVER anybody's words
);
CREATE INDEX IF NOT EXISTS site_events_day ON site_events(day);
CREATE INDEX IF NOT EXISTS site_events_feature ON site_events(day, feature);
""")

# A request that is plainly a crawler is not a visitor. Deliberately a short, boring list: the cost of
# missing one is a slightly high number, and the cost of an over-eager pattern is excluding real readers.
_BOT = re.compile(
    r"bot|crawler|spider|crawl|slurp|bingpreview|facebookexternalhit|whatsapp|telegram|curl|wget|"
    r"python-requests|httpx|headless|lighthouse|pingdom|uptime|monitor",
    re.I,
)

# Paths that are not pages. Counting these as page views makes every number wrong in the same direction.
_NOT_A_PAGE = ("/static/", "/api/", "/health", "/favicon", "/apple-touch-icon", "/site.webmanifest",
               "/robots.txt", "/sitemap", "/admin")


def ist_day(stamp: float | None = None) -> str:
    moment = dt.datetime.fromtimestamp(stamp if stamp is not None else time.time(), dt.timezone.utc)
    return moment.astimezone(IST).date().isoformat()


def _salt(day: str) -> bytes:
    """Today's salt, derived rather than stored: nothing on disk can turn a hash back into an address."""
    secret = (os.getenv("SESSION_SECRET") or os.getenv("SECRET_KEY") or "rashikundli-dev").encode()
    return hmac.new(secret, f"visitor-salt:{day}".encode(), hashlib.sha256).digest()


def visitor_hash(ip: str, user_agent: str, day: str | None = None) -> str:
    """A visitor, for ONE day. Tomorrow the same browser hashes to something unrelated, by design."""
    day = day or ist_day()
    raw = f"{ip or ''}|{(user_agent or '')[:200]}".encode()
    return hmac.new(_salt(day), raw, hashlib.sha256).hexdigest()[:32]


def is_bot(user_agent: str | None) -> bool:
    return bool(_BOT.search(user_agent or "")) if user_agent else True   # no UA at all is not a reader


def is_page(path: str) -> bool:
    return bool(path) and not path.startswith(_NOT_A_PAGE)


def record_visit(*, ip: str, user_agent: str, path: str, lang: str = "", is_admin: bool = False,
                 stamp: float | None = None) -> bool:
    """One page view. -> whether it was counted. Never raises: analytics must not break a page."""
    try:
        if not is_page(path) or is_bot(user_agent):
            return False
        now = stamp if stamp is not None else time.time()
        day = ist_day(now)
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO site_visits (ts, day, visitor, path, lang, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
                (now, day, visitor_hash(ip, user_agent, day), path[:200], lang[:5], 1 if is_admin else 0))
        return True
    except Exception:  # noqa: BLE001 - counting is never a reason to fail a request
        log.exception("could not record a visit")
        return False


def record_event(feature: str, action: str, *, account_id: str = "", is_admin: bool = False,
                 ok: bool = True, cost_inr: float = 0.0, revenue_inr: float = 0.0, lang: str = "",
                 detail: str = "", stamp: float | None = None) -> bool:
    """One thing the software did. `detail` is structural - a purpose, a product id - and never prose."""
    try:
        now = stamp if stamp is not None else time.time()
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO site_events (ts, day, account_id, is_admin, feature, action, ok, cost_inr, "
                "revenue_inr, lang, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, ist_day(now), (account_id or "")[:64], 1 if is_admin else 0, feature[:32],
                 action[:32], 1 if ok else 0, float(cost_inr), float(revenue_inr), (lang or "")[:5],
                 (detail or "")[:200]))
        return True
    except Exception:  # noqa: BLE001
        log.exception("could not record an event")
        return False


# ---------------------------------------------------------------- reading it back


def _window(days: int, now: float | None = None) -> tuple[str, str]:
    end = dt.date.fromisoformat(ist_day(now))
    start = end - dt.timedelta(days=max(1, days) - 1)
    return start.isoformat(), end.isoformat()


def summary(days: int = 7, *, include_admin: bool = False, now: float | None = None) -> dict:
    """Everything the dashboard shows, for a window of days. Admin rows are OUT unless asked for."""
    start, end = _window(days, now)
    admin_clause = "" if include_admin else " AND is_admin = 0"
    with db.transaction(write=False) as conn:
        visits = conn.execute(
            f"SELECT COUNT(*) AS views, COUNT(DISTINCT visitor) AS people FROM site_visits "
            f"WHERE day BETWEEN ? AND ?{admin_clause}", (start, end)).fetchone()
        per_day = conn.execute(
            f"SELECT day, COUNT(*) AS views, COUNT(DISTINCT visitor) AS people FROM site_visits "
            f"WHERE day BETWEEN ? AND ?{admin_clause} GROUP BY day ORDER BY day", (start, end)).fetchall()
        top_pages = conn.execute(
            f"SELECT path, COUNT(*) AS views FROM site_visits WHERE day BETWEEN ? AND ?{admin_clause} "
            f"GROUP BY path ORDER BY views DESC LIMIT 15", (start, end)).fetchall()
        languages = conn.execute(
            f"SELECT lang, COUNT(*) AS views FROM site_visits WHERE day BETWEEN ? AND ?{admin_clause} "
            f"GROUP BY lang ORDER BY views DESC", (start, end)).fetchall()
        features = conn.execute(
            f"SELECT feature, action, COUNT(*) AS n, SUM(ok) AS ok, ROUND(SUM(cost_inr), 2) AS cost, "
            f"ROUND(SUM(revenue_inr), 2) AS revenue FROM site_events WHERE day BETWEEN ? AND ?{admin_clause} "
            f"GROUP BY feature, action ORDER BY n DESC", (start, end)).fetchall()
        money = conn.execute(
            f"SELECT ROUND(SUM(cost_inr), 2) AS cost, ROUND(SUM(revenue_inr), 2) AS revenue "
            f"FROM site_events WHERE day BETWEEN ? AND ?{admin_clause}", (start, end)).fetchone()
        cost_by_day = conn.execute(
            f"SELECT day, ROUND(SUM(cost_inr), 2) AS cost, ROUND(SUM(revenue_inr), 2) AS revenue "
            f"FROM site_events WHERE day BETWEEN ? AND ?{admin_clause} GROUP BY day ORDER BY day",
            (start, end)).fetchall()
        # TOP USERS BY COST, by account id. The dashboard masks the address; this does not even have one.
        top_users = conn.execute(
            f"SELECT account_id, COUNT(*) AS n, ROUND(SUM(cost_inr), 2) AS cost FROM site_events "
            f"WHERE day BETWEEN ? AND ? AND account_id != ''{admin_clause} "
            f"GROUP BY account_id ORDER BY cost DESC LIMIT 10", (start, end)).fetchall()
        errors = conn.execute(
            f"SELECT feature, action, detail, COUNT(*) AS n FROM site_events "
            f"WHERE day BETWEEN ? AND ? AND ok = 0{admin_clause} "
            f"GROUP BY feature, action, detail ORDER BY n DESC LIMIT 20", (start, end)).fetchall()
        admin_rows = conn.execute(
            "SELECT COUNT(*) AS n FROM site_events WHERE day BETWEEN ? AND ? AND is_admin = 1",
            (start, end)).fetchone()

    cost = float(money["cost"] or 0)
    revenue = float(money["revenue"] or 0)
    return {
        "from": start, "to": end, "days": days, "include_admin": include_admin,
        "views": visits["views"] or 0, "visitors": visits["people"] or 0,
        "per_day": [dict(row) for row in per_day],
        "top_pages": [dict(row) for row in top_pages],
        "languages": [dict(row) for row in languages],
        "features": [dict(row) for row in features],
        "cost_inr": round(cost, 2), "revenue_inr": round(revenue, 2),
        "margin_inr": round(revenue - cost, 2),
        "cost_by_day": [dict(row) for row in cost_by_day],
        "top_users": [dict(row) for row in top_users],
        "errors": [dict(row) for row in errors],
        # Shown as its own line so an administrator can see what their own use added, and that it was not
        # counted in anything above.
        "admin_events_excluded": (admin_rows["n"] or 0) if not include_admin else 0,
    }


def recent_events(limit: int = 100, *, include_admin: bool = True) -> list[dict]:
    """The event log. Who (account id), when, what, cost, ok - and never a word anybody wrote."""
    clause = "" if include_admin else " WHERE is_admin = 0"
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            f"SELECT ts, account_id, is_admin, feature, action, ok, cost_inr, revenue_inr, lang, detail "
            f"FROM site_events{clause} ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
    return [dict(row) for row in rows]


def mask_account(account_id: str) -> str:
    """An account id is already a hash; this shortens it for a table rather than revealing anything."""
    return f"{account_id[:8]}…" if account_id else "—"


def as_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
