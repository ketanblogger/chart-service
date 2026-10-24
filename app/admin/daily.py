"""The six figures the daily digest did not have, each scoped to one IST calendar day.

The digest in app/admin/alerts.py already reports what the ORDERS say - how many, what they earned,
what they cost, how long they took. What it could not say is anything about the people who did not buy,
which on a day with two orders is almost everybody.

ONE IST DAY, midnight to midnight, the same window every other number on the admin uses. Not "the last
24 hours": two figures on one page measured over different windows cannot be compared, and somebody
will compare them anyway.

Each figure is its own function and each returns a plain number or a small list, so a figure that fails
to compute can be left out of the message rather than taking the whole e-mail down with it - a digest
that does not arrive is worse than one missing a line.
"""
from __future__ import annotations

import datetime as dt

from app import analytics, db
from app.admin import metrics


def _bounds(day: dt.date) -> tuple[float, float]:
    return metrics.day_start(day), metrics.day_start(day + dt.timedelta(days=1))


def visitors(day: dt.date) -> dict:
    """People and page views, excluding the administrator's own browsing and suspected crawlers."""
    with db.transaction(write=False) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS views, COUNT(DISTINCT visitor) AS people FROM site_visits "
            "WHERE day = ? AND COALESCE(is_admin, 0) = 0 AND COALESCE(suspect, 0) = 0",
            (day.isoformat(),)).fetchone()
    return {"views": row["views"] or 0, "people": row["people"] or 0}


def top_entry_pages(day: dt.date, limit: int = 5) -> list[dict]:
    """Where visits STARTED, not which pages were busiest.

    The busiest page is almost always the one everybody passes through; the page somebody ARRIVED on is
    the one that earned the visit, and it is the number the funnel work is about.
    """
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT visitor, path, MIN(ts) FROM site_visits WHERE day = ? AND COALESCE(is_admin,0)=0 "
            "AND COALESCE(suspect,0)=0 AND visitor <> '' GROUP BY visitor", (day.isoformat(),)).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["path"]] = counts.get(row["path"], 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    return [{"path": path, "visits": n, "kind": analytics.entry_kind(path)} for path, n in ranked]


def refunds(day: dt.date) -> dict:
    start, end = _bounds(day)
    with db.transaction(write=False) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount_paise), 0) AS paise FROM webhook_refunds "
            "WHERE at >= ? AND at < ?", (start, end)).fetchone()
    return {"count": row["n"] or 0, "inr": round((row["paise"] or 0) / 100, 2)}


def unpaid_orders(day: dt.date) -> dict:
    """Orders created that day and still not paid. The one step where somebody decided to buy and did
    not, so it is the number a change to checkout can actually move."""
    start, end = _bounds(day)
    with db.transaction(write=False) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount_paise), 0) AS paise FROM orders "
            "WHERE created_at >= ? AND created_at < ? AND status <> 'paid' AND paid_at IS NULL",
            (start, end)).fetchone()
    return {"count": row["n"] or 0, "inr": round((row["paise"] or 0) / 100, 2)}


def new_ratings(day: dt.date) -> dict:
    # Imported for its SCHEMA. db.register_schema runs at module import, so a table whose module nothing
    # imported does not exist in this process - which is how this read failed with "no such table" in a
    # test that had never touched payments. app/analytics.py imports app.payments.store for the same
    # reason, and says so.
    from app.payments import ratings  # noqa: F401

    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT score FROM order_ratings WHERE substr(rated_at, 1, 10) = ?",
            (day.isoformat(),)).fetchall()
    scores = [row["score"] for row in rows]
    return {"count": len(scores),
            "average": round(sum(scores) / len(scores), 1) if scores else None,
            "scores": sorted(scores)}


def failed_rashifal(day: dt.date) -> dict:
    """Pages the generator could not produce. Read from the run files, which is where the generator
    records them - the same source scripts/remedy_rejections.py reads."""
    import json
    from pathlib import Path

    runs = Path("var/rashifal/runs")
    if not runs.is_dir():
        return {"runs": 0, "failed": 0, "pages": []}
    stamp = day.strftime("%Y%m%d")
    failed, seen, pages = 0, 0, []
    for path in runs.glob(f"*-{stamp}T*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        seen += 1
        failed += int((data.get("counts") or {}).get("failed") or 0)
        for outcome in data.get("outcomes") or []:
            if str(outcome.get("status", "")).lower() == "failed":
                pages.append(f"{outcome.get('language','?')}/{outcome.get('rashi','?')}/"
                             f"{outcome.get('period','?')}")
    return {"runs": seen, "failed": failed, "pages": pages[:10]}


def lines_for(day: dt.date) -> list[str]:
    """The six figures as digest lines. A figure that cannot be computed is LEFT OUT, not guessed and
    not allowed to take the message down - a digest that does not arrive is worse than a short one."""
    out: list[str] = []
    for label, build in (
        ("visitors", lambda: f"Visitors           {visitors(day)['people']} "
                             f"({visitors(day)['views']} page views)"),
        ("refunds", lambda: _refund_line(day)),
        ("unpaid", lambda: _unpaid_line(day)),
        ("ratings", lambda: _rating_line(day)),
        ("rashifal", lambda: _rashifal_line(day)),
        # THE TWO STEPS BETWEEN ARRIVING AND BUYING, which nothing in this digest covered. 6,372
        # people reached the kundli page in thirty days and 999 charts came out of it; the offer
        # under a free chart was not counted at all. Both are here so the gap is read every morning
        # rather than rediscovered every quarter.
        ("form", lambda: _form_line(day)),
        ("offer", lambda: _offer_line(day)),
        # WHAT WENT OUT UNDER OUR NAME YESTERDAY. With autopublish on, a post can reach the public
        # without anybody reading it, so the digest names each one with its link - the morning read
        # is the first human look at it, and a list with no links is a list nobody checks.
        ("blog", lambda: _blog_line(day)),
        # THE MATCHING FUNNEL. 34 visits in thirty days against half a million monthly searches for
        # "kundali milan" - the page's problem is that nobody arrives, and the only way to know
        # whether that is changing is to read arrivals, runs and offers side by side every morning.
        ("matching", lambda: _matching_line(day)),
    ):
        try:
            line = build()
        except Exception as exc:  # noqa: BLE001 - one broken figure must not cost the whole message
            line = f"{label:18} not computed ({type(exc).__name__})"
        if line:
            out.append(line)
    top = []
    try:
        top = top_entry_pages(day)
    except Exception:  # noqa: BLE001
        pass
    if top:
        out.append("")
        out.append("Arrived on:")
        out += [f"  {row['visits']:>4}  {row['path']}" for row in top]
    return out


def _matching_line(day: dt.date) -> str:
    """Matching: who landed, who ran one, who saw and pressed the report offer."""
    from app import db
    from app.web import i18n

    paths = {i18n.url_for("matching", lang) for lang in i18n.LANGS}
    paths |= {i18n.url_for("gun-milan-name", lang) for lang in i18n.LANGS}
    marks = ",".join("?" * len(paths))
    iso = day.isoformat()
    with db.transaction(write=False) as conn:
        landed = conn.execute(
            f"SELECT COUNT(DISTINCT visitor) AS n FROM site_visits WHERE day = ? "
            f"AND path IN ({marks}) AND COALESCE(is_admin,0)=0 AND COALESCE(suspect,0)=0",
            (iso, *sorted(paths))).fetchone()["n"]
        ran = conn.execute(
            "SELECT COUNT(*) AS n FROM site_events WHERE day = ? AND feature = 'matching' "
            "AND action = 'generated' AND COALESCE(internal,0)=0", (iso,)).fetchone()["n"]
        offers = conn.execute(
            "SELECT action, COUNT(*) AS n FROM site_events WHERE day = ? AND feature = 'offer' "
            "AND detail LIKE '%matching%' AND COALESCE(internal,0)=0 GROUP BY action",
            (iso,)).fetchall()
        # The share card (item 4): offered, names ticked, shared. Whether a match gets forwarded at
        # all is the only number here that is about reach rather than about us.
        cards = conn.execute(
            "SELECT action, COUNT(*) AS n FROM site_events WHERE day = ? AND feature = 'match_card' "
            "AND action LIKE 'match_card_%' AND COALESCE(internal,0)=0 GROUP BY action",
            (iso,)).fetchall()
    seen = next((row["n"] for row in offers if row["action"] == "offer_seen"), 0)
    pressed = next((row["n"] for row in offers if row["action"] == "offer_click"), 0)
    card = {row["action"]: row["n"] for row in cards}
    shared = card.get("match_card_shared", 0)
    if not (landed or ran or seen or shared):
        return ""
    line = (f"Matching           {landed} landed, {ran} matched, "
            f"offer {seen} seen / {pressed} pressed")
    if card.get("match_card_seen") or shared:
        line += (f"\n                   card {card.get('match_card_seen', 0)} seen / "
                 f"{card.get('match_card_named', 0)} named / {shared} shared")
    return line


def _blog_line(day: dt.date) -> str:
    """The posts that went live on this day, each with its address."""
    from app.blog import store as blog_store
    from app.web import site

    posts = blog_store.published_on(day.isoformat())
    if not posts:
        return ""
    base = site.base_url().rstrip("/")
    lines = [f"Blog posts         {len(posts)} published"]
    lines += [f"  {base}{post['path']}  -  {post['title']}" for post in posts]
    return "\n".join(lines)


def _form_line(day: dt.date) -> str:
    """Birth-details form: how many people reached it, and how many got a chart out of it."""
    counts = _event_counts(day, "kundli_form", ("form_seen", "result"))
    seen, done = counts.get("form_seen", 0), counts.get("result", 0)
    if not seen:
        return ""                      # nothing to say, rather than a line of zeros every morning
    return f"Kundli form        {seen} started, {done} finished ({100 * done / seen:.0f}%)"


def _offer_line(day: dt.date) -> str:
    """The paid report's offer under a free chart: seen, and pressed."""
    counts = _event_counts(day, "offer", ("offer_seen", "offer_click"))
    seen, clicked = counts.get("offer_seen", 0), counts.get("offer_click", 0)
    if not seen:
        return ""
    return f"Report offer       {seen} seen, {clicked} pressed ({100 * clicked / seen:.0f}%)"


def _event_counts(day: dt.date, feature: str, actions: tuple[str, ...]) -> dict[str, int]:
    """{action: count} for one feature on one IST day, customers only."""
    from app import db

    marks = ",".join("?" * len(actions))
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            f"SELECT action, COUNT(*) AS n FROM site_events "
            f"WHERE day = ? AND feature = ? AND COALESCE(internal,0)=0 AND action IN ({marks}) "
            "GROUP BY action", (day.isoformat(), feature, *actions)).fetchall()
    return {row["action"]: row["n"] for row in rows}


def _refund_line(day: dt.date) -> str:
    found = refunds(day)
    return f"Refunds            {found['count']}" + ("" if not found["count"] else
                                                     f", Rs {found['inr']:.2f}")


def _unpaid_line(day: dt.date) -> str:
    found = unpaid_orders(day)
    return f"Unpaid orders      {found['count']}" + ("" if not found["count"] else
                                                     f", Rs {found['inr']:.2f} not taken")


def _rating_line(day: dt.date) -> str:
    found = new_ratings(day)
    if not found["count"]:
        return "New ratings        none"
    return f"New ratings        {found['count']}, average {found['average']} ({found['scores']})"


def _rashifal_line(day: dt.date) -> str:
    found = failed_rashifal(day)
    if not found["runs"]:
        return "Rashifal           no run"
    if not found["failed"]:
        return f"Rashifal           {found['runs']} run(s), no failed pages"
    return (f"Rashifal           {found['failed']} FAILED page(s) in {found['runs']} run(s)"
            + (f": {', '.join(found['pages'])}" if found["pages"] else ""))
