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
_columns: dict[str, dict[str, str]] = {}  # table -> {column: type and default}
_ready: set[tuple[str, str]] = set()  # (db path, schema name) already applied in this process
_lock = threading.Lock()


def _app_db_from_dotenv() -> str:
    """APP_DB as .env sets it, reading NOTHING ELSE out of that file.

    WHY NOT load_dotenv. The service deliberately has no EnvironmentFile - astrology.service says
    so - and the app picks /srv/astrology/.env up itself through app.web.site. A SCRIPT does not
    import that module, so a script and the server it deploys beside resolved APP_DB differently:
    the web app honoured an APP_DB set in .env and the script silently used var/app.db. Both then
    "worked", on two databases.

    The first fix called load_dotenv() here, and that was dangerous. load_dotenv does not override a
    variable that is SET, but it does set one that is ABSENT - and tests/conftest.py deletes
    RAZORPAY_* and ANTHROPIC_* from every test precisely so that "no test can ever make a billed
    call". db_path() is called by almost every test, so one call put the real keys back: 23
    characters of live Razorpay key and 106 of Anthropic key, in a process that had deliberately
    removed them. Five tests that assert the unconfigured path turned red, which is how it surfaced;
    the part that matters is the one that did not turn red - a test was free to spend real money.

    So this reads one key by name and leaves the rest of the file alone. A file that cannot be read
    is not an error here: APP_DB simply falls back to its default, as it did before any of this.
    """
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "APP_DB":
                return value.strip().strip("'\"")
    except OSError:
        pass
    return ""


def db_path() -> Path:
    # An explicit APP_DB in the environment always wins, which is what the tests rely on; .env is
    # consulted only when the environment is silent.
    path = Path(os.getenv("APP_DB") or _app_db_from_dotenv() or "var/app.db")
    return path if path.is_absolute() else ROOT / path


def register_schema(name: str, ddl: str) -> None:
    """Idempotent DDL (CREATE TABLE IF NOT EXISTS ...), applied lazily to whichever database is in use."""
    _schemas[name] = ddl


def register_columns(table: str, columns: dict[str, str]) -> None:
    """Columns to add to a table that ALREADY EXISTS in a live database.

    `register_schema` is `CREATE TABLE IF NOT EXISTS`, so a column added to its DDL appears on a fresh
    database and never on one that already has the table - which is every deployed one. There was no way
    to add a column at all, and the live `orders` table carries real sales, so it cannot be recreated.

    Idempotent by reading `pragma table_info` rather than by catching the duplicate-column error: an
    ALTER that fails for some other reason must still be loud. Values are `"<type> [DEFAULT ...]"`, and
    SQLite only allows a constant default on ADD COLUMN, so nothing here may be computed. Existing rows
    get NULL unless a default is given, and every reader has to treat NULL as "not recorded" rather than
    as zero - an order paid before the column existed did not cost nothing.
    """
    _columns.setdefault(table, {}).update(columns)


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
        for table, columns in _columns.items():
            if (str(path), f"columns:{table}") in _ready:
                continue
            existing = {row[1] for row in conn.execute(f"pragma table_info({table})")}
            if not existing:
                continue   # the table's own schema has not been registered; nothing to alter
            for column, spec in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")
            _ready.add((str(path), f"columns:{table}"))
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
