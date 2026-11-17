#!/usr/bin/env python3
"""Build the comparator harnesses for tools/bench.py into build/out/:

- yyjson and cJSON with an optimizing C compiler,
- simdjson, RapidJSON, and nlohmann/json with a C++ compiler,
- serde_json and sonic-rs with cargo,

each from the sources tools/vendor.py fetches, or from crates.io at the
versions bench/*/Cargo.lock pins. Every harness prints the same report as the
Nia harness, so tools/bench.py can run them side by side:

    python tools/bench.py --comparators build/out

Pass --cc and --cxx to choose the compilers; for a fair comparison use the
clang of the LLVM release the Nia compiler is built with. Every library is
built for the baseline of the target, as the Nia library is; simdjson
chooses its SIMD kernels at run time either way.
"""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""
ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "build/vendor"


def vendored(name):
    path = VENDOR / name
    if not path.is_dir():
        raise SystemExit(f"{path} not found: run tools/vendor.py")
    return path


def compile_c(compiler, name, sources, includes, out, standard):
    target = out / f"{name}{EXE}"
    command = [compiler, "-O3", "-DNDEBUG", f"-std={standard}"]
    command += [f"-I{include}" for include in includes]
    command += [str(source) for source in sources] + ["-o", str(target)]
    subprocess.run(command, check=True)
    print(f"built {target}")


def yyjson(args, out):
    source = vendored("yyjson") / "src"
    compile_c(args.cc, "yyjson", [ROOT / "bench/yyjson/main.c", source / "yyjson.c"],
              [source], out, "c11")


def cjson(args, out):
    source = vendored("cJSON")
    compile_c(args.cc, "cjson", [ROOT / "bench/cjson/main.c", source / "cJSON.c"],
              [source], out, "c11")


def simdjson(args, out):
    source = vendored("simdjson") / "singleheader"
    compile_c(args.cxx, "simdjson", [ROOT / "bench/simdjson/main.cpp", source / "simdjson.cpp"],
              [source], out, "c++17")


def rapidjson(args, out):
    compile_c(args.cxx, "rapidjson", [ROOT / "bench/rapidjson/main.cpp"],
              [vendored("rapidjson") / "include"], out, "c++17")


def nlohmann(args, out):
    compile_c(args.cxx, "nlohmann", [ROOT / "bench/nlohmann/main.cpp"],
              [vendored("nlohmann") / "single_include"], out, "c++17")


def cargo(name, package, out):
    target_dir = ROOT / "build/cargo"
    subprocess.run(["cargo", "build", "--release", "--locked", "--quiet",
                    "--manifest-path", str(ROOT / f"bench/{name}/Cargo.toml"),
                    "--target-dir", str(target_dir)], check=True)
    target = out / f"{name}{EXE}"
    shutil.copy2(target_dir / "release" / f"{package}{EXE}", target)
    print(f"built {target}")


BUILDERS = {
    "yyjson": yyjson,
    "simdjson": simdjson,
    "rapidjson": rapidjson,
    "sonic": lambda args, out: cargo("sonic", "nia-json-sonic-bench", out),
    "serde": lambda args, out: cargo("serde", "nia-json-serde-bench", out),
    "nlohmann": nlohmann,
    "cjson": cjson,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cc", default="clang" if os.name == "nt" else "cc")
    parser.add_argument("--cxx", default="clang++" if os.name == "nt" else "c++")
    parser.add_argument("--only", choices=sorted(BUILDERS), action="append",
                        help="build only this comparator; may be repeated")
    args = parser.parse_args()
    out = ROOT / "build/out"
    out.mkdir(parents=True, exist_ok=True)
    for name, build in BUILDERS.items():
        if args.only is None or name in args.only:
            build(args, out)


if __name__ == "__main__":
    main()
