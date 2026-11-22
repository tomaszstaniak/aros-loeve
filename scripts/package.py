#!/usr/bin/env python3
"""Make the AROS package of a LÖVE build and its LGPL relink kit.

    python3 scripts/package.py <target> <release>        e.g. 12.0-aros1

Reads build/<target>/love (scripts/build.py). Writes build/<target>/package:

    LOVE/ + LOVE.info                       the drawer users install
    love-<release>-<target>.zip             the drawer packed by apkg-pack
    love-<release>-<target>-lgpl-kit.zip    what is needed to link love again
                                            with a changed OpenAL Soft or
                                            libiconv (LGPL 2.1, section 6)
    SHA256SUMS

apkg-pack.pyz is named by local.json "apkg_pack" or APKG_PACK.

The kit holds every file named on the link line; the compiler's own
libraries, the start-up files and the system link libraries come from the
compiler and the SDK. The kit's link.sh is run on an unpacked copy and must
give the program that was built. The package and the kit are refused if a file in them contains a
path of the build machine's user directory.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deps  # noqa: E402

ROOT = deps.ROOT
TARGETS = {
    "aros-x86_64-abiv1-pc": ("x86_64", "v1", "mainline AROS (ABIv1) on x86_64"),
}
# Libraries and devices the program opens (strings of the linked program,
# checked against what the linked code calls).
SYSTEM = {
    "aros-x86_64-abiv1-pc": [
        "stdc.library", "stdcio.library", "posixc.library", "gl.library", "cybergraphics.library",
        "png.library", "icon.library", "workbench.library", "iffparse.library", "keymap.library",
        "lowlevel.library", "gadtools.library", "commodities.library", "muimaster.library",
        "openurl.library",
    ],
}
REPOSITORY = "https://github.com/tomaszstaniak/aros-loeve"
STRIP_FLAGS = ["--strip-unneeded", "--remove-section", ".comment"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode:
        raise SystemExit(f"package: {' '.join(str(c) for c in cmd[:3])} ... failed\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def no_user_paths(top):
    """Nothing delivered may name the build machine's user directory."""
    home = str(Path.home()).encode()
    for p in sorted(Path(top).rglob("*")):
        if p.is_file() and (home in p.read_bytes() or home in str(p.relative_to(top)).encode()):
            raise SystemExit(f"package: {p} contains a path under the user directory")


def link_command(bld):
    """CMake's link line for love, as a list."""
    words = (bld / "CMakeFiles/love.dir/link.txt").read_text().split()
    return words


def make_drawer(a, t, bld, stage, release, version, revision):
    arch, abi, system = TARGETS[a.target]
    drawer = stage / "LOVE"
    drawer.mkdir(parents=True)
    exe = drawer / "love"
    shutil.copyfile(bld / "love", exe)
    strip = Path(t["cc"]).with_name(Path(t["cc"]).name.replace("gcc", "strip"))
    run([strip] + STRIP_FLAGS + [exe])

    pin = json.loads((ROOT / "upstreams.json").read_text())["repositories"]["love"]["commit"]
    kit = f"love-{release}-{a.target}-lgpl-kit.zip"
    text = (ROOT / "packaging/ReadMe.txt.in").read_text()
    for k, v in (("@VERSION@", version), ("@COMMIT@", pin[:12]), ("@SYSTEM@", system),
                 ("@REPOSITORY@", REPOSITORY), ("@KIT@", kit)):
        text = text.replace(k, v)
    # AROS text viewers read ISO-8859-1.
    (drawer / "ReadMe.txt").write_bytes(text.encode("iso-8859-1"))

    lic = drawer / "licenses"
    lic.mkdir()
    shutil.copyfile(ROOT / "work/love/license.txt", lic / "love-license.txt")
    for src in (ROOT / "build" / a.target / "deps/licenses", Path(t["sdl_kit"]) / "licenses"):
        for f in sorted(src.iterdir()):
            shutil.copyfile(f, lic / f.name)
    for f in sorted(Path(t["crypto_kit"]).glob("LICENSE.*")):
        shutil.copyfile(f, lic / ("aros-crypto-" + f.name))

    icon = ROOT / "packaging/love-icon.png"
    mk = [sys.executable, ROOT / "scripts/make-icon.py", icon]
    run(mk + [drawer / "love.info", "--type", "tool", "--stack", "8000000"])
    run(mk + [stage / "LOVE.info", "--type", "drawer"])
    # The picture "love --icon <game>" copies for a game's icon.
    run(mk + [drawer / "Game.info", "--type", "project"])

    toml = (ROOT / "packaging/LOVE.arospkg.toml.in").read_text()
    for k, v in (("@VERSION@", version), ("@REVISION@", str(revision)), ("@ARCH@", arch), ("@ABI@", abi)):
        toml = toml.replace(k, v)
    for lib in SYSTEM[a.target]:
        toml += f'\n[[requires_system]]\ntype = "library"\nid = "{lib}"\n'
    toml += f'\n[source]\nrepository = "{REPOSITORY}"\nrevision = "v{release}"\n'
    toml += '\n[launch]\nexecutable = "love"\nmode       = "workbench"\n'
    (stage / "LOVE.arospkg.toml").write_text(toml)

    manifest = {
        "schema": 1,
        "application": "LOVE",
        "version": version,
        "release": release,
        "target": a.target,
        "source": {
            "upstream": "https://github.com/love2d/love",
            "base_commit": pin,
            "patch_series": "patches/love/series (%d patches)" % sum(
                1 for l in (ROOT / "patches/love/series").read_text().split() if l.endswith(".patch")),
        },
        "build": {
            "compiler": run([t["cc"], "--version"]).splitlines()[0],
            "unstripped_binary_sha256": sha256(bld / "love"),
            "binary_sha256": sha256(exe),
            "binary_size": exe.stat().st_size,
            "strip_flags": STRIP_FLAGS,
        },
    }
    (drawer / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return drawer


def pack(a, t, stage, drawer, release):
    tool = os.environ.get("APKG_PACK") or json.loads((ROOT / "local.json").read_text())[a.target].get("apkg_pack", "")
    if not tool or not Path(tool).exists():
        raise SystemExit("package: set local.json 'apkg_pack' or APKG_PACK to apkg-pack.pyz")
    out = stage / f"love-{release}-{a.target}.zip"
    run([sys.executable, tool, "check", drawer])
    run([sys.executable, tool, "build", drawer, "--output", out])
    run([sys.executable, tool, "check", out])
    with zipfile.ZipFile(out) as z:
        if z.testzip():
            raise SystemExit("package: the archive does not read back")
        chk = stage / "readback"
        z.extractall(chk)
    for p in sorted(drawer.rglob("*")):
        if p.is_file() and p.read_bytes() != (chk / "LOVE" / p.relative_to(drawer)).read_bytes():
            raise SystemExit(f"package: {p} differs in the archive")
    no_user_paths(chk)
    shutil.rmtree(chk)
    return out


def make_kit(a, t, bld, stage, release):
    """The relink kit: the files named on the link line, and a script that repeats it."""
    want = sha256(bld / "love")
    words = link_command(bld)
    cxx, args = words[0], words[1:]
    tmp = stage / "kit-work"
    tmp.mkdir()
    name = f"love-{release}-{a.target}-lgpl-kit"
    kit = stage / name
    (kit / "files").mkdir(parents=True)

    # The link line again, with the kit's copies in place of the build's files.
    line_out, taken = [], set()
    skip = False
    for w in args:
        p = Path(w) if w.startswith("/") else bld / w
        if skip:
            skip = False
        elif w == "-o":
            skip = True
            line_out.append('-o "$out"')
        elif w.startswith("--sysroot="):
            line_out.append('--sysroot="$sysroot"')
        elif not w.startswith("-") and p.is_file():
            base, n = p.name, 1
            while base in taken:
                n += 1
                base = f"{p.stem}-{n}{p.suffix}"
            taken.add(base)
            shutil.copyfile(p, kit / "files" / base)
            line_out.append('"$here/files/%s"' % base)
        elif w.startswith("/"):
            raise SystemExit(f"package: link input {w} is missing")
        else:
            line_out.append(w)
    script = """#!/bin/sh
# Link love again from the files of this kit.
#
#   sh link.sh <x86_64-aros-g++> <AROS Developer SDK> [output]
#
# Replace a file in files/ (libopenal.a, libiconv.a) with your own build of
# that library first. The compiler's own libraries, the start-up files and
# the system link libraries come from your compiler and SDK.
set -e
[ $# -ge 2 ] || { echo "usage: sh link.sh <x86_64-aros-g++> <AROS Developer SDK> [output]" >&2; exit 2; }
here=$(cd "$(dirname "$0")" && pwd)
cxx=$1; sysroot=$2; out=${3:-love}
"$cxx" %s
echo "linked $out"
""" % " ".join(line_out)
    (kit / "link.sh").write_text(script)
    (kit / "README.txt").write_text(f"""LGPL relink kit for love {release} ({a.target})

love is linked statically with OpenAL Soft and GNU libiconv, which are under
the GNU Lesser General Public License 2.1. This kit holds the object files
and libraries love was linked from, so that you can link the program again
with a changed version of those libraries:

    sh link.sh <x86_64-aros-g++> <AROS Developer SDK> love

Built with {run([cxx, "--version"]).splitlines()[0]} and the Developer SDK
of the mainline AROS nightly of 2026-11-10. With that compiler and SDK and
the files unchanged, the result is the program of the package before it was
stripped (SHA-256 {want}).

files/libopenal.a   OpenAL Soft 1.24.3, https://openal-soft.org
files/libiconv.a    GNU libiconv 1.19, https://www.gnu.org/software/libiconv/

The licence texts are in the package's licenses drawer. How the libraries
were built: {REPOSITORY} (scripts/deps.py) and
https://github.com/tomaszstaniak/aros-sdl (libiconv).
""")
    no_user_paths(kit)

    # The kit has to work on its own: link from an unpacked copy.
    out = stage / f"{name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(kit.rglob("*")):
            if p.is_file():
                z.write(p, Path(name) / p.relative_to(kit))
    chk = tmp / "unpacked"
    with zipfile.ZipFile(out) as z:
        z.extractall(chk)
    run(["sh", chk / name / "link.sh", cxx, t["sdk"], tmp / "love-from-kit"], cwd=tmp)
    if sha256(tmp / "love-from-kit") != want:
        raise SystemExit("package: the kit's link.sh does not give the built program")
    shutil.rmtree(tmp)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=list(TARGETS))
    ap.add_argument("release", help="<LÖVE version>-aros<revision>, e.g. 12.0-aros1")
    a = ap.parse_args()
    m = re.fullmatch(r"(\d+\.\d+(?:\.\d+)?)-aros(\d+)", a.release)
    if not m:
        raise SystemExit("package: the release name is <version>-aros<number>")
    version, revision = m.group(1), int(m.group(2))
    t = deps.config(a.target)
    bld = ROOT / "build" / a.target / "love"
    if not (bld / "love").exists():
        raise SystemExit("package: no build; run scripts/build.py")
    stage = ROOT / "build" / a.target / "package"
    if stage.exists():
        shutil.rmtree(stage)
    drawer = make_drawer(a, t, bld, stage, a.release, version, revision)
    archive = pack(a, t, stage, drawer, a.release)
    kit = make_kit(a, t, bld, stage, a.release)
    sums = "".join(f"{sha256(p)}  {p.name}\n" for p in (archive, kit))
    (stage / "SHA256SUMS").write_text(sums)
    print(sums, end="")


if __name__ == "__main__":
    main()
