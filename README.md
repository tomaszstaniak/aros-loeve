# aros-loeve

[LÖVE](https://love2d.org), the framework for 2D games written in Lua, for AROS.

This repository holds what turns the LÖVE sources into an AROS program: the pinned
upstream revision, patch series for LÖVE and LuaJIT, and build scripts for LÖVE and
the libraries it needs. LÖVE itself is not copied here.

| System | State |
| --- | --- |
| mainline AROS, x86_64 | released: runs games from a drawer, a `.love` file or a single-file game, from Workbench or a Shell |
| mainline AROS, Raspberry Pi | released: the same on Lua 5.1 (no LuaJIT); tried in the emulator with threads, a real game, saves and Workbench start; sound not verified |
| ABIv11 distributions, x86_64 | not started |

LÖVE version: 12.0 (upstream `main`). It needs OpenGL 3.3 or OpenGL ES 3.0, which mainline
AROS provides through Mesa. Revision 4 needs an AROS nightly of 2026-11-24 or later (a system
structure changed that day and programs have to be built for one side of it); revision 3
serves the nightlies from 2026-11-15 up to that day.

## What works

Window, drawing (images, shapes, text, canvases, shaders), keyboard and mouse, timers,
sound (WAV, Ogg Vorbis, MP3, FLAC and tracker modules; through AHI), game files and saved files, `.love`
archives, threads, physics, the built-in no-game screen. Games run on LuaJIT, with `ffi`
and `bit`.

A game that asks for a window larger than the screen gets one that fits, drawn smaller;
the game still sees the size it asked for.

Network: LuaSocket (TCP, UDP, name lookup, `socket.http`) and ENet, through the system's
TCP/IP stack. Each thread has to open its own sockets.
HTTPS requests with `require "https"` (lua-https): the server's certificate is checked
against the system's CA bundle, and a server that fails the check gets no request.

Tried so far: [Mr. Rescue](https://github.com/SimonLarsen/mrrescue) plays;
[SNKRX](https://github.com/a327ex/SNKRX) starts from its unchanged files: LÖVE answers a
game's request for Steam's library (`luasteam`) with an empty module.
Balatro 1.0.1o starts from its unchanged game file (`love Balatro.exe`) and shows the main
menu in fullscreen; a round is not tried yet.

## Using it

From Workbench: double-click the `love` icon and choose the game in the file requester (a
`.love` file, a single-file Windows game made with LÖVE, or the drawer that holds
`main.lua`), or drop the game's icon on the no-game window. `love --icon <game>` in a Shell
writes an icon that starts the game with a double click.

From a Shell:

    Run love <drawer with main.lua>
    Run love <game.love>

Saved games go to the `Saves` drawer beside the program, one drawer per game. Saves that
an earlier revision left in `ENVARC:LOVE/<game>` stay in use.

Packages: [releases](https://github.com/tomaszstaniak/aros-loeve/releases), or
`apkg install love`.

## Building

See [docs/development.md](docs/development.md). In short:

    scripts/bootstrap.sh
    python3 scripts/deps.py aros-x86_64-abiv1-pc
    python3 scripts/build.py aros-x86_64-abiv1-pc
    python3 scripts/package.py aros-x86_64-abiv1-pc 12.0-aros4

## Layout

| Path | Contents |
| --- | --- |
| `upstreams.json` | LÖVE's pinned commit; archives of the libraries with SHA-256 |
| `patches/love/` | the patch series for LÖVE |
| `patches/luajit/` | the patch series for LuaJIT |
| `scripts/` | patch workflow and build scripts |
| `cmake/aros.cmake` | CMake toolchain file for AROS |
| `docs/` | building, and how changes are saved as patches |

## Licences

The scripts in this repository: MIT. LÖVE: zlib licence. The patches follow the licence
of the files they change. Libraries built by `scripts/deps.py` keep their own licences
(LuaJIT and Lua: MIT; HarfBuzz: MIT-style; libogg, libvorbis, libtheora: BSD-style; OpenAL
Soft: LGPL, linked statically); their texts are
copied into `build/<target>/deps/licenses`. Mbed TLS from the aros-crypto kit (Apache 2.0)
is linked statically; its licence text is in the kit. OpenAL Soft and the SDL kit's GNU
libiconv are LGPL: `scripts/package.py` makes a relink kit beside the package, with the
files the program was linked from.
