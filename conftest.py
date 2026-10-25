"""Root conftest: keep the collector out of `var/`.

`var/` is runtime data - the database, generated PDFs, run reports, measurement cells - and nothing in it
is ever a test. It held a publication candidate for one afternoon, which is a full checkout WITH ITS OWN
`tests/` directory, and `pytest -q` stopped collecting at all: ImportPathMismatchError on
`var/publish-candidate/tests`, one error, zero tests run. A green suite and a suite that never ran look
different only if you read the last line.
"""

collect_ignore_glob = ["var/*"]


# ---- the real database must never be reachable from a test -------------------------------------------
#
# `tests/conftest.py` points APP_DB at a throwaway file for every test, autouse. That fixture only applies
# to tests UNDER `tests/`, and the rule for scratch work in this repo is "put it under `var/`" - so a
# scratch test written under `var/` gets the worst of both: the glob above keeps the collector away from it,
# and `tests/conftest.py`'s isolation never applies. Run directly, it talks to the DEVELOPER'S REAL
# DATABASE. That happened on 2026-09-29: a throwaway verification wrote a live order row into var/app.db,
# and it was noticed only because its author went looking.
#
# So the isolation is no longer a property of where a file sits. Any test, anywhere, that reaches the real
# database fails loudly instead of writing to it.
import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    """Checked HERE, not in a fixture, and the reason is fixture ordering.

    A root-level autouse fixture runs BEFORE the one in `tests/conftest.py` that points APP_DB at a
    throwaway file - so a guard written as a fixture sees the real path on every single test and fails all
    of them. `pytest_runtest_call` runs after every fixture has been set up, which is the only moment the
    question "which database is this test actually going to use" has a true answer.
    """
    from app import db

    resolved = db.db_path().resolve()
    if resolved == (db.ROOT / "var/app.db").resolve():
        raise AssertionError(
            f"{item.nodeid} would use the REAL database at {resolved}. Tests under tests/ get a throwaway "
            "one from tests/conftest.py's autouse fixture; a test outside that directory gets nothing, so "
            "it must set APP_DB itself or live under tests/."
        )
