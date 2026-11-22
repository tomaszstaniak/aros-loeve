# Scripts

The shell scripts are bash. `env.sh` loads settings: existing environment first, then
`../local.env`, then defaults.

| Script | Purpose |
|---|---|
| `bootstrap.sh [--recreate]` | Create or verify `work/love` |
| `save-patch.sh <name> "<title>" [path ...]` | Save work-copy changes as the next patch |
| `check-reproduction.sh` | Rebuild pin + series in a temporary directory and compare |
| `lib.sh` | Shared helpers |
| `deps.py <target>` | Build the libraries LÖVE needs into `build/<target>/deps` |
| `build.py <target>` | Build LÖVE into `build/<target>/love` |
| `package.py <target> <release>` | Make the AROS drawer, the apkg archive and the LGPL relink kit in `build/<target>/package` |
| `make-icon.py` | Write an AROS PNG icon from a PNG picture |

Keys: `LOVE_TMP` (temporary directory, default `$TMPDIR` or `/tmp`).
