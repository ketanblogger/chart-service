#!/usr/bin/env bash
# The fixed pre-deploy gate: about ten minutes of tests, then the live smoke check.
#
# WHY A FIXED LIST AND NOT THE WHOLE SUITE. The full suite takes over fifty minutes and was being
# run before every deploy, which meant it was run as a 50-minute block that got killed by its own
# timeout at 67% and told us nothing. A gate nobody can afford to wait for is not a gate. The whole
# suite now runs nightly (scripts/nightly_suite.sh); this list is what must be green to deploy.
#
# WHY A KNOWN-FAILURE LIST. Four tests fail today for reasons that are recorded and not regressions.
# A gate that is always red is a gate everyone learns to skip - that is exactly how a date-pinned
# festival test sat red for nine days without anyone noticing. So this script fails on a NEW failure
# and on a KNOWN failure that has started passing, and is quiet otherwise. The second half matters:
# without it the list below silently becomes permanent.
#
# Usage:  scripts/pre_deploy.sh [https://rashikundli.com]
set -uo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"
export TMPDIR="${TMPDIR:-$HOME/claude-tmp/sys}"
mkdir -p "$TMPDIR"
LIVE="${1:-https://rashikundli.com}"
LOG="$TMPDIR/pre-deploy.log"

# The list. Chosen for what a deploy can break, with measured times: publication safety (1s),
# the URL registry (1s), dated months (4s), the rendered pages and their language signals (51s),
# reachability and orphans (95s), the sitemap and hreflang (104s).
SUITES=(
  tests/test_publication_safety.py
  tests/test_i18n_registry.py
  tests/test_rashifal_dated_months.py
  tests/test_pages_i18n.py
  tests/test_internal_links_reach_everything.py
  tests/test_seo.py
  # ONE TEST, NOT ITS SUITE. test_rashifal_web.py is 291s whole and would put this gate over ten
  # minutes; this single test is 20s and carries the property worth most at deploy time - that
  # viewing a page never reaches the AI layer. A regression there spends real money per page view,
  # silently, and the bill is the first anyone hears of it.
  tests/test_rashifal_web.py::test_page_views_never_touch_the_ai_client
)
# Measured, in case the budget needs defending later: 1 + 1 + 4 + 51 + 95 + 104 + 20 = 276s of
# tests, ~330s with the live smoke check. Deliberately OUT: test_rashifal_sections.py at 716s and
# the rest of test_rashifal_web.py at 271s, both of which the nightly run covers.

# Each entry is a test id that fails TODAY, with why and what clears it. Shrink this list; never
# grow it without saying so out loud in the same change.
KNOWN_FAILURES=(
  # The three festival-orphan entries are GONE, cleared by the evergreen URLs: /muhurat/<festival>
  # always shows the next occurrence, the dated 2026 pages 301 to it, and the hub links all of them
  # unconditionally because there is always a next date. Removed in the same commit that fixed them,
  # which is what the "known failure that started passing" branch of this script is for.
  # /mantra/shiv-tandav-stotram is 12% Devanagari because the English page prints the whole stotra
  # and explains it in English, which is what that page is for. The fix is to exclude content marked
  # with a different `lang` before measuring, which needs an HTML parser rather than a regex - the
  # reasoning is written out in the test itself.
  "tests/test_pages_i18n.py::test_devanagari_pages_are_written_in_their_language"
)

echo "pre-deploy gate"
echo "  repo : $(git rev-parse --short HEAD) on $(git rev-parse --abbrev-ref HEAD)"
echo "  live : $LIVE"
echo "  log  : $LOG"
echo

started=$(date +%s)
echo "running ${#SUITES[@]} suites ..."
uv run pytest -q -p no:randomly "${SUITES[@]}" --no-header > "$LOG" 2>&1
elapsed=$(( $(date +%s) - started ))

# A RUN THAT DID NOT FINISH IS NOT A PASS. pytest prints a summary line on every ordinary outcome;
# a kill, an OOM or a C-level crash prints none, and grepping for FAILED finds nothing in exactly
# that case - which reads identically to success. So the summary has to be there before anything
# below is believed.
if ! grep -qE "^[0-9]+ (passed|failed)|[0-9]+ failed|[0-9]+ passed" "$LOG"; then
  echo "FAIL: the test run produced no summary line - it did not finish."
  tail -5 "$LOG" | sed 's/^/    /'
  echo "       Nothing has been proved. Do not deploy."
  exit 1
fi

mapfile -t failed < <(grep -oE "^FAILED [^ ]+" "$LOG" | sed 's/^FAILED //' | sort -u)
known_sorted=$(printf '%s\n' "${KNOWN_FAILURES[@]}" | grep -v '^\s*#' | sort -u)

# A KNOWN FAILURE WHOSE SUITE WAS NOT RUN IS NOT A FIXED ONE. "fixed" below is computed as "on the
# known list and not in the failed list", and a test that never ran is also not in the failed list -
# so dropping a suite from SUITES while leaving its tests here would announce them as fixed and
# block the deploy with a message that is the opposite of the truth. Found by running this script
# against a single suite, where it cheerfully reported four unrelated tests as passing.
config_error=""
while read -r entry; do
  [ -n "$entry" ] || continue
  file="${entry%%::*}"
  case " ${SUITES[*]} " in
    *" $file "*) ;;
    *) config_error+="    $entry
       -> its suite ($file) is not in SUITES, so this run cannot say anything about it
" ;;
  esac
done <<< "$known_sorted"
if [ -n "$config_error" ]; then
  echo
  echo "KNOWN_FAILURES names tests this gate does not run:"
  printf '%s' "$config_error"
  echo "    Either add the suite to SUITES or remove the entry. Nothing has been proved about them."
  exit 1
fi
new_failures=$(comm -23 <(printf '%s\n' "${failed[@]}") <(printf '%s\n' "$known_sorted"))
fixed=$(comm -13 <(printf '%s\n' "${failed[@]}") <(printf '%s\n' "$known_sorted"))

echo "  suites finished in ${elapsed}s: $(grep -oE '[0-9]+ passed' "$LOG" | tail -1), ${#failed[@]} failed"
status=0

if [ -n "$new_failures" ]; then
  echo
  echo "NEW FAILURES - these are not on the known list:"
  printf '%s\n' "$new_failures" | sed 's/^/    /'
  status=1
fi

if [ -n "$fixed" ]; then
  echo
  echo "These are on the known-failure list but PASSED. Remove them from KNOWN_FAILURES in this"
  echo "script, in the same commit as whatever fixed them:"
  printf '%s\n' "$fixed" | sed 's/^/    /'
  status=1
fi

if [ "$status" -eq 0 ] && [ "${#failed[@]}" -gt 0 ]; then
  echo "  ${#failed[@]} known failure(s), no new ones - see KNOWN_FAILURES in this script for why."
fi

echo
echo "running the smoke check against the LIVE site ..."
# AGAINST LIVE, BEFORE THE DEPLOY LINE IS WRITTEN. The check is code in this repo, so a change to
# the URL shape can leave it asserting the old world - and then it fails a deploy that was correct,
# which reads as "the deploy broke the site". It is read-only. The payment flags are configuration
# assertions, never a transaction.
if uv run python scripts/smoke_check.py "$LIVE" --expect-payments 2>&1 | tee "$TMPDIR/pre-deploy-smoke.log" | tail -4; then
  :
else
  status=1
fi
if ! grep -qE "^0 failure" "$TMPDIR/pre-deploy-smoke.log"; then
  echo
  echo "The smoke check is not clean. Decide whether the SITE or the CHECK is wrong before"
  echo "touching either - a stale assertion here has already failed one correct deploy."
  status=1
fi

echo
if [ "$status" -eq 0 ]; then
  echo "PASS: the gate is green. Safe to build the candidate and write the deploy line."
else
  echo "STOP: the gate is not green. Nothing above is a reason to deploy anyway."
fi
exit "$status"
