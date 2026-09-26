"""Tiny SQLite layer shared by the consultation chat (Phase 5) and payments (Phase 6).

One file, `var/app.db` (env `APP_DB` overrides; tests point it at a temp dir). stdlib sqlite3 only.

Usage:

    from app import db

    db.register_schema("orders", '''CREATE TABLE IF NOT EXISTS orders (...);''')   # at import time

    with db.transaction() as conn:                 # BEGIN IMMEDIATE ... COMMIT (ROLLBACK on exception)
        conn.execute("UPDATE ... WHERE ...", (...))

    with db.transaction(write=False) as conn:      # plain read
        row = conn.execute("SELECT ...").fetchone()   # sqlite3.Row: row["column"]

Every call opens its own short-lived connection, so it is safe from FastAPI's threadpool and from several
uvicorn workers. Writers use BEGIN IMMEDIATE, which serialises them: a check-then-update inside one
`transaction()` (quota, balances, idempotent credits) cannot race. WAL mode keeps readers unblocked.
"""

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_schemas: dict[str, str] = {}
_ready: set[tuple[str, str]] = set()  # (db path, schema name) already applied in this process
_lock = threading.Lock()


def db_path() -> Path:
    path = Path(os.getenv("APP_DB", "var/app.db"))
    return path if path.is_absolute() else ROOT / path


def register_schema(name: str, ddl: str) -> None:
    """Idempotent DDL (CREATE TABLE IF NOT EXISTS ...), applied lazily to whichever database is in use."""
    _schemas[name] = ddl


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)  # autocommit; we issue BEGIN ourselves
    conn.row_factory = sqlite3.Row
    for attempt in range(6):
        try:  # switching a brand-new file to WAL takes an exclusive lock that ignores the busy timeout, so
            conn.execute("PRAGMA journal_mode=WAL")  # several workers creating the database at once can collide
            break
        except sqlite3.OperationalError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    with _lock:
        for name, ddl in _schemas.items():
            if (str(path), name) not in _ready:
                conn.executescript(ddl)
                _ready.add((str(path), name))
    return conn


@contextmanager
def transaction(write: bool = True):
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
