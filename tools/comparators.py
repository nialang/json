#!/usr/bin/env python3
"""Build the comparator harnesses for tools/bench.py into build/out/:
yyjson from build/vendor/yyjson (fetch it with tools/vendor.py) with an
optimizing C compiler, and serde_json with cargo. Each prints the same report
as the Nia harness, so tools/bench.py can run them side by side:

    python tools/bench.py --yyjson build/out/yyjson --serde build/out/serde

Pass --cc to choose the C compiler; for a fair comparison use the clang of the
LLVM release the Nia compiler is built with.
"""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""
ROOT = Path(__file__).resolve().parents[1]


def yyjson(cc, out):
    source = ROOT / "build/vendor/yyjson/src"
    if not source.is_dir():
        raise SystemExit(f"{source} not found: run tools/vendor.py")
    target = out / f"yyjson{EXE}"
    subprocess.run([cc, "-O3", "-DNDEBUG", f"-I{source}", str(ROOT / "bench/yyjson/main.c"),
                    str(source / "yyjson.c"), "-o", str(target)], check=True)
    print(f"built {target}")


def serde(out):
    target_dir = ROOT / "build/serde"
    subprocess.run(["cargo", "build", "--release", "--locked", "--quiet",
                    "--manifest-path", str(ROOT / "bench/serde/Cargo.toml"),
                    "--target-dir", str(target_dir)], check=True)
    target = out / f"serde{EXE}"
    shutil.copy2(target_dir / "release" / f"nia-json-serde-bench{EXE}", target)
    print(f"built {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cc", default="clang" if os.name == "nt" else "cc")
    parser.add_argument("--only", choices=["yyjson", "serde"])
    args = parser.parse_args()
    out = ROOT / "build/out"
    out.mkdir(parents=True, exist_ok=True)
    if args.only != "serde":
        yyjson(args.cc, out)
    if args.only != "yyjson":
        serde(out)


if __name__ == "__main__":
    main()
