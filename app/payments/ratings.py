"""One tap on the order page after delivery: how was the report?

WHY THIS AND NOT A REVIEW FORM. Three paid orders exist. A form asking for a written review would collect
nothing for months, and a page that shows "no reviews yet" sells worse than a page that shows nothing.
A single tap on the page somebody is already on, the moment after they downloaded the thing they bought,
is the only version of this that gets answered at that volume.

WHAT IT STORES: a score of 1 to 5 against the order, the moment it was given, and the language the page
was in. NO FREE TEXT. A comment box is a place for somebody to type their name, their birth details or
their phone number, and this site does not hold any of those for a report buyer beyond the order row - so
the simplest way not to leak them is to have nowhere to put them.

WRITE ONCE. A rating can be given and corrected while the page is open, and after that it is the
customer's answer and not something an email campaign can change later.

NOTHING IS PUBLIC. The display threshold is five real ratings and that display does not exist yet; the
admin can see them, and the public page shows nothing until there are enough that an average means
anything. Three orders dressed up as social proof is the one thing on a page about trust that cannot be
undone once somebody notices it.
"""
from __future__ import annotations

import datetime as dt

from app import db

#: The whole scale. A tap, not a form.
SCORES = (1, 2, 3, 4, 5)

#: How many real ratings before anything is shown publicly. Below this an average is a number about
#: three people, which is not a claim this site should make about a product.
PUBLIC_THRESHOLD = 5

db.register_schema("order_ratings", """
CREATE TABLE IF NOT EXISTS order_ratings (
    order_id   TEXT PRIMARY KEY,
    score      INTEGER NOT NULL,
    language   TEXT,
    rated_at   TEXT NOT NULL
)
""")


def record(order_id: str, score: int, *, language: str | None = None) -> dict:
    """Stores one rating, replacing this order's previous answer if it had one."""
    if score not in SCORES:
        raise ValueError(f"score must be one of {SCORES}")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO order_ratings (order_id, score, language, rated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(order_id) DO UPDATE SET score=excluded.score, language=excluded.language, "
            "rated_at=excluded.rated_at",
            (order_id, int(score), language, now))
    return {"order_id": order_id, "score": int(score), "rated_at": now}


def for_order(order_id: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM order_ratings WHERE order_id = ?", (order_id,)).fetchone()
    return dict(row) if row else None


def summary() -> dict:
    """What the admin sees, and what a public display WOULD use once there are enough.

    `public` is the gate, stated here rather than at each call site so there is one answer to "may this
    be shown". It is False until PUBLIC_THRESHOLD ratings exist, whatever the average is.
    """
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT score, COUNT(*) AS n FROM order_ratings GROUP BY score").fetchall()
    counts = {score: 0 for score in SCORES}
    for row in rows:
        counts[row["score"]] = row["n"]
    total = sum(counts.values())
    average = round(sum(score * n for score, n in counts.items()) / total, 2) if total else None
    return {"counts": counts, "total": total, "average": average,
            "public": total >= PUBLIC_THRESHOLD, "threshold": PUBLIC_THRESHOLD}
