"""The opt-in QR: "check gun milan with this biodata", and the row behind it.

ONLY IF THE PERSON TICKS IT. A marriage biodata is handed to strangers and photographed and
forwarded; a code on it that resolves to somebody's exact birth moment is a decision they have to
make deliberately, not a default we chose for them because it made a nicer funnel.

WHAT IS AND IS NOT IN THE URL. The link carries an opaque id and a signature, never the birth
details - a QR is scanned by whoever is holding the paper, and a legible date, time and place in a
query string would be the biodata quietly carrying MORE than it prints. The details sit in one row,
which exists only because the tick was ticked, and holds only what prefilling partner one needs.

IT CAN BE SWITCHED OFF. That is the whole reason this is a row rather than a self-contained
encrypted token: a token that carries its own payload cannot be revoked, and "I have changed my mind
about the sheet that is now in forty WhatsApp groups" is exactly the request this has to be able to
answer. Revoking keeps the row - with its details cleared - so the link can say "this code was
switched off" instead of "not found", which is a different and more alarming thing to read.

A YEAR, THEN IT STOPS. Marriages get arranged; the sheet stays in circulation long after. The row
outlives its usefulness quickly and the expiry is checked on read, so an old link stops working even
if nothing has swept the table.
"""
from __future__ import annotations

import datetime as dt
import hmac
import secrets

from app import db

TTL_DAYS = 365
ID_BYTES = 9                       # 72 bits: a QR stays small and the space is not guessable
SIGNATURE_CHARS = 16

db.register_schema("biodata_qr", """
CREATE TABLE IF NOT EXISTS biodata_qr (
    id          TEXT PRIMARY KEY,
    created     TEXT NOT NULL,
    expires     TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0,
    birth_date  TEXT,
    birth_time  TEXT,
    lat         REAL,
    lon         REAL,
    place       TEXT,
    person      TEXT
);
""")

CAPTION = {
    "en": "Scan to check gun milan with this biodata",
    "hi": "इस बायोडाटा से गुण मिलान देखने के लिए स्कैन करें",
    "mr": "या बायोडाटाशी गुण मिलन पाहण्यासाठी स्कॅन करा",
}


def _mac(token_id: str) -> str:
    from app.ai import chat_identity as identity

    return identity._mac("biodata-qr", token_id)[:SIGNATURE_CHARS]


def issue(*, birth_date: dt.date, birth_time: dt.time | None, lat: float | None,
          lon: float | None, place: str = "", person: str = "",
          now: dt.datetime | None = None) -> str:
    """Store what prefilling partner one needs, and return `<id>.<signature>`."""
    moment = now or dt.datetime.now(dt.timezone.utc)
    token_id = secrets.token_urlsafe(ID_BYTES)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO biodata_qr (id, created, expires, birth_date, birth_time, lat, lon, place, person)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (token_id, moment.isoformat(), (moment + dt.timedelta(days=TTL_DAYS)).isoformat(),
             birth_date.isoformat(), birth_time.isoformat() if birth_time else None,
             float(lat) if lat is not None else None, float(lon) if lon is not None else None,
             place[:120], person[:120]))
    return f"{token_id}.{_mac(token_id)}"


def _split(token: str) -> str | None:
    token_id, _, signature = (token or "").partition(".")
    if not token_id or not signature:
        return None
    return token_id if hmac.compare_digest(signature, _mac(token_id)) else None


def read(token: str, *, now: dt.datetime | None = None) -> dict:
    """`{"status": "ok"|"revoked"|"expired"|"unknown", "birth": {...}|None}`.

    The four are distinguished because they are four different things to tell somebody holding a
    printed sheet, and "not found" for all of them would be both unhelpful and slightly alarming.
    """
    token_id = _split(token)
    if token_id is None:
        return {"status": "unknown", "birth": None}
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM biodata_qr WHERE id = ?", (token_id,)).fetchone()
    if row is None:
        return {"status": "unknown", "birth": None}
    if row["revoked"]:
        return {"status": "revoked", "birth": None}
    moment = now or dt.datetime.now(dt.timezone.utc)
    if dt.datetime.fromisoformat(row["expires"]) <= moment:
        return {"status": "expired", "birth": None}
    return {"status": "ok", "birth": {
        "date": row["birth_date"], "time": row["birth_time"], "lat": row["lat"],
        "lon": row["lon"], "place": row["place"] or "", "person": row["person"] or ""}}


def revoke(token: str) -> bool:
    """Switch it off and clear the details. The row stays so the link can say what happened."""
    token_id = _split(token)
    if token_id is None:
        return False
    with db.transaction() as conn:
        changed = conn.execute(
            "UPDATE biodata_qr SET revoked = 1, birth_date = NULL, birth_time = NULL,"
            " lat = NULL, lon = NULL, place = NULL, person = NULL WHERE id = ?",
            (token_id,)).rowcount
    return bool(changed)


def image_data_uri(url: str) -> str:
    """The QR as an SVG data URI, so it embeds in the sheet like the photo does - no file, no fetch.

    Error correction M: a biodata gets printed, folded and photographed, and M survives that while
    keeping the code small enough to sit beside a line of text.
    """
    import segno

    return segno.make(url, error="m").svg_data_uri(scale=4, border=2)
