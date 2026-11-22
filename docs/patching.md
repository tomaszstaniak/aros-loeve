---
type: guide
updated: 2026-11-19
---

# Reproducing and saving changes

Requirements: Git, bash, Python 3, tar, shasum.

## Sources

`upstreams.json` pins LÖVE `main` at `def245102c67909f9902095af613b1ae05249b62` (2026-11-04, version 12.0). Fetch it:

```sh
git clone https://github.com/love2d/love.git upstream/love
git -C upstream/love checkout def245102c67909f9902095af613b1ae05249b62
```

Never edit `upstream/love`.

## Work copy

```sh
scripts/bootstrap.sh
```

This creates `work/love`: a Git repository whose first commit is the pinned
tree, and one
commit per patch in `patches/love/series`. Run again to confirm it still matches.
After the pin or series changes, `scripts/bootstrap.sh --recreate` builds a new copy and
moves the old one aside as `work/love.old-<time>`; it refuses while there are
unsaved files.

## Saving a change

Edit files in `work/love`, then:

```sh
scripts/save-patch.sh short-name "Title" [path ...]
```

Without paths every change is saved. The patch is written as the next number, added to
`series` and committed in the work copy. Fill in the header (problem, change, targets,
upstream status, verification, removal condition), then commit the patch and `series`
in this repository.

## Checking reproduction

```sh
scripts/check-reproduction.sh
```

Rebuilds pin + series in a temporary directory and compares it with the work copy's
last commit. Uncommitted changes are listed separately. Nothing in `upstream/` or `work/`
is changed.

