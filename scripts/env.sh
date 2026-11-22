# Shared settings for the workflow scripts. Bash only.
# Precedence: existing environment, then ../local.env, then the defaults below.
# Relative values in local.env resolve against the directory containing it.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$PROJECT_ROOT/local.env" ]; then
  eval "$(python3 - "$PROJECT_ROOT/local.env" <<'PY'
import os, shlex, sys
from pathlib import Path
path = Path(sys.argv[1])
for raw in path.read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, val = (s.strip() for s in line.split("=", 1))
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1]
    if not key or key in os.environ:
        continue
    if val and not Path(val).is_absolute():
        val = str((path.parent / val).resolve())
    print(f"export {key}={shlex.quote(val)}")
PY
)"
fi

REPO_ID="${REPO_ID:-love}"
LOVE_TMP="${LOVE_TMP:-${TMPDIR:-/tmp}}"
UPSTREAM_DIR="$PROJECT_ROOT/upstream/$REPO_ID"
WORK_DIR="$PROJECT_ROOT/work/$REPO_ID"
PATCHES_DIR="$PROJECT_ROOT/patches/$REPO_ID"
SERIES="$PATCHES_DIR/series"
MANIFEST="$PROJECT_ROOT/upstreams.json"
