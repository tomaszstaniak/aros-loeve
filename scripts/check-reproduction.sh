#!/bin/bash
# Rebuild pin + series in a temporary directory and compare it with the
# committed state of work/love. Changes nothing in upstream/ or work/.
# Uncommitted changes in the work copy are listed separately.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$(dirname "$0")/lib.sh"

check_upstream
mkdir -p "$PROJECT_ROOT/build"
ref="$(mktemp -d "$PROJECT_ROOT/build/repro.XXXXXX")"
trap 'rm -rf "$ref"' EXIT
build_tree "$ref/tree"
want="$(git -C "$ref/tree" rev-parse 'HEAD^{tree}')"
echo "reconstructed: $want ($(series_entries | wc -l | tr -d ' ') patch(es))"
[ -d "$WORK_DIR/.git" ] || { echo "no work copy to compare"; exit 0; }
have="$(git -C "$WORK_DIR" rev-parse 'HEAD^{tree}')"
if [ "$have" = "$want" ]; then echo "work copy HEAD matches"; else echo "work copy HEAD differs: $have"; git -C "$ref/tree" diff --stat HEAD "$have" 2>/dev/null || true; exit 1; fi
extra="$(git -C "$WORK_DIR" status --porcelain --ignored)"
[ -z "$extra" ] || { echo "unsaved changes in the work copy:"; echo "$extra"; }
