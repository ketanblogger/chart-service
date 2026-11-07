"""Whether an `app.*` log line reaches the journal at all (app/logs.py).

This file exists because of a real, silent hole: every `log.info()` in this codebase - order created, order
PAID, invoice number, report generated, cost - has been dropped on every deploy since the first one. uvicorn's
`--log-level info` configures uvicorn's own loggers, our loggers had no handler, the root logger had none
either, so Python's `lastResort` fallback emitted WARNING and above and silently discarded the rest. It took a
real refund on 2026-09-29, whose event left nothing in the journal, to notice.

Writing MORE log lines would not have fixed that, which is the reason these assertions are about the
plumbing rather than about any one message.
"""

import logging

import pytest

from app import logs, mailer


@pytest.fixture(autouse=True)
def _restore_app_logging(monkeypatch):
    """These tests take the configuration apart on purpose. Put it back afterwards, or the file that runs next
    inherits a silenced `app` logger and its logging assertions pass by capturing nothing."""
    yield
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logs.configure()


def _fresh() -> logging.Logger:
    """The `app` logger with our handler removed, as a process that has not called configure() sees it."""
    log = logging.getLogger(logs.APP_LOGGER)
    for handler in [h for h in log.handlers if getattr(h, logs._MARK, False)]:
        log.removeHandler(handler)
    log.setLevel(logging.NOTSET)
    return log


def test_without_configure_an_info_line_is_dropped_and_with_it_it_is_not(monkeypatch):
    """The hole itself, in one test. `lastResort` is what a plain `logging.getLogger(__name__)` falls back to,
    and its level is WARNING - so the assertion is about the EFFECTIVE level of a child logger, which is what
    decides whether the record is created at all."""
    log = _fresh()
    child = logging.getLogger("app.payments.routes")
    assert log.level == logging.NOTSET
    assert logging.lastResort.level == logging.WARNING  # what we were relying on without knowing it
    assert not child.isEnabledFor(logging.INFO), "before configure(), an app INFO line goes nowhere"

    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logs.configure()
    assert child.isEnabledFor(logging.INFO) and not child.isEnabledFor(logging.DEBUG)


def test_configure_is_idempotent_and_leaves_third_party_loggers_alone(monkeypatch):
    """Called at import and safe to call again: two handlers would print every line twice, which in a journal
    reads as the event happening twice. httpx and anthropic stay where they are - at INFO they log per request
    and per token stream, and our own lines would be lost in it."""
    _fresh()
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    log = logs.configure()
    logs.configure()
    ours = [handler for handler in log.handlers if getattr(handler, logs._MARK, False)]
    assert len(ours) == 1
    assert logging.getLogger("httpx").level == logging.NOTSET
    assert logging.getLogger("anthropic").level == logging.NOTSET
    # pytest's caplog captures through the root logger, so propagation must stay on: turning it off would
    # make every logging assertion in this suite pass by capturing nothing at all.
    assert log.propagate is True


def test_the_level_is_configuration(monkeypatch):
    _fresh()
    monkeypatch.setenv("LOG_LEVEL", "warning")
    assert logs.configure().level == logging.WARNING
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert logs.configure().level == logging.DEBUG
    monkeypatch.setenv("LOG_LEVEL", "not-a-level")          # a typo must not silence the app
    assert logs.configure().level == logging.INFO
    monkeypatch.delenv("LOG_LEVEL")
    assert logs.configure().level == logging.INFO
    assert logs.configure("warning").level == logging.WARNING   # an explicit argument wins over the env


def test_an_address_the_mailer_logs_is_masked(monkeypatch, caplog):
    """Turning INFO on means "e-mail sent to ..." now reaches the journal on every paid order, so the address
    goes in masked. The first character and the domain survive, which is what lets an operator match a
    customer who has written in; the full address is on the admin order page, and that view is audited."""
    logs.configure()
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("REPORT_EMAIL_ENABLED", "1")
    with caplog.at_level(logging.INFO, logger="app.mailer"):
        assert mailer.send("keshav.pawar@example.com", "Your order", "body") is False
    assert "k***@example.com" in caplog.text
    assert "keshav.pawar@example.com" not in caplog.text
