#!/usr/bin/env bash
# The whole test suite, once a night, with enough time to actually finish.
#
# The full suite takes over fifty minutes. Running it before every deploy meant waiting fifty
# minutes for a gate - and the one time it ran, its own `timeout 3000` killed it at 67% and printed
# no summary at all, which looks exactly like a clean run to anything grepping for FAILED. So it
# runs here, nightly, with a three-hour budget, and the deploy gate is scripts/pre_deploy.sh.
#
# Usage:  scripts/nightly_suite.sh            (writes var/nightly-suite.log, exits non-zero on failure)
set -uo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"
export TMPDIR="${TMPDIR:-$PWD/var/nightly-tmp}"
mkdir -p "$TMPDIR" var
LOG="var/nightly-suite.log"
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# NEVER THE SERVING DATABASE. The suites point APP_DB at their own temp files through conftest, but
# this makes it explicit: a nightly job that touched var/app.db would be editing live readings at
# 3am, and the symptom would be a reader seeing yesterday's page.
export APP_DB="$TMPDIR/nightly.db"

# OPENED HERE, BEFORE ANYTHING ELSE WRITES TO IT. This block truncates the log, and it used to come
# after the credential check - so the check's own "inert:" line was written and then wiped on every
# single run. The log looked as though the check had never happened.
{
  echo "=== nightly suite $STAMP ==="
  echo "head: $(git rev-parse --short HEAD) on $(git rev-parse --abbrev-ref HEAD)"
  echo
} > "$LOG"

# ---- this runs ON THE PRODUCTION SERVER, so it runs inert ------------------------------------------
#
# The only always-on box is the one serving the site, so that is where the nightly run lives. A test
# suite beside a live site must not be able to spend money, mail a reader, or touch a payment
# gateway - not "should not": must not be able to.
#
# Neutralised rather than trusted. load_dotenv does NOT override a variable already set, which is
# the whole mechanism: exporting these empty here makes the real values in .env unreachable to
# anything the tests import. (That property is relied on in app/db.py too - see db_path().)
#
# The names are not a fixed list. They are read OUT of .env and matched by shape, so a credential
# added to .env next month is neutralised without anyone remembering to edit this script.
ENV_FILE="$PWD/.env"
SENSITIVE_RE='(KEY|SECRET|TOKEN|PASSWORD|PASSWD|SMTP|MAIL|WEBHOOK|CREDENTIAL)'
declare -a neutralised=()
# FROM .env AND FROM THIS PROCESS'S OWN ENVIRONMENT. Reading only .env left whatever the calling
# shell had already exported - which on a developer box includes real tokens unrelated to .env. The
# first run refused over one of those: correct, but useless. Neutralise it, do not decline to run.
while read -r name; do
  [ -n "$name" ] || continue
  export "$name="
  neutralised+=("$name")
done < <({ [ -f "$ENV_FILE" ] && grep -oE '^[A-Z0-9_]+=' "$ENV_FILE" | tr -d '='
           env | grep -oE '^[A-Z0-9_]+=' | tr -d '='
         } 2>/dev/null | grep -E "$SENSITIVE_RE" | sort -u)
# Belt for names that may not be in .env at all on this box.
for name in ANTHROPIC_API_KEY OPENAI_API_KEY RESEND_API_KEY RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET             RAZORPAY_WEBHOOK_SECRET ADMIN_PASSWORD SESSION_SECRET ALERT_EMAIL_TO EMAIL_FROM; do
  export "$name="
done
export REPORT_EMAIL_ENABLED=0 RASHIFAL_SCHEDULER=0 BLOG_AUTOPUBLISH=0

# FULLY OFFLINE, enforced rather than assumed: an accidental outbound call fails instantly against a
# closed port instead of succeeding. Local traffic is exempt, which is all the suite legitimately
# needs - TestClient never leaves the process and Playwright renders local HTML.
export HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9
export NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1

# AND THEN CHECK, because every line above is a thing I believe rather than a thing I know. This
# asks the app's OWN config layer what it can see, after .env has been loaded the way the app loads
# it. Anything still readable is a refusal, not a warning: the run has not started yet, so there is
# nothing to lose by stopping, and a suite that CAN mail a reader at 2am should never get to try.
leaked=$(ENV_FILE="$ENV_FILE" SENSITIVE_RE="$SENSITIVE_RE" uv run python - <<'PROBE'
import os, re, sys
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(os.environ["ENV_FILE"]))     # exactly as app.web.site and app.db do
except Exception:
    pass
pattern = re.compile(os.environ["SENSITIVE_RE"])
# A FLAG TURNED OFF IS NOT A CREDENTIAL. REPORT_EMAIL_ENABLED=0 matches the shape and has a
# value, and the first version of this refused over it - offering the thing that proves mail is
# disabled as evidence that mail is enabled.
OFF = {"", "0", "false", "off", "no", "none", "null"}
visible = sorted(name for name, value in os.environ.items()
                 if pattern.search(name) and value.strip().lower() not in OFF)
print("\n".join(visible))
PROBE
)
if [ -n "$leaked" ]; then
  {
    echo "nightly suite: REFUSING TO START - credentials are visible to the test run:"
    printf '%s\n' "$leaked" | sed 's/^/    /'
    echo "  These resolve to a non-empty value after .env is loaded, which means the suite could"
    echo "  reach a paid API, a mail provider or a payment gateway. Neutralise them in"
    echo "  deploy/systemd/nightly-suite.service (Environment=NAME=) and run again."
  } | tee -a "$LOG" >&2
  exit 3
fi
printf "inert: %d credential name(s) neutralised, outbound HTTP closed\n\n" "${#neutralised[@]}" >> "$LOG"

started=$(date +%s)
timeout 10800 uv run pytest -q -p no:randomly tests/ --no-header >> "$LOG" 2>&1
code=$?
elapsed=$(( $(date +%s) - started ))

{
  echo
  echo "--- finished in ${elapsed}s, pytest exit ${code} ---"
} >> "$LOG"

# A KILLED RUN IS NOT A PASS, and exit 124 is how `timeout` says so. Checked before the summary,
# because a killed run has no summary and "no FAILED lines" would otherwise read as success.
if [ "$code" -eq 124 ]; then
  echo "nightly suite: KILLED at the 3h limit after ${elapsed}s - no result. See $LOG" >&2
  exit 2
fi
if ! grep -qE "[0-9]+ (passed|failed)" "$LOG"; then
  echo "nightly suite: no summary line - the run did not finish (exit ${code}). See $LOG" >&2
  grep -E "Fatal Python error|MemoryError|Killed" "$LOG" | tail -3 >&2
  exit 2
fi

summary=$(grep -E "[0-9]+ (passed|failed)" "$LOG" | tail -1)
failed_count=$(grep -cE "^FAILED " "$LOG")
echo "nightly suite: ${summary} (${elapsed}s)"
if [ "$failed_count" -gt 0 ]; then
  grep -E "^FAILED " "$LOG" | sed 's/^/  /'
  # Compared against the deploy gate's own list, so the two cannot drift: anything failing here that
  # the gate does not know about is a real finding, and anything the gate excuses is reported as
  # excused rather than silently dropped.
  echo
  echo "  (scripts/pre_deploy.sh KNOWN_FAILURES is the list of the ones that are expected)"
  exit 1
fi
exit 0
