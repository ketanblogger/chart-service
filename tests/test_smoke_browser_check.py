"""The smoke check's browser click: it must SKIP for a missing browser and FAIL for a broken button.

A SMOKE CHECK THAT GOES RED OVER A MISSING DEVELOPMENT TOOL TRAINS EVERYONE TO IGNORE IT. That is what
happened on the first deploy of this check: the server prints its PDFs with a system Chromium named in
`/srv/astrology/.env`, the smoke check is a separate process that systemd never hands that file to - the
service has no EnvironmentFile on purpose, because the app loads the file itself - so the check went
looking for Playwright's own bundled browser, which was never installed there. The site was fine. The
check said FAIL.

The other half matters just as much: once a browser IS running, nothing may skip. A check that can excuse
itself after starting is a check that can excuse a real breakage.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.test_rendered_contrast import browser, chromium, live_site  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def _smoke():
    """Import scripts/smoke_check.py as a module - it is a script, not a package."""
    spec = importlib.util.spec_from_file_location("smoke_check_under_test",
                                                  ROOT / "scripts" / "smoke_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _smoke()


# ---- telling the two apart ---------------------------------------------------------------------------


@pytest.mark.parametrize("message", [
    "Error: BrowserType.launch: Failed to launch chromium because executable doesn't exist at "
    "/home/astro/.cache/ms-playwright/chromium_headless_shell-1243/chrome-linux/headless_shell",
    "BrowserType.launch: Executable doesn't exist at /somewhere/chrome",
    "Error: browserType.launch: Executable does not exist",
    "playwright is not installed on this machine",
    "FileNotFoundError: [Errno 2] No such file or directory: '/usr/bin/chromium'",
    "Please run the following command to download new browsers",
])
def test_a_browser_that_will_not_start_is_an_environment_gap(message):
    assert smoke._is_missing_browser(message), message


@pytest.mark.parametrize("message", [
    "TimeoutError: page.expect_download: Timeout 45000ms exceeded",
    "the file did not start with %PDF- (b'<!DOC')",
    "no dates came back",
    "the city list returned nothing",
    "AssertionError: something about the page",
])
def test_a_page_that_misbehaves_is_not(message):
    """These all happen AFTER a browser is running, and none of them may be excused as a missing tool."""
    assert not smoke._is_missing_browser(message), message


# ---- the verdict ---------------------------------------------------------------------------------------


class _Boom:
    """A launcher that fails the way a missing browser does."""

    message = ("Error: BrowserType.launch: Failed to launch chromium because executable doesn't exist at "
               "/home/astro/.cache/ms-playwright/chromium_headless_shell-1243/chrome-linux/headless_shell")

    def __call__(self, **kwargs):
        raise RuntimeError(self.message)


class _Refuses:
    """A launcher that fails for a reason that is NOT a missing browser."""

    def __call__(self, **kwargs):
        raise RuntimeError("Error: BrowserType.launch: Protocol error (Target.setAutoAttach): Target closed")


def test_a_missing_browser_skips_and_says_exactly_why():
    verdict, detail = smoke._muhurta_button_downloads("http://127.0.0.1:1", launcher=_Boom())
    assert verdict == "skip", f"a missing browser was reported as {verdict}"
    assert "executable doesn't exist" in detail, detail
    assert "chromium_headless_shell-1243" in detail, "the reason must name the path it looked at"


def test_a_browser_that_starts_and_then_fails_is_a_real_failure():
    """The guard on the guard. Anything that is not recognisably a missing browser is a FAIL, because the
    alternative is a check that quietly excuses itself for reasons nobody enumerated."""
    verdict, detail = smoke._muhurta_button_downloads("http://127.0.0.1:1", launcher=_Refuses())
    assert verdict == "fail", f"an unexplained launch failure was reported as {verdict}"
    assert "would not start" in detail


@pytest.mark.browser
def test_with_a_real_browser_a_broken_button_FAILS(live_site, monkeypatch):
    """THE ONE THAT MATTERS. A real Chromium, a real page, and a button that does nothing - which is the
    bug this whole check was added for. It must be a FAIL and never a skip."""
    from app.web import site

    monkeypatch.setattr(site, "MUHURTA", True)
    # The page is served with a script that binds an id the HTML does not have - exactly what a stale
    # cache did on the live server.
    dead = "(function(){ 'use strict'; var gone = document.getElementById('nothing-here'); })();"
    original = (ROOT / "app" / "static" / "js" / "muhurta.js").read_text(encoding="utf-8")
    (ROOT / "app" / "static" / "js" / "muhurta.js").write_text(dead, encoding="utf-8")
    try:
        verdict, detail = smoke._muhurta_button_downloads(live_site)
    finally:
        (ROOT / "app" / "static" / "js" / "muhurta.js").write_text(original, encoding="utf-8")
    assert verdict == "fail", f"a dead button was reported as {verdict}: {detail}"


@pytest.mark.browser
def test_with_a_real_browser_a_working_button_passes(live_site, monkeypatch):
    from app.web import site

    monkeypatch.setattr(site, "MUHURTA", True)
    verdict, detail = smoke._muhurta_button_downloads(live_site)
    assert verdict == "ok", f"{verdict}: {detail}"
    assert "KB" in detail


# ---- where the browser comes from ------------------------------------------------------------------------


def test_the_check_launches_the_same_chromium_the_app_prints_with(tmp_path, monkeypatch):
    """The fix itself: the options come from `app.pdf.browser.launch_options`, after the app's own `.env`
    has been loaded - which is the step that was missing and the whole reason for the red.

    `root=tmp_path`, which has NO .env, and that is not fussiness. Calling this with the real repository
    root loads the real `.env` into the TEST PROCESS - it holds API keys - and 36 tests elsewhere in the
    suite quietly changed behaviour and started skipping, because whether a key is present is exactly what
    several of them branch on. A test that silently reconfigures the session is worse than no test.
    """
    monkeypatch.setenv("PDF_CHROMIUM_EXECUTABLE", "/usr/bin/some-chromium")
    options = smoke._browser_launch_options(root=tmp_path)
    assert options.get("executable_path") == "/usr/bin/some-chromium"

    from app.pdf import browser as pdf_browser

    assert options == pdf_browser.launch_options(), "the check and the renderer must agree exactly"


def test_reading_the_browser_settings_does_not_reconfigure_the_caller(tmp_path, monkeypatch):
    """The guard on the lesson above: given a root with no .env, nothing in the environment moves."""
    import os

    monkeypatch.delenv("PDF_CHROMIUM_EXECUTABLE", raising=False)
    before = dict(os.environ)
    smoke._browser_launch_options(root=tmp_path)
    assert dict(os.environ) == before, "reading the settings changed the environment"


def test_the_helper_really_reads_the_env_file_the_service_does_not_hand_it(tmp_path, monkeypatch):
    """BEHAVIOUR, not a grep. The first version of this test looked for "load_dotenv" in the source and
    passed happily when the call was deleted - the word was still in the docstring. This writes a .env
    that the environment does NOT contain and asserts the setting arrives.
    """
    import os

    monkeypatch.delenv("PDF_CHROMIUM_EXECUTABLE", raising=False)
    (tmp_path / ".env").write_text("PDF_CHROMIUM_EXECUTABLE=/from/the/env/file/chromium\n", encoding="utf-8")
    # SNAPSHOT AND PUT IT BACK. `load_dotenv` sets real variables in this process - that is the whole
    # point of it on the server - and `monkeypatch.delenv` undoes what monkeypatch did, not what the
    # function under test did afterwards. Without this, the fake path stayed in the environment for the
    # rest of the session and THIRTY-SIX browser tests quietly skipped: every one of them tried to launch
    # a Chromium at /from/the/env/file/chromium. They did not fail. They stopped running, and the suite
    # still said "passed".
    before = dict(os.environ)
    try:
        options = smoke._browser_launch_options(root=tmp_path)
        assert options.get("executable_path") == "/from/the/env/file/chromium", (
            "the check did not read .env, so on the server it goes looking for a browser nobody installed")
    finally:
        os.environ.clear()
        os.environ.update(before)
    assert "PDF_CHROMIUM_EXECUTABLE" not in os.environ, "the fake path outlived its test"



def test_the_suite_can_still_launch_a_browser_after_these_tests_have_run():
    """THE REAL LESSON, as a check rather than a comment. One test wrote a made-up Chromium path into the
    process environment and thirty-six browser tests afterwards skipped instead of running - the suite
    still reported "passed", because a skip is not a failure. This asserts the session was left usable.
    """
    import os

    from app.pdf import browser as pdf_browser

    leaked = os.environ.get("PDF_CHROMIUM_EXECUTABLE", "")
    assert "/from/the/env/file" not in leaked, (
        f"a test left PDF_CHROMIUM_EXECUTABLE={leaked!r} behind; everything browser-driven after it skips")
    ok, reason = pdf_browser.chromium_available()
    assert ok, f"no browser can be launched any more: {reason}"


# ---- the three things the live run reported ------------------------------------------------------------


def test_the_script_runs_from_the_repo_root_without_a_pythonpath():
    """The deploy runbook says `.venv/bin/python scripts/smoke_check.py ...`, which puts `scripts/` on the
    path and not the directory above it - so `import app...` failed and the browser check skipped itself
    with a message about "browser settings". Requiring a PYTHONPATH in front of a documented command is a
    trap for whoever runs it next, so the script says where it lives."""
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-c",
         "import importlib.util, sys;"
         "spec = importlib.util.spec_from_file_location('sc', 'scripts/smoke_check.py');"
         "m = importlib.util.module_from_spec(spec); sys.modules['sc'] = m; spec.loader.exec_module(m);"
         "print(bool(m._browser_launch_options()))"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp"})   # deliberately NO PYTHONPATH
    assert done.returncode == 0, done.stderr[-400:]
    assert "True" in done.stdout, done.stdout


def test_the_admin_check_is_not_wedged_between_an_if_and_its_else():
    """`for ... else` IS valid Python, so a loop dropped between an `if` body and its `else` silently
    steals the else - and that else then runs on every deploy. That is how the live smoke check came to
    announce the sign-in as switched off on a box where it was plainly on, and skip three real checks.

    Read structurally rather than by eye, because by eye is exactly how it got there.
    """
    import ast

    source = (ROOT / "scripts" / "smoke_check.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    for node in ast.walk(main):
        if isinstance(node, ast.For) and node.orelse:
            raise AssertionError(
                f"a for-loop at line {node.lineno} has an `else` - almost certainly an `if`'s else that "
                f"the loop was dropped in front of")


def test_the_sign_in_state_is_read_from_the_page_not_guessed_from_a_status_code():
    """The old probe read "not 401" as "the flag is off", and a rate limit reads the same. The home page's
    sign-in control is rendered when, and only when, the sign-in is on."""
    source = (ROOT / "scripts" / "smoke_check.py").read_text(encoding="utf-8")
    assert 'sign_in_offered = \'class="site-account__in"\' in home.text' in source
    assert "gated = client.post" not in source, "the old inference is still there"
