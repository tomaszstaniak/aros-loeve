# Patches

`love/series` lists the patches in application order. Each patch has a header
(title, base, problem, change, targets, upstream status, verification, removal
condition) followed by a Git diff relative to the LÖVE root. An empty series
means the unchanged pin. See [patching.md](../docs/patching.md).

`luajit/series` does the same for LuaJIT; its patches are plain diffs relative to the
root of the LuaJIT archive named in `upstreams.json`, applied by `scripts/deps.py`.
`openal-soft/series` works the same way for OpenAL Soft.
