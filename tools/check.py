#!/usr/bin/env python3
"""Check the parser's conformance through the conformance executable, which
reads a document on stdin and writes it back compactly.

Every accepting case of JSONTestSuite (y_*) must be accepted and written back
as the same value, every rejecting case (n_*) rejected, and the
implementation-defined cases (i_*) must not crash. Then generated documents
must survive a round trip unchanged, and mutations of them that a strict
oracle (Python's json with Decimal numbers) rejects must be rejected too.

Build the executable with `nia build conformance` and fetch the suite with
`python tools/vendor.py` first.
"""
import argparse
import decimal
import json
import os
import random
import subprocess
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""

SUITE_REVISION = "1ef36fa01286573e846ac449e8683f8833c5b26a"


def oracle(data):
    def reject(value):
        raise ValueError(value)
    return json.loads(data.decode("utf-8"), parse_float=decimal.Decimal,
                      parse_int=decimal.Decimal, parse_constant=reject)


def execute(binary, data):
    run = subprocess.run([binary], input=data, capture_output=True, timeout=10)
    if run.returncode not in (0, 1):
        raise RuntimeError(f"parser process exited {run.returncode}: {run.stderr!r}")
    return run


def roundtrip(binary, data):
    run = execute(binary, data)
    if run.returncode:
        raise AssertionError(f"valid input rejected: {data[:160]!r}: {run.stderr!r}")
    if oracle(run.stdout) != oracle(data):
        raise AssertionError(f"changed JSON value: {data[:160]!r}")
    again = execute(binary, run.stdout)
    if again.returncode or again.stdout != run.stdout:
        raise AssertionError("compact serialization is not idempotent")


def generated_value(rng, depth=0):
    kind = rng.randrange(5 if depth == 5 else 7)
    if kind == 0:
        return None
    if kind == 1:
        return bool(rng.randrange(2))
    if kind == 2:
        return rng.randrange(-(1 << 90), 1 << 90)
    if kind == 3:
        return rng.uniform(-1e100, 1e100)
    if kind == 4:
        alphabet = ["a", "\x00", "\n", "\t", "\r", "\b", "\f", chr(34), chr(92), "~", "/", "é", "中", "𝄞", "\u2028"]
        return "".join(rng.choice(alphabet) for _ in range(rng.randrange(40)))
    if kind == 5:
        return [generated_value(rng, depth + 1) for _ in range(rng.randrange(8))]
    return {str(index) + "~é/": generated_value(rng, depth + 1)
            for index in range(rng.randrange(8))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=f"build/out/conformance{EXE}")
    parser.add_argument("--suite", type=Path, default=Path("build/vendor/JSONTestSuite"),
                        help="a JSONTestSuite checkout at the pinned revision")
    parser.add_argument("--no-suite", action="store_true", help="run only the generated cases")
    parser.add_argument("--cases", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=8259)
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    if args.no_suite:
        args.suite = None
    elif not args.suite.is_dir():
        parser.error(f"{args.suite} not found: run tools/vendor.py, or pass --no-suite")
    counts = {"accept": 0, "reject": 0, "implementation_defined": 0, "generated": 0, "mutations": 0}
    if args.suite:
        revision = subprocess.check_output(["git", "-C", str(args.suite), "rev-parse", "HEAD"], text=True).strip()
        if revision != SUITE_REVISION:
            raise SystemExit(f"JSONTestSuite must be at {SUITE_REVISION}, got {revision}")
        for path in sorted((args.suite / "test_parsing").glob("*.json")):
            data = path.read_bytes()
            run = execute(binary, data)
            if path.name.startswith("y_"):
                if run.returncode:
                    raise AssertionError(f"{path.name}: {run.stderr!r}")
                roundtrip(binary, data)
                counts["accept"] += 1
            elif path.name.startswith("n_"):
                if run.returncode != 1:
                    raise AssertionError(f"{path.name}: accepted invalid input")
                counts["reject"] += 1
            else:
                counts["implementation_defined"] += 1
    rng = random.Random(args.seed)
    for _ in range(args.cases):
        value = generated_value(rng)
        data = json.dumps(value, ensure_ascii=rng.choice([True, False]),
                          separators=rng.choice([(",", ":"), (", ", ": ")])).encode()
        roundtrip(binary, data)
        counts["generated"] += 1
        # Only compare mutations where the strict oracle rejects or produces
        # valid Unicode. Lone surrogates are intentionally rejected by Nia.
        if len(data) > 1:
            at = rng.randrange(len(data))
            mutation = data[:at] + bytes([rng.randrange(32)]) + data[at + 1:]
            try:
                oracle(mutation)
            except (ValueError, UnicodeError):
                if execute(binary, mutation).returncode != 1:
                    raise AssertionError(f"accepted invalid mutation: {mutation[:160]!r}")
                counts["mutations"] += 1
    print(json.dumps({"seed": args.seed, "suite_revision": SUITE_REVISION if args.suite else None, **counts}, sort_keys=True))


if __name__ == "__main__":
    main()
