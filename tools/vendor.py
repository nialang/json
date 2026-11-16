#!/usr/bin/env python3
"""Fetch the third-party sources the tests and benchmarks use, at pinned
revisions, into build/vendor/: JSONTestSuite for tools/check.py and
tools/diff.py, and yyjson for the C comparator. Needs git."""
import argparse
import subprocess
from pathlib import Path

SOURCES = {
    "JSONTestSuite": ("https://github.com/nst/JSONTestSuite.git",
                      "1ef36fa01286573e846ac449e8683f8833c5b26a"),
    "yyjson": ("https://github.com/ibireme/yyjson.git",
               "8b4a38dc994a110abaec8a400615567bd996105f"),  # 0.12.0
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
