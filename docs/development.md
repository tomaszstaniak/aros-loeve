---
type: guide
updated: 2026-11-20
---

# Building

Host: macOS or Linux with Git, bash, Python 3, CMake, make, a C compiler, curl, tar,
patch, shasum.

## What you need

- An AROS cross compiler (GCC 10.5 is what the port is built with) and the matching
  Developer SDK. For mainline x86_64 the SDK must provide FreeType, zlib, libpng and
  OpenGL headers; the official nightly SDK does.
- The aros-sdl kit for the same target (static SDL 3 with the AROS port from the
  AROS contrib repository).
- The aros-crypto kit for the same target (static Mbed TLS with the AROS platform
  parts), for HTTPS requests.

- For the Raspberry Pi: the Pi toolchain is Clang without a C++ library, so a libc++ built
  for AROS is needed as well (`cxxrt`: a directory with `include/c++/v1` and `lib`). The Pi
  build uses Lua 5.1 instead of LuaJIT and gets thread-local variables from
  `support/aros_emutls.c`.

Copy `local.example.json` to `local.json` and fill in the paths, or set `AROS_CC`,
`AROS_CXX`, `AROS_AR`, `AROS_SDK`, `AROS_SDL_KIT` and `AROS_CRYPTO_KIT`.

## Steps

```sh
git clone https://github.com/love2d/love.git upstream/love
git -C upstream/love checkout <commit from upstreams.json>
scripts/bootstrap.sh
python3 scripts/deps.py aros-x86_64-abiv1-pc
python3 scripts/build.py aros-x86_64-abiv1-pc
```

- `scripts/bootstrap.sh` creates `work/love`: the pinned LÖVE with the patch series.
- `scripts/deps.py` downloads LuaJIT, Lua 5.1, HarfBuzz, OpenAL Soft, libogg, libvorbis and
  libtheora (checked against the SHA-256 values in `upstreams.json`), applies
  `patches/<name>/series` where there is one, and builds static libraries into
  `build/<target>/deps`. Log: `build/<target>/deps.log`. LuaJIT's build also needs the
  build machine's own C compiler (`cc`) for its code generators.
- `scripts/build.py` runs LÖVE's CMake build with `cmake/aros.cmake`. Result:
  `build/<target>/love/love`. Log: `build/<target>/build.log`. With `--plain-lua` it
  links Lua 5.1 instead of LuaJIT, into `build/<target>/love-lua51`.

Both scripts refuse output with GOT relocations (position-independent code), which AROS
cannot load, and C sources that call undeclared functions.

## C++ exceptions on mainline x86_64

Mainline GCC 10.5 toolchains built before AROS commit `52bab89955` have a libgcc
unwinder that aborts on every C++ throw. LÖVE needs exceptions. If `local.json` has
`gcc_build` (the build tree of that GCC), `deps.py` rebuilds the one object with the
defect removed and `build.py` links it. With a newer toolchain leave `gcc_build` out.

## Running

```
Run love <drawer with main.lua>
Run love <game.love>
```

The program asks for an 8 MiB stack by itself.

## LuaJIT on AROS

LuaJIT is built as for an unknown system (`TARGET_SYS=Other`) with 64-bit GC, the C
library's allocator and its own stack unwinding. `patches/luajit` adds what AROS lacks:
a seed from entropy.resource and memory for machine code from exec.library.

## Sound

OpenAL Soft is built statically with its SDL3 backend, so sound goes through the SDL kit's
AHI driver. `patches/openal-soft` keeps its helper libraries from being compiled as
position-independent code, which AROS cannot load.
