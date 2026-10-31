import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: needs headless Chromium (Playwright); skipped when it cannot launch")


@pytest.fixture(autouse=True)
def _never_touch_the_real_database_or_razorpay(tmp_path, monkeypatch):
    """Default isolation for every test (modules may override): a throw-away SQLite file - the report gate now
    looks up paid orders - and no Razorpay or Anthropic credentials from a developer's .env, so no test can
    ever make a billed call (tests that need a key set a fake one themselves)."""
    monkeypatch.setenv("APP_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path / "rashifal-runs"))  # scripts/rashifal_refresh.py run reports
    # A test report written into the real cache is keyed like a real one, so a paying customer whose birth
    # details hash to the same id would be served it. Keep every generated artefact inside tmp_path.
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("PDFS_DIR", str(tmp_path / "pdfs"))
    for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
                 "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
