#!/usr/bin/env python3
"""Interleaved A/B of bench executables on the corpora of tools/bench.py: the
executables alternate every sample, so drift of the machine hits each alike,
and the median MB/s of each is reported with its ratio to the first.

    python tools/ab.py build/out/bench-old,build/out/bench parse records-100k,mixed-100k
"""
import argparse
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import corpora  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("binaries", help="comma-separated bench executables; the first is the baseline")
    parser.add_argument("mode", choices=["parse", "reuse", "write", "roundtrip"])
    parser.add_argument("corpora", help="comma-separated corpus names from tools/bench.py")
    parser.add_argument("rounds", type=int, nargs="?", default=15)
    parser.add_argument("--megabytes", type=int, default=16, help="input processed per sample")
    args = parser.parse_args()
    binaries = [str(Path(b).resolve()) for b in args.binaries.split(",")]
    available = corpora()
    for name in args.corpora.split(","):
        if name not in available:
            parser.error(f"unknown corpus {name}; known: {', '.join(available)}")
        data = available[name]
        iterations = max(2, args.megabytes * 1_000_000 // len(data))
        samples = {binary: [] for binary in binaries}
        for _ in range(args.rounds):
            for binary in binaries:
                run = subprocess.run([binary, args.mode, str(iterations)], input=data,
                                     capture_output=True, check=True)
                ns = int(re.search(rb"elapsed_ns=(\d+)", run.stdout + run.stderr).group(1))
                samples[binary].append(iterations * len(data) / (ns / 1e9) / 1e6)
        medians = [statistics.median(samples[binary]) for binary in binaries]
        print(f"{name:16} " + "  ".join(f"{Path(b).stem}={m:8.1f}" for b, m in zip(binaries, medians))
              + "  " + " ".join(f"r{i}={m / medians[0]:.3f}" for i, m in enumerate(medians) if i))


if __name__ == "__main__":
    main()
