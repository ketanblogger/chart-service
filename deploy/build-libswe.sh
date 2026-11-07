#!/usr/bin/env bash
# Build libswe from the official Astrodienst source, at the ONE commit that matches what we measured.
#
#   sudo apt-get install -y build-essential git      # once
#   deploy/build-libswe.sh                           # -> /srv/astrology/lib/libswe.so
#   deploy/build-libswe.sh /some/other/prefix        # -> /some/other/prefix/libswe.so
#
# WHY A PINNED COMMIT AND NOT "LATEST". `pyswisseph==2.10.3.2` reports libswe 2.10.03, and
# tests/fixtures/swe_golden.json was generated from it. Equivalence to a thousandth of an arcsecond is only
# meaningful against the SAME ephemeris version: a newer libswe may legitimately change a value, and we
# would have no way to tell that apart from a bug in our own binding. Move the pin deliberately, with a
# regenerated fixture and a note saying why - never as a side effect of cloning.
#
# The .se1 data files are NOT built here. They live in app/engine/ephe and are unchanged by any of this.
set -euo pipefail

REPO="https://github.com/aloistr/swisseph.git"
TAG="v2.10.03"
COMMIT="175e1fcb3108bcd5c0d146c803f51dcf23508012"
PREFIX="${1:-/srv/astrology/lib}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for tool in git make cc; do
    command -v "$tool" >/dev/null || { echo "missing: $tool (apt-get install build-essential git)" >&2; exit 1; }
done

echo "cloning $REPO at $TAG"
git clone --quiet "$REPO" "$WORK/swisseph"
git -C "$WORK/swisseph" checkout --quiet "$COMMIT"

# Refuse to build anything but the commit we pinned. A tag can be moved; a commit id cannot.
actual="$(git -C "$WORK/swisseph" rev-parse HEAD)"
[ "$actual" = "$COMMIT" ] || { echo "expected $COMMIT, got $actual" >&2; exit 1; }

echo "building libswe.so"
make -C "$WORK/swisseph" --quiet libswe.so

mkdir -p "$PREFIX"
install -m 0644 "$WORK/swisseph/libswe.so" "$PREFIX/libswe.so"

echo "installed $PREFIX/libswe.so from $COMMIT"
echo "record this commit in the launch runbook; the Astrodienst licence covers libswe, not the wrapper"
echo
echo "verify:  SWE_LIB=$PREFIX/libswe.so PYTHONPATH=. uv run pytest tests/test_swe_binding.py -q"
