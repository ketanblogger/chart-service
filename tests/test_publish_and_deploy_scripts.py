"""The two scripts that now do the publishing and the deploying.

THE TOKEN IS THE WHOLE POINT of most of this. `scripts/publish.sh` must be unable to show it, unable to
put it in a command line that `ps` would reveal, and unable to run at all when the person has not asked
for a publish. Those are properties worth a test rather than a careful reading, because the next edit to
that file will be made in a hurry.

`scripts/deploy.sh` is not run here - there is no VPS on this machine - so what is checked is its shape:
that it stops at the two gates, and that it never runs the payment check.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / "scripts" / "publish.sh"
DEPLOY = ROOT / "scripts" / "deploy.sh"


def test_both_scripts_exist_and_are_executable():
    for script in (PUBLISH, DEPLOY):
        assert script.is_file(), script
        assert script.stat().st_mode & 0o111, f"{script.name} is not executable"


@pytest.mark.parametrize("script", [PUBLISH, DEPLOY])
def test_they_parse(script):
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0


# ---- the token ---------------------------------------------------------------------------------------


def test_publish_never_puts_the_token_on_a_command_line_or_in_output():
    """`ps` shows arguments. A token passed as one is a token every process on the box can read, and a
    token echoed is a token in the scrollback and in whatever captured it."""
    text = PUBLISH.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.split("\n") if not line.lstrip().startswith("#"))
    assert "set -x" not in code, "tracing would print the token's surroundings"
    # The token is only ever read by the helper, from the file, by git.
    assert 'cat "$GH_PUBLISH_TOKEN_FILE"' in text
    for forbidden in ("echo $TOKEN", 'echo "$TOKEN"', "--password", "x-access-token:$",
                      "https://$TOKEN", "${TOKEN}@"):
        assert forbidden not in code, f"{forbidden!r} would expose the token"
    # ...and nothing prints a variable that holds it. The FILE PATH may be printed; the contents may not.
    scrubbed = code.replace("GH_PUBLISH_TOKEN_FILE", "FILE").replace("TOKEN_FILE", "FILE")
    assert not re.search(r"(echo|printf)[^\n]*\bTOKEN\b", scrubbed), \
        "something prints a token-shaped variable"


def test_publish_demands_a_token_file_that_only_the_owner_can_read():
    text = PUBLISH.read_text(encoding="utf-8")
    assert "600|400" in text, "a world-readable token file must be refused"


# ---- what it refuses ---------------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path):
    """A bare repo and a working copy, so nothing here can ever reach the real remote."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    run = lambda *args: subprocess.run(args, cwd=work, check=True, capture_output=True)
    run("git", "config", "user.email", "x@y")
    run("git", "config", "user.name", "x")
    (work / "a.txt").write_text("one")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "one")
    run("git", "push", "-q", str(remote), "HEAD:main")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True,
                          text=True).stdout.strip()
    (work / "a.txt").write_text("two")
    run("git", "commit", "-qam", "two")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True,
                          text=True).stdout.strip()
    token = tmp_path / "token"
    token.write_text("ghp_NOT_A_REAL_SECRET_abc123")
    token.chmod(0o600)
    return {"remote": remote, "work": work, "base": base, "head": head, "token": token}


def _publish(sandbox, *args, token=None):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(sandbox["work"].parent),
           "PUBLISH_DIR": str(sandbox["work"]), "PUBLISH_REMOTE": str(sandbox["remote"]),
           "GH_PUBLISH_TOKEN_FILE": str(token or sandbox["token"])}
    return subprocess.run(["bash", str(PUBLISH), *args], capture_output=True, text=True, env=env)


def _remote_head(sandbox):
    out = subprocess.run(["git", "ls-remote", str(sandbox["remote"]), "refs/heads/main"],
                         capture_output=True, text=True).stdout
    return out.split()[0] if out.strip() else ""


def test_it_refuses_unless_the_person_asked_for_a_publish(sandbox):
    """THE GATE. Everything else here is a safety net; this is the rule."""
    done = _publish(sandbox, "--sha", sandbox["head"], "--lease", sandbox["base"])
    assert done.returncode != 0
    assert "has not said" in done.stderr
    assert _remote_head(sandbox) == sandbox["base"], "it pushed anyway"


def test_it_refuses_a_lease_that_is_not_what_is_live(sandbox):
    done = _publish(sandbox, "--sha", sandbox["head"], "--lease", "0" * 40, "--i-said-publish")
    assert done.returncode != 0
    assert "NOTHING WAS PUSHED" in done.stderr
    assert _remote_head(sandbox) == sandbox["base"]


def test_it_refuses_a_candidate_that_is_not_the_one_reported(sandbox):
    done = _publish(sandbox, "--sha", "1" * 40, "--lease", sandbox["base"], "--i-said-publish")
    assert done.returncode != 0
    assert "not the one that was reported" in done.stderr
    assert _remote_head(sandbox) == sandbox["base"]


def test_it_refuses_when_the_token_file_is_missing(sandbox, tmp_path):
    done = _publish(sandbox, "--sha", sandbox["head"], "--lease", sandbox["base"], "--i-said-publish",
                    token=tmp_path / "nowhere")
    assert done.returncode != 0
    assert "no token file" in done.stderr
    assert _remote_head(sandbox) == sandbox["base"]


def test_it_refuses_a_token_file_anyone_can_read(sandbox):
    sandbox["token"].chmod(0o644)
    done = _publish(sandbox, "--sha", sandbox["head"], "--lease", sandbox["base"], "--i-said-publish")
    assert done.returncode != 0 and "must be 600 or 400" in done.stderr
    assert _remote_head(sandbox) == sandbox["base"]


def test_it_publishes_and_says_whether_the_remote_matches(sandbox):
    done = _publish(sandbox, "--sha", sandbox["head"], "--lease", sandbox["base"], "--i-said-publish")
    assert done.returncode == 0, done.stderr
    assert "PASS" in done.stdout
    assert sandbox["head"] in done.stdout, "it does not print the remote sha after pushing"
    assert _remote_head(sandbox) == sandbox["head"]


def test_the_token_never_appears_in_anything_it_prints(sandbox):
    secret = sandbox["token"].read_text()
    done = _publish(sandbox, "--sha", sandbox["head"], "--lease", sandbox["base"], "--i-said-publish")
    assert secret not in done.stdout and secret not in done.stderr
    # ...and not even a fragment of it
    assert "NOT_A_REAL_SECRET" not in (done.stdout + done.stderr)


# ---- the deploy script ---------------------------------------------------------------------------------


def test_deploy_stops_at_the_two_gates_and_never_charges_anybody():
    """Not run here - there is no VPS on this machine - so its SHAPE is what is checked."""
    text = DEPLOY.read_text(encoding="utf-8")
    assert "browser_check_payments" in text and "deliberately does NOT run" in text, \
        "the payment check must be named and refused, not merely absent - absence is not a decision"
    assert text.count("fail \"app.hardening is not happy") == 1
    assert "the smoke check FAILED" in text
    for required in ("git fetch origin", "git reset --hard origin/main", "uv pip install -r requirements.txt",
                     "-m app.hardening", "systemctl restart", "is-active", "smoke_check.py",
                     "--chromium --expect-payments"):
        assert required in text, f"the deploy is missing: {required}"
    assert "PASS:" in text and "FAIL:" in text
    # SKIP IS NOT A FAILURE. The smoke check's exit code already says so - 1 only when something failed -
    # and the deploy must read it that way rather than counting words in the output, because the browser
    # click skips on a machine with no browser Playwright can start.
    assert "skip" in text.lower(), "the deploy must say what a skip line means"
    assert "EXIT CODE, NOT WORD-COUNTING" in text


def test_deploy_refuses_a_machine_that_is_not_the_vps():
    done = subprocess.run(["bash", str(DEPLOY)], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "APP_DIR": "/nonexistent-on-purpose"})
    assert done.returncode != 0 and "no /nonexistent-on-purpose" in done.stderr
