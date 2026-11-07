#!/usr/bin/env bash
# Deploy on the VPS, in one line, with the same commands the runbook has always listed.
#
#   sudo -u astro bash /srv/astrology/scripts/deploy.sh
#
# It STOPS at the first thing that goes wrong and says FAIL. The two gates it will not go past are
# `app.hardening` and the smoke check: a service that restarted is not a service that works, and the
# difference between those two has been the whole point of the smoke check since it was written.
#
# It deliberately does NOT run scripts/browser_check_payments.py. That drives a real checkout, and with
# live keys a real charge - it is a build-time gate and never belongs on this machine.
set -uo pipefail

APP_DIR="${APP_DIR:-/srv/astrology}"
SERVICE="${SERVICE:-astrology}"
SITE="${SITE:-https://rashikundli.com}"
WAIT_SECONDS="${WAIT_SECONDS:-15}"

step() { printf '\n== %s\n' "$1"; }
fail() { printf '\nFAIL: %s\n' "$1" >&2; exit 1; }

cd "$APP_DIR" || fail "no $APP_DIR on this machine"

step "what is here now"
BEFORE="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
printf 'currently deployed: %s\n' "$BEFORE"

step "fetch and reset to origin/main"
# `reset --hard`, never `git pull`: every publication is a new unrelated root commit, so there is nothing
# to fast-forward. Safe because var/ and .env are untracked.
git fetch origin || fail "could not fetch - is the network up?"
git reset --hard origin/main || fail "could not reset to origin/main"
AFTER="$(git rev-parse HEAD)"
printf 'now deployed: %s\n' "$AFTER"
if [ "$BEFORE" = "$AFTER" ]; then
  printf 'NOTE: the sha did not change. Either nothing was published, or this is a re-run.\n'
fi

step "dependencies"
.venv/bin/uv pip install -r requirements.txt || fail "uv pip install failed"

step "configuration check (app.hardening)"
if ! .venv/bin/python -m app.hardening; then
  fail "app.hardening is not happy. NOTHING WAS RESTARTED - read what it listed and fix it first.
       MAIL_TEST_MODE is the one that matters most: with it on, anyone who can read the journal can sign
       in as anyone."
fi

step "restart"
# The restart needs root; everything else runs as astro. If this script was started as astro, sudo will
# ask or fail loudly rather than quietly skipping the restart.
sudo systemctl restart "$SERVICE" || fail "systemctl restart $SERVICE failed"
printf 'waiting %ss for it to come up...\n' "$WAIT_SECONDS"
sleep "$WAIT_SECONDS"

if ! systemctl is-active --quiet "$SERVICE"; then
  printf '\n--- the last 40 journal lines ---\n'
  journalctl -u "$SERVICE" -n 40 --no-pager || true
  fail "$SERVICE is not active after the restart"
fi
printf '%s is active\n' "$SERVICE"

step "smoke check against the live site"
# EXIT CODE, NOT WORD-COUNTING. smoke_check.py returns 1 only when something FAILED; a skip and a warning
# both leave it at 0, which is the distinction that matters here. A skip means a check could not be run -
# the browser click skips when this machine has no browser Playwright can start - and an environment gap
# is not a broken deploy. The skips are printed either way, so they are never silent.
if ! .venv/bin/python scripts/smoke_check.py "$SITE" --chromium --expect-payments; then
  fail "the smoke check FAILED against $SITE. The new code IS deployed and running - read the failures
       above and decide whether to fix forward or roll back (git reset --hard <previous sha> and restart;
       the previous sha was $BEFORE).
       Note: lines marked 'skip' are NOT failures - they are checks that could not run here."
fi

printf '\n=====================================\n'
printf 'PASS: %s is live and the smoke check reported no failures.\n' "$AFTER"
printf 'If it printed any "skip" lines, those are checks this machine could not run - read them, but\n'
printf 'they are not a failed deploy.\n' 
printf '=====================================\n'
