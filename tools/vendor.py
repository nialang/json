#!/usr/bin/env python3
"""Fetch the third-party sources the tests and benchmarks use, at pinned
revisions, into build/vendor/: JSONTestSuite for tools/check.py and
tools/diff.py, the C and C++ libraries the comparators build, and from
nativejson-benchmark the real-world documents tools/bench.py measures. Needs
git."""
import argparse
import subprocess
from pathlib import Path

SOURCES = {
    "JSONTestSuite": ("https://github.com/nst/JSONTestSuite.git",
                      "1ef36fa01286573e846ac449e8683f8833c5b26a"),
    "yyjson": ("https://github.com/ibireme/yyjson.git",
               "8b4a38dc994a110abaec8a400615567bd996105f"),  # 0.12.0
    "simdjson": ("https://github.com/simdjson/simdjson.git",
                 "a0d5ad9798f9e51706399b649929dafb91d9b714"),  # 5.2.0
    # The last release, 1.1.0, is from 2016 and does not build with current
    # compilers; this is the head of master.
    "rapidjson": ("https://github.com/Tencent/rapidjson.git",
                  "297637bc0a0f00dc504dbc1a47ebdaa577f8ae19"),
    "nlohmann": ("https://github.com/nlohmann/json.git",
                 "55f93686c01528224f448c19128836e7df245f72"),  # 3.12.0
    "cJSON": ("https://github.com/DaveGamble/cJSON.git",
              "c859b25da02955fef659d658b8f324b5cde87be3"),  # 1.7.19
    # twitter.json, citm_catalog.json, and canada.json, in data/.
    "nativejson-benchmark": ("https://github.com/miloyip/nativejson-benchmark.git",
                             "478d5727c2a4048e835a29c65adecc7d795360d5"),
}


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def fetch(name, url, revision, root):
    path = root / name
    if path.exists():
        current = git("rev-parse", "HEAD", cwd=path)
        if current == revision:
            print(f"{name}: at {revision[:12]}")
            return
        raise SystemExit(f"{name}: {path} is at {current}, expected {revision}; remove it to fetch again")
    path.mkdir(parents=True)
    git("init", "--quiet", cwd=path)
    git("remote", "add", "origin", url, cwd=path)
    git("fetch", "--quiet", "--depth", "1", "origin", revision, cwd=path)
    git("checkout", "--quiet", "FETCH_HEAD", cwd=path)
    print(f"{name}: fetched {revision[:12]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("build/vendor"))
    args = parser.parse_args()
    for name, (url, revision) in SOURCES.items():
        fetch(name, url, revision, args.root)


if __name__ == "__main__":
    main()
