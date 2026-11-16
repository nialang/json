#!/usr/bin/env python3
"""Measure parsing, parsing into reused storage, writing, and round trips on
deterministic workloads, for the Nia harness and any comparators given.

Each sample is a fresh process that reads the corpus on stdin and reports the
time of its measured loop; the medians, every sample, and the corpus hashes
are written to --output. See docs/benchmarks.md for the method, and
tools/comparators.py to build the yyjson and serde_json comparators.
"""
import argparse
import hashlib
import json
import os
import platform
import random
import re
import statistics
import subprocess
import time
from pathlib import Path


EXE = ".exe" if os.name == "nt" else ""


def corpora():
    row = {"id": 12345, "name": "nia", "active": True,
           "values": [1, -2, 3.25, None], "meta": {"region": "east", "revision": 3}}
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return {
        "small": (Path(__file__).resolve().parents[1] / "bench/corpus.json").read_bytes(),
        "records-1k": encode([row] * 8),
        "records-100k": encode([row] * 800),
        "records-2m": encode([row] * 16000),
        "integers-100k": encode(list(range(18000))),
        "strings-100k": encode(["plain text without escapes " * 16] * 240),
        "unicode-100k": encode(["中文é𝄞 " * 24] * 300),
        "escapes-100k": encode([("a" + chr(10) + chr(9) + chr(34) + chr(92)) * 32] * 300),
        # The same records as written for people: indented by spaces or tabs,
        # with LF or CRLF line ends, so whitespace is over half the bytes.
        "records-pretty": json.dumps([row] * 800, indent=2).encode(),
        "records-tabs": json.dumps([row] * 800, indent="\t").encode(),
        "records-crlf": json.dumps([row] * 800, indent=2).replace("\n", "\r\n").encode(),
        "mixed-100k": encode(mixed(290)),
    }


def mixed(count):
    """Messages shaped like an API feed: large ids, text of every length with
    some Unicode and escapes, nested objects, coordinates, flags and nulls."""
    rng = random.Random(20261115)
    words = ["nia", "json", "parse", "value", "東京", "café", "naïve", "😀", "line\nbreak",
             "say \"hi\"", "path\\to", "tab\tthere", "data", "fast", "small", "x"]

    def text(low, high):
        return " ".join(rng.choice(words) for _ in range(rng.randint(low, high)))

    messages = []
    for index in range(count):
        messages.append({
            "id": 1_400_000_000_000_000_000 + index * 7919,
            "created": "2026-11-%02dT%02d:%02d:%02dZ" % (1 + index % 28, index % 24, index % 60, index * 7 % 60),
            "text": text(0, 24),
            "user": {"id": rng.randint(1, 10**9), "name": text(1, 2), "verified": rng.random() < 0.1,
                     "followers": rng.randint(0, 10**6), "bio": text(0, 12) or None},
            "tags": [text(1, 1) for _ in range(rng.randint(0, 4))],
            "geo": None if rng.random() < 0.6 else [round(rng.uniform(-90, 90), 6), round(rng.uniform(-180, 180), 6)],
            "score": round(rng.random() * 100, 3),
            "replies": rng.randint(0, 500),
        })
    return messages


def count_nodes(value):
    """Count every tape value: scalars, containers, and object keys."""
    if isinstance(value, list):
        return 1 + sum(map(count_nodes, value))
    if isinstance(value, dict):
        # Keys are string tape values; count them plus each value recursively.
        return 1 + len(value) + sum(map(count_nodes, value.values()))
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nia", default=f"build/out/bench{EXE}")
    parser.add_argument("--serde")
    parser.add_argument("--yyjson")
    parser.add_argument("--simdjson")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--megabytes", type=int, default=32)
    parser.add_argument("--output", type=Path, default=Path("build/benchmark.json"))
    parser.add_argument("--corpus", action="append")
    args = parser.parse_args()
    if args.repeat < 1 or args.megabytes < 1:
        parser.error("repeat and megabytes must be positive")
    implementations = [("nia", str(Path(args.nia).resolve()))]
    for name in ("serde", "yyjson", "simdjson"):
        if getattr(args, name):
            implementations.append((name, str(Path(getattr(args, name)).resolve())))
    result = {"schema": 2, "platform": platform.platform(), "processor": platform.processor(),
              "python": platform.python_version(), "repeat": args.repeat,
              "method": ("fresh process per sample; binary stdin; each harness times only its "
                         "measured loop with a monotonic clock (elapsed_ns); counting sink"),
              "samples": []}
    for name, data in corpora().items():
        if args.corpus and name not in args.corpus:
            continue
        iterations = max(2, args.megabytes * 1_000_000 // len(data))
        nodes = count_nodes(json.loads(data)) * iterations
        for mode in ("parse", "reuse", "write", "roundtrip"):
            for implementation, binary in implementations:
                if mode == "reuse" and implementation != "nia":
                    continue
                command = [binary, mode, str(iterations)]
                # One fresh-process warmup before the measured processes.
                subprocess.run(command, input=data, capture_output=True, check=True, timeout=120)
                samples = []
                process_seconds = []
                metrics = None
                for _ in range(args.repeat):
                    start = time.perf_counter()
                    run = subprocess.run(command, input=data, capture_output=True, check=True, timeout=120)
                    process_seconds.append(time.perf_counter() - start)
                    observed = {key: int(value) for key, value in re.findall(
                        r"(iterations|nodes|input_bytes|output_bytes|elapsed_ns)=(\d+)",
                        (run.stdout + run.stderr).decode())}
                    elapsed_ns = observed.pop("elapsed_ns", None)
                    if not elapsed_ns:
                        raise RuntimeError(f"{implementation}/{name}/{mode}: no elapsed_ns reported")
                    samples.append(elapsed_ns / 1e9)
                    for key, expected in {"iterations": iterations, "nodes": nodes, "input_bytes": len(data)}.items():
                        if observed.get(key) != expected:
                            raise RuntimeError(f"{implementation}/{name}/{mode}: {key}: {observed.get(key)} != {expected}")
                    if metrics is not None and observed != metrics:
                        raise RuntimeError("inconsistent metrics between processes")
                    metrics = observed
                median = statistics.median(samples)
                record = {"implementation": implementation, "corpus": name, "mode": mode,
                          "sha256": hashlib.sha256(data).hexdigest(), "seconds": samples,
                          "process_seconds": process_seconds,
                          "median_seconds": median, "mb_per_second": iterations * len(data) / median / 1e6,
                          **metrics}
                result["samples"].append(record)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print(f"{name:18} {mode:10} {implementation:8} {record['mb_per_second']:9.1f} MB/s", flush=True)


if __name__ == "__main__":
    main()
