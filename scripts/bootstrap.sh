#!/bin/bash
# Create work/love from the pinned upstream and the full patch series,
# or confirm that the existing copy still matches them.
#
#   scripts/bootstrap.sh              create, or verify an existing copy
#   scripts/bootstrap.sh --recreate   rebuild after a pin or series change
#
# work/love is a Git repository whose first commit is the pinned tree
# with submodule contents as plain files, followed by one commit per patch.
# It is never deleted: --recreate moves the old copy aside with its .git.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$(dirname "$0")/lib.sh"

RECREATE=0
case "${1:-}" in "") ;; --recreate) RECREATE=1 ;; *) die "usage: bootstrap.sh [--recreate]" ;; esac
[ -f "$MANIFEST" ] || die "missing upstreams.json"
[ -f "$SERIES" ] || die "missing $SERIES (an empty file is a valid series)"
check_upstream

want="$(inputs_id)"
# Built beside work/ so the final move stays on one file system.
mkdir -p "$(dirname "$WORK_DIR")"
ref="$(mktemp -d "$WORK_DIR.new.XXXXXX")"
trap 'rm -rf "$ref"' EXIT
build_tree "$ref/tree"
want_tree="$(git -C "$ref/tree" rev-parse 'HEAD^{tree}')"

if [ -d "$WORK_DIR/.git" ]; then
  have="$(cat "$WORK_DIR/.git/aros-inputs" 2>/dev/null || true)"
  head_tree="$(git -C "$WORK_DIR" rev-parse 'HEAD^{tree}')"
  dirty="$(git -C "$WORK_DIR" status --porcelain --ignored)"
  if [ "$have" = "$want" ] && [ "$head_tree" = "$want_tree" ]; then
    [ -z "$dirty" ] && echo "work copy in sync ($want_tree)" || { echo "work copy in sync; unsaved changes:"; echo "$dirty"; }
    exit 0
  fi
  echo "work copy differs from pin + series (inputs ${have:-unknown} -> $want, tree $head_tree -> $want_tree)"
  [ "$RECREATE" = 1 ] || die "run with --recreate after saving any changes"
  [ -z "$dirty" ] || die "work copy has unsaved or ignored files; save or move them first"
  aside="$WORK_DIR.old-$(date +%Y%m%d-%H%M%S)"
  mv "$WORK_DIR" "$aside"
  echo "previous work copy moved to $aside (with its .git, stashes and branches)"
fi

mkdir -p "$(dirname "$WORK_DIR")"
mv "$ref/tree" "$WORK_DIR"
echo "$want" > "$WORK_DIR/.git/aros-inputs"
echo "work copy created: $(series_entries | wc -l | tr -d ' ') patch(es), tree $want_tree"
