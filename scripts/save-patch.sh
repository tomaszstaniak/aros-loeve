#!/bin/bash
# Save the uncommitted changes in work/love as the next patch.
#
#   scripts/save-patch.sh <short-name> "<title>" [path ...]
#
# Without paths every change (new, deleted and modified files) is saved.
# The patch gets a header to fill in (problem, scope, status, verification),
# is appended to the series and committed in the work copy. Commit the patch
# and series in this repository afterwards.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$(dirname "$0")/lib.sh"

[ $# -ge 2 ] || die 'usage: save-patch.sh <short-name> "<title>" [path ...]'
name="$1"; title="$2"; shift 2
[[ "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "short name: lowercase letters, digits and hyphens"
[ -d "$WORK_DIR/.git" ] || die "no work copy; run scripts/bootstrap.sh"
[ "$(cat "$WORK_DIR/.git/aros-inputs" 2>/dev/null)" = "$(inputs_id)" ] || die "work copy is stale; run scripts/bootstrap.sh"

last="$(ls "$PATCHES_DIR" | sed -n 's/^\([0-9]\{4\}\)-.*\.patch$/\1/p' | sort | tail -1)"
num="$(printf '%04d' $((10#${last:-0} + 1)))"
file="$num-$name.patch"
[ ! -e "$PATCHES_DIR/$file" ] || die "$file already exists"

if [ $# -gt 0 ]; then git -C "$WORK_DIR" add -A -- "$@"; else git -C "$WORK_DIR" add -A; fi
git -C "$WORK_DIR" diff --cached --quiet && die "nothing to save"

tmp="$(mktemp "$LOVE_TMP/aros-loeve-patch.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
{
  echo "Title: $title"
  echo "Repository: $REPO_ID"
  echo "Base: $(manifest_field commit)"
  echo "Requires: preceding patches in series"
  echo "Date: $(date +%Y-%m-%d)"
  echo "Author: aros-loeve project"
  echo "Problem: TODO"
  echo "Change: TODO"
  echo "Scope: TODO (targets)"
  echo "Upstream: local-only"
  echo "Verification: not run"
  echo "Removal: TODO"
  echo "---"
  git -C "$WORK_DIR" diff --cached --binary --full-index
} > "$tmp"

mv "$tmp" "$PATCHES_DIR/$file"
echo "$file" >> "$SERIES"
git -C "$WORK_DIR" commit -q -m "$file"
inputs_id > "$WORK_DIR/.git/aros-inputs"
echo "saved patches/$REPO_ID/$file; fill in its header, then run scripts/check-reproduction.sh"
