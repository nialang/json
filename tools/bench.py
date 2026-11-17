#!/usr/bin/env python3
"""Measure parsing, parsing into reused storage, writing, and round trips on
deterministic workloads, for the Nia harness and any comparators given, and
with --memory the memory a parsed document takes.

Each sample is a fresh process that reads the corpus on stdin and reports the
time of its measured loop; the medians, every sample, and the corpus hashes
are written to --output. See docs/benchmarks.md for the method, and
tools/comparators.py to build the comparators:

    python tools/bench.py --comparators build/out
    python tools/bench.py --comparators build/out --memory --output build/memory.json
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
import tempfile
import time
from pathlib import Path


EXE = ".exe" if os.name == "nt" else ""
ROOT = Path(__file__).resolve().parents[1]
# The comparators tools/comparators.py builds, by the name of their harness.
COMPARATORS = ["yyjson", "simdjson", "rapidjson", "sonic", "serde", "nlohmann", "cjson"]
# The libraries whose documents keep their storage from one parse to the next,
# which the `reuse` mode measures.
REUSE = {"nia", "simdjson"}
# The real-world documents of nativejson-benchmark, fetched by tools/vendor.py:
# a Twitter API response, a catalog of events, and the outline of Canada as
# GeoJSON coordinates.
STANDARD = ["twitter.json", "citm_catalog.json", "canada.json"]
STANDARD_DIR = ROOT / "build/vendor/nativejson-benchmark/data"


def corpora():
    row = {"id": 12345, "name": "nia", "active": True,
           "values": [1, -2, 3.25, None], "meta": {"region": "east", "revision": 3}}
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    result = {
        "small": (ROOT / "bench/corpus.json").read_bytes(),
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
    examples = STANDARD_DIR
    for name in STANDARD:
        if (examples / name).is_file():
            result[name.removesuffix(".json")] = (examples / name).read_bytes()
    return result


def memory_corpora():
    """Documents of about 20 MB, large enough that the memory a document takes
    stands well above what a process starts with."""
    row = {"id": 12345, "name": "nia", "active": True,
           "values": [1, -2, 3.25, None], "meta": {"region": "east", "revision": 3}}
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    result = {
        "records-20m": encode([row] * 200000),
        "integers-20m": encode(list(range(3_000_000))),
        "strings-20m": encode(["plain text without escapes " * 16] * 48000),
        "records-pretty-20m": json.dumps([row] * 90000, indent=2).encode(),
        "mixed-20m": encode(mixed(58000)),
    }
    examples = STANDARD_DIR
    for name in STANDARD:
        if (examples / name).is_file():
            result[name.removesuffix(".json")] = (examples / name).read_bytes()
    return result


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


REPORT = re.compile(r"(iterations|nodes|input_bytes|output_bytes|elapsed_ns)=(\d+)")


def report(output):
    return {key: int(value) for key, value in REPORT.findall(output.decode())}


def check(label, observed, expected):
    for key, value in expected.items():
        if observed.get(key) != value:
            raise RuntimeError(f"{label}: {key}: {observed.get(key)} != {value}")


def measure_speed(args, implementations, result):
    for name, data in corpora().items():
        if args.corpus and name not in args.corpus:
            continue
        iterations = max(2, args.megabytes * 1_000_000 // len(data))
        nodes = count_nodes(json.loads(data)) * iterations
        for mode in ("parse", "reuse", "write", "roundtrip"):
            for implementation, binary in implementations:
                if mode == "reuse" and implementation not in REUSE:
                    continue
                label = f"{implementation}/{name}/{mode}"
                command = [binary, mode, str(iterations)]
                # One fresh-process warmup before the measured processes.
                subprocess.run(command, input=data, capture_output=True, check=True, timeout=300)
                samples = []
                process_seconds = []
                metrics = None
                for _ in range(args.repeat):
                    start = time.perf_counter()
                    run = subprocess.run(command, input=data, capture_output=True, check=True, timeout=300)
                    process_seconds.append(time.perf_counter() - start)
                    observed = report(run.stdout + run.stderr)
                    elapsed_ns = observed.pop("elapsed_ns", None)
                    if not elapsed_ns:
                        raise RuntimeError(f"{label}: no elapsed_ns reported")
                    samples.append(elapsed_ns / 1e9)
                    check(label, observed, {"iterations": iterations, "nodes": nodes, "input_bytes": len(data)})
                    if metrics is not None and observed != metrics:
                        raise RuntimeError(f"{label}: inconsistent metrics between processes")
                    metrics = observed
                median = statistics.median(samples)
                record = {"implementation": implementation, "corpus": name, "mode": mode,
                          "sha256": hashlib.sha256(data).hexdigest(), "seconds": samples,
                          "process_seconds": process_seconds,
                          "median_seconds": median, "mb_per_second": iterations * len(data) / median / 1e6,
                          **metrics}
                result["samples"].append(record)
                write(args.output, result)
                print(f"{name:18} {mode:10} {implementation:10} {record['mb_per_second']:9.1f} MB/s", flush=True)


def peak_kilobytes(command, path, label):
    """Runs `command` with `path` on standard input and returns its report and
    its peak resident memory in kilobytes.

    GNU time starts the command: a child forked from this process would count
    this process's memory, which holds the corpora, in its own peak until it
    executes the command, and the peak never comes down again."""
    with tempfile.NamedTemporaryFile("r", suffix=".rss") as rss, open(path, "rb") as stdin:
        run = subprocess.run(["/usr/bin/time", "-f", "%M", "-o", rss.name, *command],
                             stdin=stdin, capture_output=True, timeout=300)
        if run.returncode != 0:
            raise RuntimeError(f"{label}: exit status {run.returncode}")
        kilobytes = int(rss.read().strip().splitlines()[-1])
    return report(run.stdout + run.stderr), kilobytes


def measure_memory(args, implementations, result):
    if not Path("/usr/bin/time").is_file():
        raise SystemExit("--memory needs GNU time at /usr/bin/time")
    with tempfile.TemporaryDirectory() as scratch:
        for name, data in memory_corpora().items():
            if args.corpus and name not in args.corpus:
                continue
            path = Path(scratch) / f"{name}.json"
            path.write_bytes(data)
            nodes = count_nodes(json.loads(data))
            for implementation, binary in implementations:
                label = f"{implementation}/{name}/memory"
                read_kb, load_kb, parse_seconds = [], [], []
                # Each sample pairs a process that only reads the input with
                # one that also parses it, run back to back.
                for _ in range(args.repeat):
                    observed, kilobytes = peak_kilobytes([binary, "read", "1"], path, label)
                    check(label, observed, {"input_bytes": len(data)})
                    read_kb.append(kilobytes)
                    observed, kilobytes = peak_kilobytes([binary, "load", "1"], path, label)
                    check(label, observed, {"iterations": 1, "nodes": nodes, "input_bytes": len(data)})
                    load_kb.append(kilobytes)
                    parse_seconds.append(observed["elapsed_ns"] / 1e9)
                document = statistics.median(load - read for load, read in zip(load_kb, read_kb)) * 1024
                record = {"implementation": implementation, "corpus": name, "mode": "memory",
                          "sha256": hashlib.sha256(data).hexdigest(), "input_bytes": len(data),
                          "nodes": nodes, "read_kilobytes": read_kb, "load_kilobytes": load_kb,
                          "parse_seconds": parse_seconds, "document_bytes": document,
                          "bytes_per_input_byte": document / len(data)}
                result["samples"].append(record)
                write(args.output, result)
                print(f"{name:20} {implementation:10} {document / 1e6:8.1f} MB  "
                      f"{record['bytes_per_input_byte']:5.2f}x input", flush=True)


def write(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--nia", default=f"build/out/bench{EXE}")
    parser.add_argument("--comparators", type=Path,
                        help="a directory holding comparator harnesses built by tools/comparators.py")
    for name in COMPARATORS:
        parser.add_argument(f"--{name}", help=f"the {name} harness, overriding --comparators")
    parser.add_argument("--memory", action="store_true",
                        help="measure the memory a parsed document takes instead of speed")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--megabytes", type=int, default=32)
    parser.add_argument("--output", type=Path, default=Path("build/benchmark.json"))
    parser.add_argument("--corpus", action="append")
    args = parser.parse_args()
    if args.repeat < 1 or args.megabytes < 1:
        parser.error("repeat and megabytes must be positive")
    implementations = [("nia", str(Path(args.nia).resolve()))]
    for name in COMPARATORS:
        binary = getattr(args, name)
        if binary is None and args.comparators is not None:
            candidate = args.comparators / f"{name}{EXE}"
            binary = candidate if candidate.is_file() else None
        if binary is not None:
            implementations.append((name, str(Path(binary).resolve())))
    method = ("fresh process per sample; binary stdin; each harness times only its "
              "measured loop with a monotonic clock (elapsed_ns); counting sink")
    if args.memory:
        method = ("fresh process per sample; peak resident memory (ru_maxrss) of a process that "
                  "reads the input and parses it once, minus that of one that only reads it")
    result = {"schema": 3, "platform": platform.platform(), "processor": platform.processor(),
              "python": platform.python_version(), "repeat": args.repeat, "method": method,
              "implementations": [name for name, _ in implementations], "samples": []}
    if args.memory:
        measure_memory(args, implementations, result)
    else:
        measure_speed(args, implementations, result)


if __name__ == "__main__":
    main()
