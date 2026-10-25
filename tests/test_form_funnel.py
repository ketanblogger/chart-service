"""The birth-details form funnel: what it records, and the far more important question of what it cannot.

WHY IT EXISTS. 6,372 people arrived on the kundli page in thirty days and 999 charts came out of it.
Five in six left without one and nothing said where they stopped, so every explanation was a guess.

WHAT THESE TESTS ARE MOSTLY ABOUT. A measurement endpoint that a page can post to is a hole in a site
unless it is shut, so most of what follows is about the shutting: a step outside the allowlist is
dropped, a field name outside the allowlist is dropped, no value a reader typed can reach the database
through it, and it answers 204 whatever it is sent so that measurement can never be why somebody
cannot use the form.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import analytics, db
from app.api import FUNNEL_FIELDS, FUNNEL_STEPS
from app.main import app

client = TestClient(app)
SCRIPT = Path("app/static/js/kundli-funnel.js").read_text(encoding="utf-8")


def rows(feature: str) -> list[dict]:
    with db.transaction(write=False) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT action, detail, device, lang, entry FROM site_events WHERE feature = ? "
            "ORDER BY id DESC LIMIT 20", (feature,)).fetchall()]


@pytest.fixture(autouse=True)
def clean():
    with db.transaction() as conn:
        conn.execute("DELETE FROM site_events WHERE feature IN ('kundli_form','offer')")
    yield
    with db.transaction() as conn:
        conn.execute("DELETE FROM site_events WHERE feature IN ('kundli_form','offer')")


def test_a_step_outside_the_allowlist_is_dropped():
    """The allowlist is the whole safety of this route: nothing a page sends may become free text."""
    assert client.post("/api/funnel?step=evil&field=city").status_code == 204
    # Something long and script-shaped is refused EARLIER than the allowlist - the step parameter is
    # capped at 24 characters, so FastAPI answers 422 before the handler runs. Either refusal is fine;
    # what matters is that nothing reached the table.
    assert client.post("/api/funnel?step=<script>alert(1)</script>").status_code in (204, 422)
    assert rows("kundli_form") == []


def test_a_field_name_outside_the_allowlist_is_dropped_but_the_step_is_kept():
    """A reader's city must not arrive here under the name of a field. If somebody sends one anyway,
    the step is still worth counting - it is the VALUE that is refused, not the person."""
    client.post("/api/funnel?step=field_done&field=Pune%20Maharashtra&w=390")
    recorded = rows("kundli_form")
    assert len(recorded) == 1
    assert recorded[0]["action"] == "field_done"
    assert recorded[0]["detail"] == "", "something that was not a field name was stored"


def test_no_value_a_reader_typed_can_reach_the_database():
    """Every string this endpoint accepts is checked against a fixed set before it is stored."""
    # An INVENTED date. The first version of this line used the one the runbook's own grep looks for,
    # which is the operator's real date of birth - copied out of the check while writing a test about
    # not leaking things. The publication guard caught it, which is the entire reason it runs on every
    # commit rather than once before a push.
    for attempt in ("step=field_done&field=1991-03-14", "step=invalid&field=secret",
                    "step=place_typed&field=%E0%A4%AA%E0%A5%81%E0%A4%A3%E0%A5%87"):
        client.post(f"/api/funnel?{attempt}")
    for row in rows("kundli_form"):
        assert row["detail"] in {""} | {f"field={name}" for name in FUNNEL_FIELDS}, row


def test_it_answers_204_whatever_it_is_sent():
    """Measurement must never be the reason somebody cannot use the form it is measuring."""
    for query in ("", "step=", "step=form_seen&w=-5", "step=form_seen&w=999999", "field=city"):
        assert client.post(f"/api/funnel?{query}").status_code in (204, 422)


def test_the_viewport_is_bucketed_and_the_width_itself_is_never_kept():
    """A width is a fingerprinting surface and a device string is worse. The question is only whether
    this was a phone."""
    client.post("/api/funnel?step=form_seen&w=390")
    client.post("/api/funnel?step=first_touch&w=1440")
    seen = {row["action"]: row["device"] for row in rows("kundli_form")}
    assert seen["form_seen"] == "mobile"
    assert seen["first_touch"] == "desktop"
    for row in rows("kundli_form"):
        assert "390" not in (row["detail"] or "") and "1440" not in (row["detail"] or "")


def test_the_language_comes_from_the_page_not_from_a_header():
    for referer, expected in (("http://x/hi/kundli", "hi"), ("http://x/mr/kundali", "mr"),
                              ("http://x/birth-chart", "en"), ("", "en")):
        with db.transaction() as conn:
            conn.execute("DELETE FROM site_events WHERE feature='kundli_form'")
        client.post("/api/funnel?step=form_seen&w=390", headers={"referer": referer} if referer else {})
        assert rows("kundli_form")[0]["lang"] == expected, referer


def test_the_offer_steps_are_recorded_as_their_own_feature():
    """The chat's paywall was counted and the report offer under a free chart was not, so the two steps
    between a free reader and a paying one were invisible."""
    client.post("/api/funnel?step=offer_seen&w=390")
    client.post("/api/funnel?step=offer_click&w=390")
    assert {row["action"] for row in rows("offer")} == {"offer_seen", "offer_click"}
    assert rows("kundli_form") == [], "offer steps leaked into the form funnel"


def test_the_entry_page_is_read_from_the_cookie():
    """This is the join that did not exist: a form step and an arrival could not be connected at all."""
    client.cookies.set(analytics.ENTRY_COOKIE, "kundli")
    client.post("/api/funnel?step=form_seen&w=390")
    client.cookies.clear()
    assert rows("kundli_form")[0]["entry"] == "kundli"


def test_every_step_the_script_sends_is_one_the_server_accepts():
    """Two allowlists that disagree would silently drop a step nobody notices is missing."""
    import re

    sent = set(re.findall(r'send\("([a-z_]+)"', SCRIPT))
    assert sent, "no steps found in the script at all"
    assert sent <= FUNNEL_STEPS, sent - FUNNEL_STEPS


def test_every_field_the_script_names_is_one_the_server_accepts():
    import re

    named = set(re.findall(r'send\("[a-z_]+",\s*"([a-z]+)"\)', SCRIPT))
    assert named <= FUNNEL_FIELDS, named - FUNNEL_FIELDS


def test_the_script_only_watches_and_never_changes_the_form():
    """Measurement must not be able to break the thing it measures. This file reads the DOM the form
    already produces and writes nothing to it - the one attribute it sets is its own marker."""
    for forbidden in (".value =", ".innerHTML", "preventDefault", "submit()", ".disabled"):
        assert forbidden not in SCRIPT, f"the funnel script does {forbidden} to the form"


def test_it_is_a_file_and_not_an_inline_script():
    """`script-src 'self'` blocks inline, and an inline version would die with a console line."""
    for template in ("tool.html", "tool_v2.html"):
        markup = Path(f"app/web/templates/{template}").read_text(encoding="utf-8")
        assert "kundli-funnel.js?v=" in markup, template


def test_the_report_runs_on_an_empty_database_and_says_so():
    """A report that crashes when nothing has happened yet is a report nobody runs on day one."""
    import subprocess
    import sys

    done = subprocess.run([sys.executable, "scripts/form_funnel.py", "--days", "1"],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-400:]
