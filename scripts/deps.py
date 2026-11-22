#!/usr/bin/env python3
"""Build the libraries LÖVE needs that the AROS SDK does not have.

    python3 scripts/deps.py <target>

Lua 5.1, LuaJIT, HarfBuzz, libogg, libvorbis, libtheora (decoder) and OpenAL Soft
from the archives named in upstreams.json, static, into build/<target>/deps. SDL3 comes from the aros-sdl kit
(local.json "sdl_kit"); FreeType and zlib come from the SDK. Compilers and SDKs
come from local.json; AROS_CC, AROS_CXX, AROS_AR and AROS_SDK override them.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "upstreams.json").read_text())
DISTFILES = ROOT / "distfiles"
ARCH_CFLAGS = {
    "aros-x86_64-abiv1-pc": ["-m64", "-mcmodel=large", "-mno-red-zone", "-mno-ms-bitfields"],
    # Clang: thread_local variables through __emutls_get_address (support/aros_emutls.c).
    "aros-aarch64-abiv1-raspi": ["-femulated-tls"],
}
# Built with plain Lua 5.1 only: LuaJIT is not ported to these.
NO_LUAJIT = ("aros-aarch64-abiv1-raspi",)
COMMON_CFLAGS = ["-O2", "-fno-asynchronous-unwind-tables", "-fno-omit-frame-pointer"]


def run(cmd, cwd=None, logfile=None, env=None):
    cmd = [str(c) for c in cmd]
    out = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if logfile:
        with open(logfile, "a") as f:
            f.write("$ " + " ".join(cmd) + "\n" + out.stdout + out.stderr)
    if out.returncode:
        sys.stderr.write(out.stdout[-3000:] + out.stderr[-3000:])
        raise SystemExit(f"failed ({out.returncode}): {' '.join(cmd)[:200]}")
    return out.stdout


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def config(target):
    local = ROOT / "local.json"
    cfg = json.loads(local.read_text()).get(target, {}) if local.exists() else {}
    t = {k: os.environ.get("AROS_" + k.upper(), cfg.get(k, "")) for k in ("cc", "cxx", "ar", "sdk", "sdl_kit", "crypto_kit")}
    for k, v in t.items():
        if not v or not Path(v).exists():
            raise SystemExit(f"{target}: '{k}' not set or missing ({v!r}); see local.example.json")
    t["gcc_build"] = cfg.get("gcc_build", "")
    # A toolchain without a C++ standard library (the Raspberry Pi's Clang)
    # gets one from "cxxrt": a libc++ build with include/c++/v1 and lib. The
    # compiler is then called through a script that names both.
    cxxrt = os.environ.get("AROS_CXXRT", cfg.get("cxxrt", ""))
    if cxxrt:
        if not (Path(cxxrt) / "include/c++/v1").is_dir():
            raise SystemExit(f"{target}: 'cxxrt' has no include/c++/v1 ({cxxrt!r})")
        wrap = ROOT / "build" / target / "tools/cxx"
        wrap.parent.mkdir(parents=True, exist_ok=True)
        wrap.write_text(f'#!/bin/sh\nexec "{t["cxx"]}" -nostdinc++ -isystem "{cxxrt}/include/c++/v1" '
                        f'-L"{cxxrt}/lib" "$@"\n')
        wrap.chmod(0o755)
        t["cxx"] = str(wrap)
    t["cxxrt"] = cxxrt
    t["cflags"] = ARCH_CFLAGS[target] + COMMON_CFLAGS
    t["target"] = target
    return t


def distfile(key):
    d = MANIFEST["distfiles"][key]
    p = DISTFILES / d["file"]
    if not p.exists():
        DISTFILES.mkdir(exist_ok=True)
        run(["curl", "-sSLf", "-o", p, d["url"]])
    if sha256(p) != d["sha256"]:
        raise SystemExit(f"{p}: SHA-256 differs from upstreams.json")
    return p


def series(repo, target=None):
    """The patches of `series`, then those of `series.<target>` if there is one."""
    out = []
    for s in (ROOT / "patches" / repo / "series", ROOT / "patches" / repo / f"series.{target}"):
        if s.exists():
            names = [l.split("#")[0].strip() for l in s.read_text().splitlines()]
            out += [ROOT / "patches" / repo / n for n in names if n]
    return out


def unpack(archive, dest, patches):
    top = dest / re.sub(r"\.tar\.(gz|xz)$", "", archive.name)
    shutil.rmtree(top, ignore_errors=True)
    with tarfile.open(archive) as t:
        t.extractall(dest, filter="data")
    for p in patches:
        run(["patch", "-p1", "-s", "-N", "-i", p], cwd=top)
    return top


def check_no_got(t, lib):
    rel = run([t["ar"][:-2] + "readelf", "-r", "-W", lib])
    n = len(re.findall(r"R_X86_64_(?:GOT\w*|PLTOFF64)|R_AARCH64_\w*GOT\w*", rel))
    if n:
        raise SystemExit(f"{lib}: {n} GOT relocations (PIC code), AROS cannot load these")


def compile_all(t, compiler, srcs, objdir, flags, logfile, work):
    shutil.rmtree(objdir, ignore_errors=True)
    objdir.mkdir(parents=True)
    objs = []
    for s in srcs:
        o = objdir / (s.stem + ".o")
        run([compiler, "--sysroot=" + t["sdk"]] + t["cflags"] + flags
            + [f"-ffile-prefix-map={work}=/deps", "-c", s, "-o", o], logfile=logfile)
        objs.append(o)
    return objs


def archive(t, lib, objs, logfile):
    lib.unlink(missing_ok=True)
    run([t["ar"], "rcsD", lib] + objs, logfile=logfile)
    return lib


C_FLAGS = ["-std=gnu99", "-Wall", "-Werror=implicit-function-declaration"]


def build_lua(t, work, out, logfile):
    """Lua 5.1.5, the plain interpreter library (no lua.c / luac.c)."""
    src = unpack(distfile("lua"), work, series("lua")) / "src"
    files = sorted(f for f in src.glob("*.c") if f.name not in ("lua.c", "luac.c", "print.c"))
    objs = compile_all(t, t["cc"], files, work / "lua-obj", C_FLAGS, logfile, work)
    for h in ("lua.h", "luaconf.h", "lualib.h", "lauxlib.h"):
        shutil.copy(src / h, out / "include" / h)
    shutil.copy(src.parent / "COPYRIGHT", out / "licenses/lua-COPYRIGHT")
    return archive(t, out / "lib/liblua51.a", objs, logfile)


def build_luajit(t, work, out, logfile):
    """LuaJIT (v2.1 branch at a pinned commit) through its own Makefile, as for an
    unknown system: static library, 64-bit GC (the default on x86_64), the C
    library's allocator instead of mmap, LuaJIT's own stack unwinding. buildvm
    and minilua are built with the build machine's compiler."""
    src = unpack(distfile("luajit"), work, series("luajit"))
    cc = Path(t["cc"])
    cross = str(cc)[: -len("gcc")]
    tflags = ["--sysroot=" + t["sdk"]] + [f for f in t["cflags"] if f.startswith("-m")] + [
        "-Werror=implicit-function-declaration", f"-ffile-prefix-map={work}=/deps"]
    run(["make", "-C", src / "src", "-j8", "libluajit.a", "HOST_CC=cc", "CROSS=" + cross, "CC=gcc",
         "TARGET_SYS=Other", "BUILDMODE=static", "TARGET_CFLAGS=" + " ".join(tflags),
         "XCFLAGS=-DLUAJIT_NO_UNWIND -DLUAJIT_USE_SYSMALLOC"], logfile=logfile)
    inc = out / "include/luajit"
    inc.mkdir(exist_ok=True)
    for h in ("lua.h", "luaconf.h", "lualib.h", "lauxlib.h", "luajit.h", "lua.hpp"):
        shutil.copy(src / "src" / h, inc / h)
    shutil.copy(src / "COPYRIGHT", out / "licenses/luajit-COPYRIGHT")
    lib = out / "lib/libluajit.a"
    shutil.copy(src / "src/libluajit.a", lib)
    return lib


def build_harfbuzz(t, work, out, logfile):
    """HarfBuzz as its one-file build (src/harfbuzz.cc), with FreeType support.
    HB_NO_MT: LÖVE shapes text on one thread at a time."""
    src = unpack(distfile("harfbuzz"), work, series("harfbuzz"))
    flags = ["-std=c++11", "-DHB_NO_MT", "-DHB_NO_MMAP", "-DHB_NO_SETLOCALE", "-DHAVE_FREETYPE=1",
             "-fno-exceptions", "-fno-rtti"]
    objs = compile_all(t, t["cxx"], [src / "src/harfbuzz.cc"], work / "harfbuzz-obj", flags, logfile, work)
    inc = out / "include/harfbuzz"
    inc.mkdir(exist_ok=True)
    for h in (src / "src").glob("hb*.h"):
        shutil.copy(h, inc / h.name)
    shutil.copy(src / "COPYING", out / "licenses/harfbuzz-COPYING")
    return archive(t, out / "lib/libharfbuzz.a", objs, logfile)


def build_libogg(t, work, out, logfile):
    src = unpack(distfile("libogg"), work, series("libogg"))
    (src / "include/ogg/config_types.h").write_text(
        "#ifndef __CONFIG_TYPES_H__\n#define __CONFIG_TYPES_H__\n#include <stdint.h>\n"
        "typedef int16_t ogg_int16_t;\ntypedef uint16_t ogg_uint16_t;\n"
        "typedef int32_t ogg_int32_t;\ntypedef uint32_t ogg_uint32_t;\n"
        "typedef int64_t ogg_int64_t;\ntypedef uint64_t ogg_uint64_t;\n#endif\n")
    objs = compile_all(t, t["cc"], [src / "src/bitwise.c", src / "src/framing.c"], work / "ogg-obj",
                       C_FLAGS + ["-I" + str(src / "include")], logfile, work)
    inc = out / "include/ogg"
    inc.mkdir(exist_ok=True)
    for h in ("ogg.h", "os_types.h", "config_types.h"):
        shutil.copy(src / "include/ogg" / h, inc / h)
    shutil.copy(src / "COPYING", out / "licenses/libogg-COPYING")
    return archive(t, out / "lib/libogg.a", objs, logfile)


def build_libvorbis(t, work, out, logfile):
    """Decoder, encoder and vorbisfile in one archive."""
    src = unpack(distfile("libvorbis"), work, series("libvorbis"))
    skip = ("psytune.c", "barkmel.c", "tone.c")
    files = sorted(f for f in (src / "lib").glob("*.c") if f.name not in skip)
    flags = C_FLAGS + ["-I" + str(src / "include"), "-I" + str(src / "lib"), "-I" + str(out / "include")]
    objs = compile_all(t, t["cc"], files, work / "vorbis-obj", flags, logfile, work)
    inc = out / "include/vorbis"
    inc.mkdir(exist_ok=True)
    for h in ("codec.h", "vorbisfile.h", "vorbisenc.h"):
        shutil.copy(src / "include/vorbis" / h, inc / h)
    shutil.copy(src / "COPYING", out / "licenses/libvorbis-COPYING")
    return archive(t, out / "lib/libvorbis.a", objs, logfile)


def build_libtheora(t, work, out, logfile):
    """The decoder (th_* API), portable C paths only."""
    src = unpack(distfile("libtheora"), work, series("libtheora"))
    names = ["bitpack", "decinfo", "decode", "dequant", "fragment", "huffdec", "idct", "info",
             "internal", "quant", "state"]
    flags = C_FLAGS + ["-I" + str(src / "include"), "-I" + str(out / "include")]
    objs = compile_all(t, t["cc"], [src / "lib" / (n + ".c") for n in names], work / "theora-obj",
                       flags, logfile, work)
    inc = out / "include/theora"
    inc.mkdir(exist_ok=True)
    for h in ("codec.h", "theoradec.h"):
        shutil.copy(src / "include/theora" / h, inc / h)
    shutil.copy(src / "COPYING", out / "licenses/libtheora-COPYING")
    return archive(t, out / "lib/libtheoradec.a", objs, logfile)


def build_libmodplug(t, work, out, logfile):
    """Tracker music decoder (MOD, S3M, XM, IT and others), the version and
    the options of AROS contrib's recipe (MultiMedia/libs/modplug), whose AROS
    diff is empty. Compiled directly: its configure script only finds the
    four things defined here."""
    src = unpack(distfile("libmodplug"), work, series("libmodplug")) / "src"
    flags = ["-std=gnu++98", "-D_GNU_SOURCE", "-DMODPLUG_STATIC", "-DHAVE_STDINT_H", "-DHAVE_INTTYPES_H",
             "-DHAVE_SETENV", "-DHAVE_SINF", "-fno-exceptions", "-I" + str(src), "-I" + str(src / "libmodplug")]
    objs = compile_all(t, t["cxx"], sorted(src.glob("*.cpp")), work / "modplug-obj", flags, logfile, work)
    inc = out / "include/libmodplug"
    inc.mkdir(exist_ok=True)
    shutil.copy(src / "modplug.h", inc / "modplug.h")
    shutil.copy(src.parent / "COPYING", out / "licenses/libmodplug-COPYING")
    return archive(t, out / "lib/libmodplug.a", objs, logfile)


def build_openal(t, work, out, logfile):
    """OpenAL Soft through its CMake build: static, output through SDL3 (the
    aros-sdl kit, which plays through AHI) plus the null device, HRTF data
    embedded, no tools or examples."""
    src = unpack(distfile("openal-soft"), work, series("openal-soft", t["target"]))
    bld = work / "openal-build"
    shutil.rmtree(bld, ignore_errors=True)
    flags = " ".join([f for f in t["cflags"] if f != "-O2"] + [f"-ffile-prefix-map={work}=/deps"])
    run(["cmake", "-S", src, "-B", bld, "-G", "Unix Makefiles",
         f"-DCMAKE_TOOLCHAIN_FILE={ROOT}/cmake/aros.cmake", "-DCMAKE_BUILD_TYPE=Release",
         f"-DAROS_CC={t['cc']}", f"-DAROS_CXX={t['cxx']}", f"-DAROS_AR={t['ar']}", f"-DAROS_SDK={t['sdk']}",
         "-DAROS_CFLAGS=" + flags, "-DCMAKE_POSITION_INDEPENDENT_CODE=OFF",
         "-DLIBTYPE=STATIC", "-DALSOFT_UTILS=OFF", "-DALSOFT_EXAMPLES=OFF", "-DALSOFT_TESTS=OFF",
         "-DALSOFT_NO_CONFIG_UTIL=ON", "-DALSOFT_INSTALL=OFF",
         "-DALSOFT_BACKEND_SDL3=ON", "-DALSOFT_REQUIRE_SDL3=ON", "-DALSOFT_BACKEND_SDL2=OFF",
         "-DALSOFT_BACKEND_WAVE=OFF", f"-DSDL3_DIR={t['sdl_kit']}/lib/cmake/SDL3"], logfile=logfile)
    run(["cmake", "--build", bld, "-j", "8"], logfile=logfile)
    inc = out / "include/AL"
    inc.mkdir(exist_ok=True)
    for h in (src / "include/AL").glob("*.h"):
        shutil.copy(h, inc / h.name)
    shutil.copy(src / "COPYING", out / "licenses/openal-soft-COPYING")
    lib = out / "lib/libopenal.a"
    shutil.copy(bld / "libopenal.a", lib)
    return lib


def build_unwind_fix(t, work, out, logfile, variant="fixed"):
    """Mainline x86_64 GCC 10.5 toolchains built before AROS 52bab89955 have a
    libgcc unwinder without its register size table: every C++ throw aborts.
    Rebuild libgcc's own unwind-dw2.c without the AROS guard around
    __builtin_init_dwarf_reg_size_table. Needs the configured GCC build tree
    ("gcc_build" in local.json). variant="stock" rebuilds the unchanged source,
    to compare it with the toolchain's object."""
    g0 = Path(t["gcc_build"])
    g = g0 / "gen/host/tools/crosstools/gnu/gcc"
    p = g0 / "Ports/host/gcc/gcc-10.5.0/libgcc"
    tc = Path(t["cc"]).parent
    d = work / ("unwind-" + variant)
    d.mkdir(parents=True, exist_ok=True)
    src = (p / "unwind-dw2.c").read_text()
    if variant == "fixed":
        guarded = ("#ifdef MD_FALLBACK_FRAME_STATE_FOR\n"
                   "  __builtin_init_dwarf_reg_size_table (dwarf_reg_size_table);\n#endif\n")
        if guarded not in src:
            raise SystemExit("unwind-dw2.c: AROS guard not found; is this toolchain already fixed?")
        src = src.replace(guarded, "  __builtin_init_dwarf_reg_size_table (dwarf_reg_size_table);\n")
    (d / "unwind-dw2.c").write_text(src)
    run([g / "gcc/xgcc", f"-B{g}/gcc/", f"-B{tc}/x86_64-aros/bin/", f"-B{tc}/x86_64-aros/lib/",
         "-isystem", f"{tc}/x86_64-aros/include", "-isystem", f"{tc}/x86_64-aros/sys-include",
         "-mcmodel=large", "-O2", "-DIN_GCC", "-DCROSS_DIRECTORY_STRUCTURE", "-isystem", "./include",
         "-DIN_LIBGCC2", "-fbuilding-libgcc", "-fno-stack-protector", "-I.", "-I../.././gcc",
         f"-I{p}", f"-I{p}/../gcc", f"-I{p}/../include", "-fexceptions", "-fvisibility=hidden",
         "-DHIDE_EXPORTS", "-c", d / "unwind-dw2.c", "-o", d / "unwind-dw2.o"],
        cwd=g / "x86_64-aros/libgcc", logfile=logfile)
    obj = d / "unwind-dw2.o"
    if variant == "fixed":
        if not re.search(r" dwarf_reg_size_table$", run([t["ar"][:-2] + "nm", obj]), re.M):
            raise SystemExit("unwind fix not effective: no dwarf_reg_size_table")
        shutil.copy(obj, out / "lib/unwind-dw2-fixed.o")
        return out / "lib/unwind-dw2-fixed.o"
    return obj


def build_emutls(t, work, out, logfile):
    """__emutls_get_address for Clang targets (support/aros_emutls.c)."""
    objs = compile_all(t, t["cc"], [ROOT / "support/aros_emutls.c"], work / "emutls-obj",
                       C_FLAGS + ["-Wextra"], logfile, work)
    return archive(t, out / "lib/libarosemutls.a", objs, logfile)


PARTS = (("lua", build_lua), ("luajit", build_luajit), ("harfbuzz", build_harfbuzz), ("libogg", build_libogg),
         ("libvorbis", build_libvorbis), ("libtheora", build_libtheora), ("libmodplug", build_libmodplug),
         ("openal-soft", build_openal))


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ARCH_CFLAGS:
        raise SystemExit("usage: deps.py " + "|".join(ARCH_CFLAGS))
    target = sys.argv[1]
    t = config(target)
    base = ROOT / "build" / target
    work, out = base / "deps-work", base / "deps"
    shutil.rmtree(out, ignore_errors=True)
    for d in (work, out / "lib", out / "include", out / "licenses"):
        d.mkdir(parents=True, exist_ok=True)
    logfile = base / "deps.log"
    logfile.unlink(missing_ok=True)
    info = {"target": target, "compiler": run([t["cc"], "--version"]).splitlines()[0], "parts": {}}
    for name, fn in PARTS:
        if name == "luajit" and target in NO_LUAJIT:
            continue
        print(f"{target}: {name}", flush=True)
        lib = fn(t, work, out, logfile)
        check_no_got(t, lib)
        d = MANIFEST["distfiles"][name]
        info["parts"][name] = {"source": d["file"], "sha256": d["sha256"],
                               "patches": [p.name for p in series(name, target)], "library_sha256": sha256(lib)}
    if "-femulated-tls" in ARCH_CFLAGS[target]:
        print(f"{target}: emulated TLS", flush=True)
        lib = build_emutls(t, work, out, logfile)
        check_no_got(t, lib)
        info["parts"]["emutls"] = {"source": "support/aros_emutls.c", "library_sha256": sha256(lib)}
    if target == "aros-x86_64-abiv1-pc" and t["gcc_build"]:
        print(f"{target}: unwind fix", flush=True)
        stock = build_unwind_fix(t, work, out, logfile, "stock")
        orig = work / "unwind-orig"
        orig.mkdir(exist_ok=True)
        run([t["ar"], "x", run([t["cc"], "-print-libgcc-file-name"]).strip(), "unwind-dw2.o"], cwd=orig)
        dis = lambda o: re.sub(r"^.*file format.*$", "", run([t["ar"][:-2] + "objdump", "-d", "-r", o]), flags=re.M)
        if dis(stock) != dis(orig / "unwind-dw2.o"):
            raise SystemExit("rebuilt stock unwind-dw2.o differs from the toolchain's: recipe mismatch")
        fixed = build_unwind_fix(t, work, out, logfile)
        info["parts"]["unwind-fix"] = {"source": "toolchain GCC build tree libgcc/unwind-dw2.c, AROS guard removed",
                                       "stock_rebuild_matches": True, "object_sha256": sha256(fixed)}
    (out / "BUILD.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"deps: {out}")


if __name__ == "__main__":
    main()
