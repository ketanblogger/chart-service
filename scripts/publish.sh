#!/usr/bin/env bash
# Publish the candidate in ~/rashikundli-publish to the public repository.
#
# THE TOKEN IS NEVER AN ARGUMENT AND NEVER A VARIABLE THIS SCRIPT PRINTS. It is read, by git itself, from
# ~/.gh_publish_token through a credential helper - so it is not in the process list (`ps` shows the
# helper's name, not its output), not in this script's environment as a value anyone can echo, not in the
# shell history, and not in any log line below. `set -x` is deliberately never used.
#
# It refuses to do anything unless the caller passes --i-said-publish, which the agent may only do when the
# person has said "publish" in that terminal, in their latest message. That is a convention a script cannot
# enforce; what the script CAN do is refuse every other way of being run, which it does.
set -euo pipefail

PUBLISH_DIR="${PUBLISH_DIR:-$HOME/rashikundli-publish}"
TOKEN_FILE="${GH_PUBLISH_TOKEN_FILE:-$HOME/.gh_publish_token}"
REMOTE_URL="${PUBLISH_REMOTE:-https://github.com/ketanblogger/chart-service.git}"
BRANCH="main"

die() { printf '\nFAIL: %s\n' "$1" >&2; exit 1; }
say() { printf '%s\n' "$1"; }

EXPECTED_SHA=""
LEASE_SHA=""
CONFIRMED="no"
while [ $# -gt 0 ]; do
  case "$1" in
    --sha)              EXPECTED_SHA="${2:-}"; shift 2 ;;
    --lease)            LEASE_SHA="${2:-}"; shift 2 ;;
    --i-said-publish)   CONFIRMED="yes"; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ "$CONFIRMED" = "yes" ] || die "refusing to publish: the person has not said \"publish\" in this terminal.
       This script is only ever run with --i-said-publish, and only in the turn where they said it."
[ -n "$EXPECTED_SHA" ] || die "--sha is required: the candidate sha that was reported"
[ -n "$LEASE_SHA" ]    || die "--lease is required: the sha that must be live right now"
[ -d "$PUBLISH_DIR/.git" ] || die "$PUBLISH_DIR is not a git repository - build the candidate first"

# ---- the token, without ever showing it ------------------------------------------------------------
[ -f "$TOKEN_FILE" ] || die "no token file at $TOKEN_FILE
       Put a GitHub token with push rights in it, readable only by you:
         printf '%s' '<token>' > $TOKEN_FILE && chmod 600 $TOKEN_FILE"
[ -s "$TOKEN_FILE" ] || die "$TOKEN_FILE is empty"
PERMS="$(stat -c '%a' "$TOKEN_FILE")"
case "$PERMS" in
  600|400) ;;
  *) die "$TOKEN_FILE is mode $PERMS - it must be 600 or 400 (chmod 600 $TOKEN_FILE)" ;;
esac

# A credential helper: git asks, the helper reads the file, git uses it. The value never passes through
# this script, so there is nothing here that could print it by accident.
HELPER_DIR="$(mktemp -d)"
trap 'rm -rf "$HELPER_DIR"' EXIT
cat > "$HELPER_DIR/helper.sh" <<'HELPER'
#!/usr/bin/env bash
# git calls this with "get"; anything else is a store/erase we deliberately ignore.
[ "${1:-}" = "get" ] || exit 0
printf 'username=x-access-token\n'
printf 'password=%s\n' "$(cat "$GH_PUBLISH_TOKEN_FILE")"
HELPER
chmod 700 "$HELPER_DIR/helper.sh"
export GH_PUBLISH_TOKEN_FILE="$TOKEN_FILE"

cd "$PUBLISH_DIR"
GIT=(git -c "credential.helper=$HELPER_DIR/helper.sh" -c "credential.useHttpPath=false")

# ---- is this the candidate that was reported? ------------------------------------------------------
LOCAL_SHA="$(git rev-parse HEAD)"
say "candidate here : $LOCAL_SHA"
say "candidate asked: $EXPECTED_SHA"
[ "$LOCAL_SHA" = "$EXPECTED_SHA" ] || die "the candidate in $PUBLISH_DIR is not the one that was reported.
       Nothing was pushed. Rebuild it, or check the sha."

# ---- is the live repository where we think it is? --------------------------------------------------
REMOTE_BEFORE="$("${GIT[@]}" ls-remote "$REMOTE_URL" "refs/heads/$BRANCH" | awk '{print $1}')"
[ -n "$REMOTE_BEFORE" ] || die "could not read the remote - is the token right, and the network up?"
say "live now       : $REMOTE_BEFORE"
say "lease given    : $LEASE_SHA"
[ "$REMOTE_BEFORE" = "$LEASE_SHA" ] || die "the live repository is at $REMOTE_BEFORE, not the lease $LEASE_SHA.
       Somebody else has pushed, or the lease is stale. NOTHING WAS PUSHED - re-read the lease and decide."

# ---- push ------------------------------------------------------------------------------------------
say ""
say "pushing $LOCAL_SHA over $LEASE_SHA ..."
"${GIT[@]}" push "$REMOTE_URL" "HEAD:$BRANCH" --force-with-lease="$BRANCH:$LEASE_SHA" 2>&1 \
  | sed -e 's#https://[^@]*@#https://#g'      # belt and braces: never echo a URL that could carry a secret

REMOTE_AFTER="$("${GIT[@]}" ls-remote "$REMOTE_URL" "refs/heads/$BRANCH" | awk '{print $1}')"
say ""
say "remote sha after the push: $REMOTE_AFTER"
if [ "$REMOTE_AFTER" = "$LOCAL_SHA" ]; then
  say "PASS: the remote matches the candidate that was published."
  exit 0
fi
die "the remote is $REMOTE_AFTER, which is NOT the candidate $LOCAL_SHA. Check it by hand before doing anything else."
