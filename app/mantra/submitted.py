"""What has already been sent to IndexNow, so nothing is sent twice.

THE RELEASE GATE NEEDS NO STATE AND THIS IS NOT THE GATE. Whether a page is live remains a pure
function of the date; this records only what has been ANNOUNCED, which is a different question and
genuinely needs remembering - a submission already made cannot be observed from the registry or the
calendar.

WHY A CATCH-UP IS NEEDED AT ALL. The timer submits the texts whose release date is today. If the
deploy lands after a release date - the deadline is tight and deploys slip - that morning's pages
are live by the gate and were never announced, because the timer that would have announced them ran
on a machine that did not have them yet. The pages would simply sit uncrawled, and nothing would
say so. So the timer asks a different question: of everything live now, what has not been submitted?

Recorded per URL rather than per text, because the two languages are two URLs and a partial
submission - the Hindi accepted, the English refused - must leave the English still owed.
"""
from __future__ import annotations

import datetime as dt

from app import db

db.register_schema("mantra_indexnow", """
CREATE TABLE IF NOT EXISTS mantra_indexnow_submitted (
    url          TEXT PRIMARY KEY,
    submitted_at TEXT NOT NULL              -- ISO date, for reading the table by eye
);
""")


def already() -> set[str]:
    with db.transaction(write=False) as conn:
        return {row[0] for row in conn.execute("SELECT url FROM mantra_indexnow_submitted")}


def record(urls: list[str], *, day: dt.date | None = None) -> int:
    """Mark these URLs as submitted. Idempotent: re-recording one changes nothing."""
    when = (day or dt.date.today()).isoformat()
    with db.transaction() as conn:
        before = conn.execute("SELECT count(*) FROM mantra_indexnow_submitted").fetchone()[0]
        conn.executemany(
            "INSERT OR IGNORE INTO mantra_indexnow_submitted (url, submitted_at) VALUES (?, ?)",
            [(url, when) for url in urls])
        after = conn.execute("SELECT count(*) FROM mantra_indexnow_submitted").fetchone()[0]
    return after - before


def outstanding(day: dt.date | None = None) -> list[str]:
    """Every URL of every live text, in both languages, that has not been submitted yet.

    The hubs are deliberately NOT here: their content changes on every release morning, so they are
    submitted each time rather than once.
    """
    from app.mantra import texts as mantra_texts
    from app.web import i18n

    sent = already()
    return [path
            for text in mantra_texts.live(day)
            for path in (i18n.url_for("mantra", "hi", slug=text.slug),
                         i18n.url_for("mantra", "en", slug=text.slug))
            if path not in sent]
