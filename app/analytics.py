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
from urllib.parse import parse_qsl, urlparse
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
    r"python-requests|httpx|headless|lighthouse|pingdom|uptime|monitor|"
    # Libraries, not browsers. Every one of these turned up in the agent column at some point, and none
    # of them is a person reading a horoscope.
    r"go-http-client|okhttp|java/|apache-httpclient|axios|node-fetch|got/|libwww|scrapy|httpie|"
    r"phantomjs|puppeteer|playwright|selenium|webdriver|dataprovider|feedfetcher|preview",
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


db.register_columns("site_visits", {
    # Where this arrival came from: one word from a fixed list, and the campaign tag if the link had one.
    "source": "TEXT NOT NULL DEFAULT ''",
    "campaign": "TEXT NOT NULL DEFAULT ''",
    # Did a real browser run the page? 0 until it says so. This is the signal that separates 500 counted
    # visitors from 7 search clicks, and nothing is ever refused because of it.
    "js": "INTEGER NOT NULL DEFAULT 0",
    "suspect": "INTEGER NOT NULL DEFAULT 0",
    # Which section of our OWN site sent them to this page. The section, never the page.
    "via": "TEXT NOT NULL DEFAULT ''",
})

# OURS OR A CUSTOMER'S. An admin chat and an admin report consume real AI and cost real money, so they
# are never hidden - they are shown as their own line. What they are not is customer usage, and counting
# them as such makes every per-customer figure wrong. NULL means not yet classified.
db.register_columns("site_events", {"internal": "INTEGER"})

db.register_columns("site_events", {
    # WHICH KIND OF PAGE THIS PERSON ARRIVED ON, from the entry cookie - one word from the same fixed
    # list the orders table uses. Until now only ORDERS carried arrival, so "tools run" was one
    # undifferentiated number and the funnel's top and bottom could not be joined: 6,372 people landed
    # on the kundli page and 999 charts were run, and nothing said whether those were the same people.
    "entry": "TEXT NOT NULL DEFAULT ''",
    # Phone or desktop, from the viewport the browser reports. NOT a device string: the width bucket is
    # the whole of it, because the question is whether a form behaves differently on a small screen and
    # a user-agent would be both more identifying and less accurate.
    "device": "TEXT NOT NULL DEFAULT ''",
})

db.register_columns("site_events", {
    # Where the person behind this event first arrived from. First touch, copied from the account, so a
    # sale can be read against the channel that brought them rather than the page they happened to be on.
    "source": "TEXT NOT NULL DEFAULT ''",
    # 0 means the cost of this event was never worked out - an unpriced model, or an event from before
    # the cost was wired up. It is deliberately NOT the same as a cost of zero: every chat question sat
    # at 0.00 for months and the dashboard reported it as a free service.
    "cost_known": "INTEGER NOT NULL DEFAULT 0",
})


def visitor_hash(ip: str, user_agent: str, day: str | None = None) -> str:
    """A visitor, for ONE day. Tomorrow the same browser hashes to something unrelated, by design."""
    day = day or ist_day()
    raw = f"{ip or ''}|{(user_agent or '')[:200]}".encode()
    return hmac.new(_salt(day), raw, hashlib.sha256).hexdigest()[:32]


def is_bot(user_agent: str | None) -> bool:
    return bool(_BOT.search(user_agent or "")) if user_agent else True   # no UA at all is not a reader


def is_page(path: str) -> bool:
    return bool(path) and not path.startswith(_NOT_A_PAGE)


# ---- where a visit came from -------------------------------------------------------------------------
#
# WHY. The dashboard counts 450-580 visitors a day and Search Console reports about 7 Google clicks a day.
# Both cannot be describing the same people. Until arrivals carry a source, every rate computed from them -
# cost per visitor, conversion, which language earns its keep - has an unknown denominator.
#
# WHAT IS KEPT. One word from the list below, and a campaign tag if the link carried one. Never the
# referring URL, never its query, never anything joining a source to a person: the visitor is the same
# daily-salted hash of IP and user agent it has always been.

#: A LABEL of the host -> the word we file it under. Matching on labels rather than on any substring is
#: not fussiness: "t.co" appears inside "reddi(t.co)m", and the first version of this filed every Reddit
#: arrival under Twitter.
_SOURCE_LABELS = {
    "google": "google", "bing": "bing", "duckduckgo": "duckduckgo", "yandex": "yandex",
    "ecosia": "ecosia", "brave": "brave", "qwant": "qwant",
    "chatgpt": "chatgpt", "openai": "chatgpt", "perplexity": "perplexity", "claude": "claude",
    "facebook": "facebook", "instagram": "instagram", "whatsapp": "whatsapp", "twitter": "twitter",
    "youtube": "youtube", "reddit": "reddit", "quora": "quora", "pinterest": "pinterest",
    "linkedin": "linkedin", "telegram": "telegram", "snapchat": "snapchat", "threads": "threads",
    "tumblr": "tumblr", "medium": "medium",
}
#: Whole hosts, for the ones whose label says nothing - and for the AI assistants, whose sub-domain is the
#: part that matters.
_SOURCE_HOSTS = (
    ("googlequicksearchbox", "google"), ("gemini.google.com", "gemini"), ("news.google.com", "google"),
    ("search.yahoo.com", "yahoo"), ("chat.openai.com", "chatgpt"), ("copilot.microsoft.com", "copilot"),
    ("t.co", "twitter"), ("x.com", "twitter"), ("youtu.be", "youtube"), ("fb.com", "facebook"),
    ("fb.me", "facebook"), ("l.facebook.com", "facebook"),
)
_OUR_HOSTS = ("rashikundli.com", "www.rashikundli.com", "localhost", "127.0.0.1")
_CAMPAIGN_OK = re.compile(r"[^a-z0-9 _.-]+")


def classify_source(referer: str | None, query: str | None) -> tuple[str, str]:
    """(source, campaign) for one arrival.

    A tag the person building the link chose beats the referrer, because it was chosen deliberately and
    the referrer is whatever the browser felt like sending. A link from one of our own pages is not an
    arrival at all - counting it would make the biggest source on the dashboard be this site.
    """
    campaign, tagged = "", ""
    for key, value in parse_qsl((query or "").lstrip("?"), keep_blank_values=False):
        if key == "utm_source":
            tagged = value.strip().lower()[:40]
        elif key == "utm_campaign":
            campaign = _CAMPAIGN_OK.sub("", value.strip().lower())[:40]
    if tagged:
        return tagged, campaign

    raw = (referer or "").strip()
    if not raw:
        return "direct", campaign
    try:
        parts = urlparse(raw)
        host = (parts.hostname or "").lower()
        scheme = (parts.scheme or "").lower()
    except ValueError:
        return "other", campaign

    # An app link like "whatsapp://send" has no host worth the name; the scheme IS the source.
    if scheme and scheme not in ("http", "https") and scheme in _SOURCE_LABELS:
        return _SOURCE_LABELS[scheme], campaign
    if not host:
        return "direct" if not scheme else "other", campaign
    if host in _OUR_HOSTS or host.endswith(".rashikundli.com"):
        return "internal", campaign

    for full, name in _SOURCE_HOSTS:
        if host == full or host.endswith("." + full):
            return name, campaign
    for label in host.split("."):
        if label in _SOURCE_LABELS:
            return _SOURCE_LABELS[label], campaign
    return "other", campaign


#: Our own sections, for the one question the funnel could not answer: did the rashifal pages - which are
#: most of the traffic - actually send anybody to the chart or the astrologer? The referrer is already in
#: hand on every request; this keeps the SECTION it came from and nothing else. Not the page, not the sign,
#: not the query - the same arm's length the external sources are kept at.
_OUR_SECTIONS = (
    ("rashifal", ("/horoscope", "/hi/rashifal", "/mr/rashi-bhavishya")),
    ("kundali", ("/birth-chart", "/hi/kundli", "/mr/kundali", "/sidereal-birth-chart")),
    ("matching", ("/horoscope-matching", "/hi/kundali-matching", "/mr/patrika-matching")),
    ("muhurta", ("/muhurta",)),
    ("chat", ("/ai-astrologer", "/hi/ai-jyotish", "/mr/ai-jyotish")),
)


def internal_origin(referer: str | None, host: str = "") -> str:
    """Which section of this site sent them here, or "" when they did not come from inside it.

    `host` is THIS request's own host, and comparing against it is what "internal" actually means. A
    hardcoded list of our domains gets this wrong everywhere the site is not on its production name -
    a staging host, a preview, a test - and files our own links as if they came from a stranger.
    """
    raw = (referer or "").strip()
    if not raw:
        return ""
    try:
        parts = urlparse(raw)
    except ValueError:
        return ""
    from_host = (parts.hostname or "").lower()
    here = (host or "").split(":")[0].lower()
    known = from_host in _OUR_HOSTS or from_host.endswith(".rashikundli.com")
    if from_host and not known and from_host != here:
        return ""
    path = parts.path or ""
    for name, prefixes in _OUR_SECTIONS:
        if any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes):
            return name
    return ""


#: More page views than this from one visitor inside a minute is not somebody reading.
RATE_SUSPECT_VIEWS = 15
_RATE_WINDOW = 60.0


#: WHERE A VISIT STARTED, as one word from a fixed list. Six values, never a path and never an id.
#:
#: It exists because "8,626 visitors and 4 orders" cannot be acted on: it does not say whether the
#: rashifal pages bring readers who were never going to buy, or whether the kundli page converts well and
#: simply gets no traffic. Every step below the top of the funnel needs to know where the journey began,
#: and nothing in site_events or orders carried that.
ENTRY_COOKIE = "entry"
ENTRY_KINDS = (
    ("rashifal", ("/horoscope", "/hi/rashifal", "/mr/rashi-bhavishya")),
    ("kundli", ("/birth-chart", "/kundli", "/hi/kundli", "/mr/kundali", "/sidereal-birth-chart")),
    ("matching", ("/horoscope-matching", "/hi/kundali-matching", "/mr/patrika-matching")),
    ("panchang", ("/panchang", "/hi/aaj-ka-panchang", "/mr/aajche-panchang")),
    ("chat", ("/ai-astrologer", "/hi/ai-jyotish", "/mr/ai-jyotish")),
)
ENTRY_VALUES = tuple(name for name, _ in ENTRY_KINDS) + ("other",)


def entry_kind(path: str) -> str:
    """Which of the six kinds of page this path is. The first match wins."""
    for name, prefixes in ENTRY_KINDS:
        if any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes):
            return name
    return "other"


def record_visit(*, ip: str, user_agent: str, path: str, lang: str = "", is_admin: bool = False,
                 referer: str | None = None, query: str | None = None, host_header: str = "",
                 stamp: float | None = None) -> bool:
    """One page view. -> whether it was counted. Never raises: analytics must not break a page.

    A visit starts with `js = 0` - unproven. A real browser runs the page and says so through
    `confirm_browser`, which is the one signal that separates a reader from something that fetched the
    HTML and stopped. Nothing is ever blocked on this: being wrong about a person must not cost them the
    page, so a suspect visit is counted and flagged, never refused.
    """
    try:
        if not is_page(path) or is_bot(user_agent):
            return False
        now = stamp if stamp is not None else time.time()
        day = ist_day(now)
        who = visitor_hash(ip, user_agent, day)
        source, campaign = classify_source(referer, query)
        via = internal_origin(referer, host=host_header)
        with db.transaction() as conn:
            seen = conn.execute(
                "SELECT COUNT(*) AS n FROM site_visits WHERE visitor = ? AND ts > ?",
                (who, now - _RATE_WINDOW)).fetchone()["n"]
            conn.execute(
                "INSERT INTO site_visits (ts, day, visitor, path, lang, is_admin, source, campaign, "
                "js, suspect, via) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (now, day, who, path[:200], lang[:5], 1 if is_admin else 0, source[:20], campaign[:40],
                 1 if seen >= RATE_SUSPECT_VIEWS else 0, via[:20]))
        return True
    except Exception:  # noqa: BLE001 - counting is never a reason to fail a request
        log.exception("could not record a visit")
        return False


def confirm_browser(*, ip: str, user_agent: str, path: str, stamp: float | None = None) -> bool:
    """A real browser ran the page. -> whether a visit was found to mark.

    The beacon carries nothing: the server recomputes the same visitor hash it stored, so there is no id
    to hand out, nothing to forge that is worth forging, and nothing new kept about anybody.
    """
    try:
        now = stamp if stamp is not None else time.time()
        day = ist_day(now)
        who = visitor_hash(ip, user_agent, day)
        with db.transaction() as conn:
            found = conn.execute(
                "UPDATE site_visits SET js = 1 WHERE id = ("
                "  SELECT id FROM site_visits WHERE visitor = ? AND path = ? AND day = ? "
                "  ORDER BY id DESC LIMIT 1)",
                (who, path[:200], day))
        return found.rowcount > 0
    except Exception:  # noqa: BLE001 - a beacon must never be able to break anything
        log.exception("could not confirm a browser")
        return False


def source_of_visitor(ip: str, user_agent: str, stamp: float | None = None) -> str:
    """The source of this visitor's most recent arrival today, or "" when there is none.

    Used once, at sign-up, to give an account its first touch. It reads the hash it already stored and
    learns nothing new about anybody.
    """
    try:
        now = stamp if stamp is not None else time.time()
        day = ist_day(now)
        with db.transaction(write=False) as conn:
            row = conn.execute(
                "SELECT source FROM site_visits WHERE visitor = ? AND day = ? AND source != 'internal' "
                "ORDER BY id LIMIT 1", (visitor_hash(ip, user_agent, day), day)).fetchone()
        return (row["source"] if row else "") or ""
    except Exception:  # noqa: BLE001
        log.exception("could not read a visitor's source")
        return ""


def visits_on(day: str, *, path: str = "") -> list[dict]:
    """Every visit on one IST day, for the dashboard and for tests. Hashes, never people."""
    clause = " AND path = ?" if path else ""
    args = (day, path) if path else (day,)
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            f"SELECT ts, day, visitor, path, lang, is_admin, source, campaign, js, suspect, via "
            f"FROM site_visits WHERE day = ?{clause} ORDER BY id", args).fetchall()
    return [dict(row) for row in rows]


def record_event(feature: str, action: str, *, account_id: str = "", is_admin: bool = False,
                 ok: bool = True, cost_inr: float | None = None, revenue_inr: float = 0.0, lang: str = "",
                 detail: str = "", source: str = "", stamp: float | None = None,
                 entry: str = "", device: str = "") -> bool:
    """One thing the software did. `detail` is structural - a purpose, a product id - and never prose.

    `cost_inr=None` means NOT RECORDED, which is not the same as nothing. Every chat question was written
    at 0.00 for months because the cost was read from a key nobody wrote, and a column of zeroes looks
    exactly like a free service - Margin equalled Revenue on the dashboard and nobody could tell. An
    unpriced model, or an event from before the cost was wired up, says so now instead of saying zero.
    """
    try:
        now = stamp if stamp is not None else time.time()
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO site_events (ts, day, account_id, is_admin, feature, action, ok, cost_inr, "
                "cost_known, revenue_inr, lang, detail, source, entry, device) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, ist_day(now), (account_id or "")[:64], 1 if is_admin else 0, feature[:32],
                 action[:32], 1 if ok else 0, float(cost_inr or 0.0), 0 if cost_inr is None else 1,
                 float(revenue_inr), (lang or "")[:5], (detail or "")[:200], (source or "")[:20],
                 (entry or "")[:16], (device or "")[:8]))
        return True
    except Exception:  # noqa: BLE001
        log.exception("could not record an event")
        return False


# ---------------------------------------------------------------- reading it back


def revenue_ex_gst(start: str, end: str) -> dict:
    """What we actually KEEP over a range of IST days, and the tax we merely collected.

    THE USAGE PAGE HAS BEEN COUNTING GST AS INCOME. `site_events.revenue_inr` is written from
    `amount_paise`, the tax-INCLUSIVE charge, so every margin on that page included 18% that was never
    ours - it is collected on the government's behalf and remitted. On a Rs 299 sale that is Rs 45.61 of
    imaginary income.

    Read from ORDERS rather than from the events, because the orders table stores the split per row and
    so gives the right answer for sales already made - correcting the recording alone would fix the
    future and leave every historic figure overstated. Orders paid before the GST columns existed have
    NULL there and fall back to the charge, with their count reported separately: a row we cannot split
    is not a row worth guessing at.
    """
    from app.payments import store  # noqa: F401 - imported so the orders schema is registered

    with db.transaction(write=False) as conn:
        # REFUNDS COME OFF. `refunded_paise` accumulates across partial refunds, and a refunded sale
        # counted as revenue is the same flattering error as GST counted as income - the money went
        # back. The refund is taken off the tax-inclusive charge, because that is what was returned, and
        # the tax on it is credited in proportion, which is what the credit note records.
        #
        # NET IS DERIVED FROM GROSS, not summed on its own. Three independent integer truncations put
        # net + gst two paise away from gross, which on a page about money is a figure somebody would
        # eventually have to explain. Subtracting makes the identity true by construction.
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_paise - COALESCE(refunded_paise, 0)), 0)             AS gross, "
            "       COALESCE(SUM(CAST(COALESCE(gst_paise, 0) * "
            "            (1.0 - COALESCE(refunded_paise, 0) * 1.0 / amount_paise) AS INTEGER)), 0) AS gst, "
            "       SUM(CASE WHEN base_paise IS NULL THEN 1 ELSE 0 END)                      AS unsplit, "
            "       SUM(CASE WHEN COALESCE(refunded_paise, 0) > 0 THEN 1 ELSE 0 END)         AS refunded, "
            "       COUNT(*)                                                                 AS orders "
            "FROM orders WHERE status = 'paid' AND COALESCE(live, 1) = 1 AND amount_paise > 0 "
            "AND date(paid_at, 'unixepoch', '+05:30') BETWEEN ? AND ?", (start, end)).fetchone()

        # A PAID ORDER WITH NO PAYMENT DATE IS NOT A PAID ORDER THAT EARNED NOTHING. The range filter
        # above is on paid_at, and some early rows have status 'paid' with that column empty - so they
        # fell out of the window silently and the revenue was short by their whole value. They cannot be
        # put in a day they do not have, so they are counted and reported, and the page says so.
        undated = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(base_paise, amount_paise)), 0) AS base "
            "FROM orders WHERE status = 'paid' AND COALESCE(live, 1) = 1 AND paid_at IS NULL").fetchone()
    gross_paise, gst_paise = row["gross"] or 0, row["gst"] or 0
    return {"net_inr": round((gross_paise - gst_paise) / 100, 2),
            "gst_inr": round(gst_paise / 100, 2),
            "gross_inr": round(gross_paise / 100, 2),
            "orders": row["orders"] or 0,
            "unsplit_orders": row["unsplit"] or 0,
            "refunded_orders": row["refunded"] or 0,
            "undated_orders": undated["n"] or 0,
            "undated_inr": round((undated["base"] or 0) / 100, 2)}


def estimated_cost(start: str, end: str, include_admin: bool = False) -> dict:
    """A cost for the chat and report events that have none, worked out from the ones that do.

    WHY THERE IS A GAP: cost was not carried onto the usage event for months, so those rows sit at
    "unknown" - and a margin that treats unknown as zero is the most flattering possible lie.

    THE ESTIMATE IS PER feature+action AND IT IS A MEDIAN, not a mean: one retried report costing six
    times the usual would drag a mean up and quietly inflate every estimate taken from it. A kind with
    no known rows gets no estimate at all - there is nothing to estimate from, and inventing a number
    would be the same mistake as calling it zero. Those are counted and reported.

    Returned APART from the real cost and never added into it, so the page can label it.
    """
    admin_clause = "" if include_admin else " AND COALESCE(is_admin, 0) = 0"
    with db.transaction(write=False) as conn:
        known = conn.execute(
            f"SELECT feature, action, cost_inr FROM site_events "
            f"WHERE day BETWEEN ? AND ? AND cost_known = 1 AND cost_inr IS NOT NULL "
            f"AND feature IN ('chat', 'report'){admin_clause}", (start, end)).fetchall()
        missing = conn.execute(
            f"SELECT feature, action, COUNT(*) AS n FROM site_events "
            f"WHERE day BETWEEN ? AND ? AND cost_known = 0 AND feature IN ('chat', 'report')"
            f"{admin_clause} GROUP BY feature, action", (start, end)).fetchall()

    samples: dict[tuple[str, str], list[float]] = {}
    for row in known:
        samples.setdefault((row["feature"], row["action"]), []).append(float(row["cost_inr"]))

    total, covered, uncovered = 0.0, 0, 0
    for row in missing:
        values = sorted(samples.get((row["feature"], row["action"]), ()))
        if not values:
            uncovered += row["n"]
            continue
        half = len(values) // 2
        middle = values[half] if len(values) % 2 else (values[half - 1] + values[half]) / 2
        total += middle * row["n"]
        covered += row["n"]
    return {"inr": round(total, 2), "events": covered, "no_basis": uncovered,
            "samples": {f"{key[0]}/{key[1]}": len(value) for key, value in sorted(samples.items())}}


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
            f"SELECT ROUND(SUM(cost_inr), 2) AS cost, ROUND(SUM(revenue_inr), 2) AS revenue, "
            f"       SUM(CASE WHEN cost_known = 0 AND feature IN ('chat', 'report') THEN 1 ELSE 0 END) "
            f"            AS cost_unknown "
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
        # WHERE THEY CAME FROM: visitors, sign-ups and revenue against one another, which is the whole
        # point of the exercise - 450-580 arrivals a day against 7 search clicks is only answerable if
        # the three can be read on one line.
        by_source = conn.execute(
            f"SELECT COALESCE(NULLIF(source, ''), 'direct') AS source, "
            f"       COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS views, "
            f"       SUM(js) AS proven, SUM(suspect) AS suspect "
            f"FROM site_visits WHERE day BETWEEN ? AND ?{admin_clause} "
            f"GROUP BY 1 ORDER BY visitors DESC LIMIT 20", (start, end)).fetchall()
        money_by_source = conn.execute(
            f"SELECT COALESCE(NULLIF(source, ''), 'direct') AS source, "
            f"       SUM(CASE WHEN feature = 'auth' AND action = 'sign-up' THEN 1 ELSE 0 END) AS signups, "
            f"       ROUND(SUM(revenue_inr), 2) AS revenue "
            f"FROM site_events WHERE day BETWEEN ? AND ?{admin_clause} "
            f"GROUP BY 1", (start, end)).fetchall()
        admin_rows = conn.execute(
            "SELECT COUNT(*) AS n FROM site_events WHERE day BETWEEN ? AND ? AND is_admin = 1",
            (start, end)).fetchone()

    cost = float(money["cost"] or 0)
    revenue = float(money["revenue"] or 0)
    money_split = revenue_ex_gst(start, end)
    estimate = estimated_cost(start, end, include_admin)
    # How much of the margin below is a real number. If chat answers or reports went in with no cost
    # worked out, the margin is an over-statement and the page has to say so rather than imply profit.
    cost_unknown = int(money["cost_unknown"] or 0)
    return {
        "from": start, "to": end, "days": days, "include_admin": include_admin,
        "cost_unknown": cost_unknown,
        "by_source": _merge_sources(by_source, money_by_source),
        "views": visits["views"] or 0, "visitors": visits["people"] or 0,
        "per_day": [dict(row) for row in per_day],
        "top_pages": [dict(row) for row in top_pages],
        "languages": [dict(row) for row in languages],
        "features": [dict(row) for row in features],
        "cost_inr": round(cost, 2), "revenue_inr": round(revenue, 2),
        # WHAT WE ACTUALLY KEEP. `revenue_inr` above is the sum of the events, which carry the
        # tax-INCLUSIVE charge - so the margin beside it counted 18% that is collected for the
        # government and remitted. Both are published: the gross is what the customer paid and is the
        # right number next to a payment fee, the net is the only one a margin may be taken on.
        "revenue_net_inr": money_split["net_inr"], "gst_collected_inr": money_split["gst_inr"],
        "revenue_gross_inr": money_split["gross_inr"], "paid_orders": money_split["orders"],
        "unsplit_orders": money_split["unsplit_orders"],
        # Paid orders carrying no payment date: they belong to no day, so they are outside every range
        # on this page rather than wrongly inside one. Reported so the figure above is not read as the
        # whole of the money.
        "undated_orders": money_split["undated_orders"], "undated_inr": money_split["undated_inr"],
        "refunded_orders": money_split["refunded_orders"],
        "margin_inr": round(money_split["net_inr"] - cost, 2),
        # The margin with an estimate filled in for the events that never had a cost recorded. Kept
        # apart and labelled rather than folded in, because an estimate presented as a measurement is
        # how a page stops being trustworthy.
        "estimated_cost_inr": estimate["inr"], "estimated_cost_events": estimate["events"],
        "estimated_cost_no_basis": estimate["no_basis"],
        "margin_with_estimate_inr": round(money_split["net_inr"] - cost - estimate["inr"], 2),
        "cost_by_day": [dict(row) for row in cost_by_day],
        "top_users": [dict(row) for row in top_users],
        "errors": [dict(row) for row in errors],
        # Shown as its own line so an administrator can see what their own use added, and that it was not
        # counted in anything above.
        "admin_events_excluded": (admin_rows["n"] or 0) if not include_admin else 0,
    }


#: The funnel, in the order somebody actually walks it. Each step says where its number comes from, so a
#: reader can tell a measured step from a derived one - and so a step that quietly stops being recorded
#: shows up as a zero next to a name rather than vanishing from the page.
def _consultation_paths() -> tuple[str, ...]:
    """The three AI-astrologer URLs, from the registry that defines them.

    Spelled out here once and they would drift the day a path changes, and the step would quietly read
    zero for ever - a measurement that cannot fire is worse than one that is missing, because it looks
    like an answer.
    """
    from app.web import i18n

    return tuple(i18n.PAGES["consultation"].values())


FUNNEL = (
    ("visitors", "Visitors", "visit", None),
    ("chart", "Birth chart generated", "event", ("kundali", "generated")),
    ("chat_open", "AI astrologer opened", "path", None),          # filled from the URL registry
    # NOT "reached the login page": this site has no login page. The form is inline on whatever page the
    # reader is already on, so asking for a code is the real step, and the gap between it and a finished
    # sign-up is the e-mail round trip - which is where people are actually lost.
    ("code", "Asked for a sign-in code", "event", ("auth", "code-requested")),
    ("signup", "Signed up", "event", ("auth", "sign-up")),
    ("first_q", "First question", "first", ("chat", "question")),
    ("paywall", "Saw the paywall", "event", ("chat", "paywall")),
    ("paid", "Paid", "event", ("report", "sold")),
)


def funnel(days: int = 7, *, lang: str = "", include_admin: bool = False) -> list[dict]:
    """How many people reached each step, in a window, optionally for one language tree.

    PEOPLE, NOT EVENTS. Every step counts DISTINCT visitors or accounts, because the question this answers
    is "how many got this far", and one person asking nine questions is one person. Counting events would
    make the middle of the funnel wider than its top and the whole shape meaningless.
    """
    start, end = _window(days)
    admin_visits = "" if include_admin else " AND is_admin = 0"
    admin_events = "" if include_admin else " AND is_admin = 0"
    lang_visits = " AND lang = ?" if lang else ""
    lang_events = " AND lang = ?" if lang else ""
    out = []
    with db.transaction(write=False) as conn:
        for key, label, kind, spec in FUNNEL:
            args: tuple = (start, end)
            if kind == "visit":
                sql = (f"SELECT COUNT(DISTINCT visitor) AS n FROM site_visits "
                       f"WHERE day BETWEEN ? AND ?{admin_visits}{lang_visits}")
                if lang:
                    args += (lang,)
            elif kind == "path":
                spec = spec or _consultation_paths()
                marks = ", ".join("?" for _ in spec)
                sql = (f"SELECT COUNT(DISTINCT visitor) AS n FROM site_visits "
                       f"WHERE day BETWEEN ? AND ? AND path IN ({marks}){admin_visits}{lang_visits}")
                args += tuple(spec)
                if lang:
                    args += (lang,)
            elif kind == "first":
                # The first question an ACCOUNT ever asked, not every account that asked one in the
                # window: "reached this step" is a thing that happens once per person.
                sql = (f"SELECT COUNT(*) AS n FROM (SELECT account_id, MIN(ts) AS first_ts "
                       f"FROM site_events WHERE feature = ? AND action = ? AND account_id != ''"
                       f"{admin_events} GROUP BY account_id) "
                       f"WHERE first_ts BETWEEN ? AND ?")
                args = (spec[0], spec[1], _epoch(start), _epoch(end, end_of_day=True))
            else:
                sql = (f"SELECT COUNT(DISTINCT CASE WHEN account_id != '' THEN account_id END) AS people, "
                       f"       COUNT(*) AS events FROM site_events "
                       f"WHERE day BETWEEN ? AND ? AND feature = ? AND action = ?"
                       f"{admin_events}{lang_events}")
                args += (spec[0], spec[1])
                if lang:
                    args += (lang,)
            row = conn.execute(sql, args).fetchone()
            count = row["n"] if "n" in row.keys() else (row["people"] or row["events"] or 0)
            out.append({"key": key, "label": label, "people": int(count or 0), "kind": kind})
    top = out[0]["people"] or 0
    for step in out:
        step["share"] = round(100 * step["people"] / top, 1) if top else 0.0
    return out


def _epoch(day: str, end_of_day: bool = False) -> float:
    """An IST calendar day as a timestamp, so a day means what a person in India means by it."""
    import datetime as dt

    date = dt.date.fromisoformat(day)
    moment = dt.datetime.combine(date, dt.time(23, 59, 59) if end_of_day else dt.time(0, 0),
                                 tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    return moment.timestamp()


def internal_journeys(days: int = 7, include_admin: bool = False) -> list[dict]:
    """Who went from one section of this site to another - the rashifal pages' whole job, measured.

    Most of the traffic lands on a rashifal page. Whether any of it goes on to a chart or the astrologer
    was the question the funnel could not answer, because every internal arrival was filed as "internal"
    and stopped there. People, not views: somebody reading nine rashifal pages and opening one chart is
    one journey.
    """
    start, end = _window(days)
    admin = "" if include_admin else " AND is_admin = 0"
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            f"SELECT via AS came_from, "
            f"       CASE WHEN path IN (SELECT value FROM json_each(?)) THEN 'chat' "
            f"            WHEN path IN (SELECT value FROM json_each(?)) THEN 'kundali' "
            f"            ELSE 'elsewhere' END AS went_to, "
            f"       COUNT(DISTINCT visitor) AS people "
            f"FROM site_visits WHERE day BETWEEN ? AND ? AND via != ''{admin} "
            f"GROUP BY 1, 2 HAVING went_to != 'elsewhere' ORDER BY people DESC LIMIT 20",
            (json.dumps(list(_chat_paths())), json.dumps(list(_kundali_paths())), start, end)).fetchall()
    return [dict(row) for row in rows]


def _chat_paths() -> tuple[str, ...]:
    from app.web import i18n

    return tuple(i18n.PAGES["consultation"].values())


def _kundali_paths() -> tuple[str, ...]:
    from app.web import i18n

    return tuple(i18n.PAGES["kundali"].values())


def accounts_that_never_asked(days: int = 30) -> list[dict]:
    """People who signed up in this window and have never asked a question.

    The point of the list is not the number - it is that each row is a person who did the hard part and
    then stopped, so whatever is in their way is costing us the ones who were most willing.
    """
    start, end = _window(days)
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT account_id, MIN(ts) AS signed_up, MAX(lang) AS lang, MAX(source) AS source "
            "FROM site_events WHERE feature = 'auth' AND action = 'sign-up' AND account_id != '' "
            "  AND day BETWEEN ? AND ? AND is_admin = 0 "
            "GROUP BY account_id "
            "HAVING account_id NOT IN (SELECT account_id FROM site_events "
            "                          WHERE feature = 'chat' AND action = 'question') "
            "ORDER BY signed_up DESC LIMIT 50", (start, end)).fetchall()
    return [dict(row) for row in rows]


def _merge_sources(visits, money) -> list[dict]:
    """One row per source: visitors, how many proved they were a browser, sign-ups and revenue."""
    rows: dict[str, dict] = {}
    for row in visits:
        rows[row["source"]] = {"source": row["source"], "visitors": row["visitors"] or 0,
                               "views": row["views"] or 0, "proven": row["proven"] or 0,
                               "suspect": row["suspect"] or 0, "signups": 0, "revenue": 0.0}
    for row in money:
        entry = rows.setdefault(row["source"], {"source": row["source"], "visitors": 0, "views": 0,
                                                "proven": 0, "suspect": 0, "signups": 0, "revenue": 0.0})
        entry["signups"] = row["signups"] or 0
        entry["revenue"] = float(row["revenue"] or 0)
    return sorted(rows.values(), key=lambda r: (-r["visitors"], -r["revenue"], r["source"]))


def recent_events(limit: int = 100, *, include_admin: bool = True) -> list[dict]:
    """The event log. Who (account id), when, what, cost, ok - and never a word anybody wrote."""
    clause = "" if include_admin else " WHERE is_admin = 0"
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            f"SELECT ts, account_id, is_admin, feature, action, ok, cost_inr, cost_known, revenue_inr, "
            f"       lang, detail "
            f"FROM site_events{clause} ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
    return [dict(row) for row in rows]


def mask_account(account_id: str) -> str:
    """An account id is already a hash; this shortens it for a table rather than revealing anything."""
    return f"{account_id[:8]}…" if account_id else "—"


def as_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
