#!/usr/bin/env python3
"""Compare two builds of the conformance executable: their exit status,
diagnostics, and output must agree byte for byte on every JSONTestSuite case,
on hand-written seeds, and on random byte-level mutations of both.

A change meant to keep behavior, such as an optimization, is checked by
building the conformance executable before and after it:

    python tools/diff.py build/out/conformance-old build/out/conformance
"""
import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("old")
parser.add_argument("new")
parser.add_argument("--suite", type=Path, default=Path("build/vendor/JSONTestSuite"))
parser.add_argument("--cases", type=int, default=3000, help="mutated inputs to add")
args = parser.parse_args()
if not args.suite.is_dir():
    parser.error(f"{args.suite} not found: run tools/vendor.py")
old, new, suite, cases = str(Path(args.old).resolve()), str(Path(args.new).resolve()), args.suite, args.cases


def run(binary, data):
    r = subprocess.run([binary], input=data, capture_output=True, timeout=30)
    return r.returncode, r.stdout, r.stderr


inputs = [p.read_bytes() for p in sorted((suite / "test_parsing").glob("*.json"))]
rng = random.Random(77)
alphabet = b' \t\n\r[]{},:"\\/0123456789-+.eEtrufalsn\x00\x1f\x7f\xc3\xa9\xe4\xb8\xad\xed\xa0\x80\xf0\x9d\x84\x9e\xff'
seeds = list(inputs)
seeds += [
    b'{"a":[1,2,{"b":null}],"c":"x\\u00e9\\ud834\\udd1e"}',
    b'[[[[[[]]]]],{},[],{"":{"":[]}}]',
    b'{"key" : [ true , false , null , -0.5e+3 ] , "k2":"\\n\\t\\"\\\\"}',
    # Long strings of multi-byte text, so mutations land inside 16-byte chunks.
    ('["' + "中文é𝄞 " * 10 + '","' + "é" * 40 + '"]').encode(),
    ('{"k":"' + "x" * 13 + "𝄞" * 9 + "\\n" + "中" * 20 + "tail\\u00e9" + "é" * 17 + '"}').encode(),
    ('"' + "abcdefghijklmno" + "ࠀ" * 12 + "\U0010ffff" * 3 + "z" * 20 + '"').encode(),
]
for _ in range(cases):
    base = bytearray(rng.choice(seeds))
    for _ in range(rng.randrange(1, 4)):
        op = rng.randrange(4)
        if op == 0 and base:
            del base[rng.randrange(len(base))]
        elif op == 1:
            base.insert(rng.randrange(len(base) + 1), rng.choice(alphabet))
        elif op == 2 and base:
            base[rng.randrange(len(base))] = rng.choice(alphabet)
        elif base:
            base = base[: rng.randrange(len(base) + 1)]
    inputs.append(bytes(base))

mismatches = 0
for data in inputs:
    a, b = run(old, data), run(new, data)
    if a != b:
        mismatches += 1
        if mismatches <= 10:
            print("MISMATCH", data[:120], "\n  old:", a, "\n  new:", b)
print(json.dumps({"inputs": len(inputs), "mismatches": mismatches}))
sys.exit(1 if mismatches else 0)
