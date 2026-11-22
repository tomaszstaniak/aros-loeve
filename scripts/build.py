#!/usr/bin/env python3
"""Configure and build LÖVE for AROS from work/love.

    python3 scripts/build.py <target> [--plain-lua] [--configure-only] [-j N]

Needs the libraries from scripts/deps.py, the aros-sdl kit (local.json
"sdl_kit") and the aros-crypto kit (local.json "crypto_kit"). Output: build/<target>/love (CMake tree) with the executable
build/<target>/love/love. The log is build/<target>/build.log.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deps  # noqa: E402

ROOT = deps.ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=list(deps.ARCH_CFLAGS))
    ap.add_argument("--configure-only", action="store_true")
    ap.add_argument("--plain-lua", action="store_true",
                    help="Lua 5.1 instead of LuaJIT; builds into build/<target>/love-lua51")
    ap.add_argument("-j", default="8")
    a = ap.parse_args()
    if a.target in deps.NO_LUAJIT:
        a.plain_lua = True
    t = deps.config(a.target)
    base = ROOT / "build" / a.target
    d, kit, sdk = base / "deps", Path(t["sdl_kit"]), Path(t["sdk"])
    if not (d / "BUILD.json").exists():
        raise SystemExit("run scripts/deps.py first")
    bld = base / ("love-lua51" if a.plain_lua else "love")
    log = base / ("build-lua51.log" if a.plain_lua else "build.log")
    log.unlink(missing_ok=True)
    opts = [
        f"-DCMAKE_TOOLCHAIN_FILE={ROOT}/cmake/aros.cmake", "-DCMAKE_BUILD_TYPE=Release",
        f"-DAROS_CC={t['cc']}", f"-DAROS_CXX={t['cxx']}", f"-DAROS_AR={t['ar']}", f"-DAROS_SDK={sdk}",
        "-DAROS_CFLAGS=" + " ".join(deps.ARCH_CFLAGS[a.target] + deps.COMMON_CFLAGS[1:]),
        "-DCMAKE_POSITION_INDEPENDENT_CODE=OFF",
        # LÖVE compiles its bundled libraries with -w; a call to an undeclared
        # function must still stop the build.
        "-DCMAKE_C_FLAGS=" + " ".join(deps.ARCH_CFLAGS[a.target] + deps.COMMON_CFLAGS[1:]
                                      + ["-Werror=implicit-function-declaration"]),
        f"-DSDL3_DIR={kit}/lib/cmake/SDL3",
        f"-DAROS_CRYPTO_KIT={t['crypto_kit']}",
        f"-DFREETYPE_INCLUDE_DIRS={sdk}/include",
        f"-DFREETYPE_INCLUDE_DIR_ft2build={sdk}/include",
        f"-DFREETYPE_INCLUDE_DIR_freetype2={sdk}/include",
        f"-DFREETYPE_LIBRARY={sdk}/lib/libfreetype2.static.a",
        f"-DHARFBUZZ_INCLUDE_DIR={d}/include/harfbuzz", f"-DHARFBUZZ_LIBRARY={d}/lib/libharfbuzz.a",
        f"-DTHEORA_INCLUDE_DIR={d}/include", f"-DTHEORA_LIBRARY={d}/lib/libtheoradec.a",
        f"-DTHEORADEC_LIBRARY={d}/lib/libtheoradec.a",
        f"-DVORBIS_INCLUDE_DIR={d}/include", f"-DVORBIS_LIBRARY={d}/lib/libvorbis.a",
        f"-DVORBISFILE_LIBRARY={d}/lib/libvorbis.a",
        f"-DOGG_INCLUDE_DIR={d}/include", f"-DOGG_LIBRARY={d}/lib/libogg.a",
        f"-DOPENAL_INCLUDE_DIR={d}/include/AL", f"-DOPENAL_LIBRARY={d}/lib/libopenal.a",
        f"-DMODPLUG_INCLUDE_DIR={d}/include", f"-DMODPLUG_LIBRARY={d}/lib/libmodplug.a",
        f"-DZLIB_INCLUDE_DIR={sdk}/include", f"-DZLIB_LIBRARY={sdk}/lib/libz.static.a",
    ]
    if a.plain_lua:
        opts += ["-DLOVE_JIT=OFF", f"-DLUA_INCLUDE_DIR={d}/include", f"-DLUA_LIBRARY={d}/lib/liblua51.a",
                 f"-DLUA_LIBRARIES={d}/lib/liblua51.a"]
    else:
        opts += ["-DLOVE_JIT=ON", f"-DLUAJIT_INCLUDE_DIR={d}/include/luajit",
                 f"-DLUAJIT_LIBRARY={d}/lib/libluajit.a"]
    # System libraries the static parts call: libpng (FreeType), openurl (SDL).
    std = ["-lpng", "-lopenurl"]
    emutls = d / "lib/libarosemutls.a"
    if emutls.exists():
        # __emutls_get_address for code compiled with -femulated-tls.
        std.append(str(emutls))
    fix = d / "lib/unwind-dw2-fixed.o"
    if fix.exists():
        # Linked ahead of libgcc (the driver adds -lgcc after these): C++ throws work.
        std.insert(0, str(fix))
    opts.append("-DCMAKE_CXX_STANDARD_LIBRARIES=" + " ".join(std))
    deps.run(["cmake", "-S", ROOT / "work/love", "-B", bld, "-G", "Unix Makefiles"] + opts, logfile=log)
    if a.configure_only:
        return
    deps.run(["cmake", "--build", bld, "-j", a.j, "--", "-k"], logfile=log)
    deps.check_no_got(t, bld / "love")
    print(f"built: {bld}/love")


if __name__ == "__main__":
    main()
