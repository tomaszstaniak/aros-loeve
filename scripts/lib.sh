# Helpers shared by bootstrap.sh, save-patch.sh and check-reproduction.sh.
# Requires env.sh to be sourced first.

die() { echo "$(basename "$0"): $*" >&2; exit 1; }

manifest_field() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repositories"][sys.argv[2]][sys.argv[3]])' \
    "$MANIFEST" "$REPO_ID" "$1"
}

series_entries() {
  sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^$/d' "$SERIES"
}

# Stable identity of the inputs: pin, ordered series, patch contents.
inputs_id() {
  {
    echo "pin $(manifest_field commit)"
    while IFS= read -r p; do
      [ -f "$PATCHES_DIR/$p" ] || die "series names missing patch $p"
      echo "patch $p $(shasum -a 256 < "$PATCHES_DIR/$p" | cut -d' ' -f1)"
    done < <(series_entries)
  } | shasum -a 256 | cut -d' ' -f1
}

# The upstream checkout must sit on the pin with every submodule at its
# recorded commit and no local change anywhere.
check_upstream() {
  local pin; pin="$(manifest_field commit)"
  [ -d "$UPSTREAM_DIR/.git" ] || die "no checkout in $UPSTREAM_DIR (see docs/patching.md)"
  [ "$(git -C "$UPSTREAM_DIR" rev-parse HEAD)" = "$pin" ] || die "upstream is not at the pin $pin"
  [ -z "$(git -C "$UPSTREAM_DIR" status --porcelain --ignore-submodules=none)" ] || die "upstream has local changes"
  if git -C "$UPSTREAM_DIR" submodule status --recursive | grep -q '^[-+U]'; then
    die "upstream submodules are missing or not at their recorded commits"
  fi
}

# Export the pinned tree, submodule contents included, as plain files into $1.
export_base() {
  local dest="$1"
  mkdir -p "$dest"
  git -C "$UPSTREAM_DIR" ls-files -z --recurse-submodules \
    | tar -C "$UPSTREAM_DIR" --null -T - -cf - \
    | tar -C "$dest" -xf -
}

# Build a Git repository in $1: base commit, then one commit per patch.
build_tree() {
  local dest="$1" pin; pin="$(manifest_field commit)"
  export_base "$dest"
  (
    cd "$dest"
    git init -q -b base
    git config user.name "aros-loeve"
    git config user.email "aros-loeve@localhost"
    git config core.autocrlf false
    git config core.safecrlf false
    # Every exported file is tracked upstream; personal ignore rules must not drop any.
    git config core.excludesFile /dev/null
    # No background gc/maintenance: it races with removing temporary trees.
    git config gc.auto 0
    git config maintenance.auto false
    git add -A
    git commit -q -m "LÖVE $pin (with submodule contents)"
    git tag pin
    while IFS= read -r p; do
      git apply --index --whitespace=nowarn "$PATCHES_DIR/$p" || { echo "failed to apply $p" >&2; exit 1; }
      git commit -q -m "$p"
    done < <(series_entries)
    git branch -q -m main
  )
}
