# Testing

The library is checked in four ways: two test suites built with the package,
conformance against JSONTestSuite and generated documents, a differential
check between two builds, and benchmarks that verify their own counts. This
document describes each and how to run it.

## Test Suites

```sh
nia build test        # unit and robustness, unoptimized
nia build test -O2    # the same, optimized
```

Run both: the parser's fast paths and the compiler's optimizations differ
between the two, and either can hide a bug the other shows.

`tests/unit.nia` checks behavior:

| Case | Checks |
| --- | --- |
| objects and arrays | reading containers, members, and elements |
| strings written by their spelling | strings without escapes are written as their source |
| output past the stage | writing many 4 KiB blocks of tokens of every length, and to a writer one byte too short |
| every byte escaped anywhere | every byte value in every position of strings of every length is escaped and written back correctly |
| whitespace of any length | runs of every whitespace kind and length, in every position |
| numbers alike on either path | every number of up to four characters gives the same result on the fast path as on the general one |
| every node limit | each node limit is enforced exactly at its boundary |
| reused storage ends at the input | a shorter document parsed into used storage does not read past its end |
| every token limit | each string and number limit at every length, for keys, values, and top-level values |
| JSON pointers | lookups, escapes, and every error |
| compact and pretty writing | both formats |
| string decoding | escapes, surrogate pairs, and errors |
| UTF-8 validation | every boundary of RFC 3629's table of well-formed sequences, in every position of a vector chunk |
| grammar corpus | valid and invalid documents of every grammar rule |
| diagnostics | the code, offset, line, and column of errors |
| use after deinit | a released document refuses to parse |
| number conversion | integer and floating-point conversions and their errors |

`tests/robustness.nia` checks the document under failure and at its limits:

| Case | Checks |
| --- | --- |
| allocation failures retain ownership | an allocation failure at every point of a parse leaves a consistent document that owns all it allocated |
| failed cleanup is retryable | a failed release keeps its storage, and `deinit` can retry it |
| capacity reuse and input ownership | storage is reused across parses, and the document does not depend on its input |
| exact resource boundaries | each limit at its value and just past it |
| explicit correctly rounded floats | conversions at the edges of `f32` and `f64` |
| subtree writing and writer failures | writing a value inside a document, and to a writer that runs out of space |
| iterative deep document | nested arrays parsed and written back without recursion |
| frames spilled at any depth | nesting on either side of the parser's inline frames, with allocation failures |

Several cases are exhaustive over a small domain rather than sampled, such as
every escape in every position, or every number spelling up to four
characters. A case that guards an optimization is checked by mutation: the
optimized code is broken on purpose, and the case must fail.

## Conformance

`tools/check.py` runs the conformance executable, which reads a document on
standard input and writes it back compactly, against
[JSONTestSuite](https://github.com/nst/JSONTestSuite) and against generated
documents:

```sh
python tools/vendor.py        # once: fetch JSONTestSuite and yyjson
nia build conformance -O2
python tools/check.py
```

Every accepting case (`y_`) must be accepted and written back as the same
value, as Python's `json` module reads it with exact decimal numbers, and
writing that output again must give the same text. Every rejecting case
(`n_`) must be rejected. The implementation-defined cases (`i_`) must not
crash. The parser accepts the ten `i_` cases of very large or very small
numbers, which it keeps as written, and rejects the twenty-five others,
which hold malformed UTF-8, unpaired surrogates, UTF-16, a byte order mark,
or 500 levels of nesting.

Then a thousand random documents of every kind of value, including large
integers, control characters, and text outside the Basic Multilingual Plane,
must survive the same round trip, and a byte replaced in each one at random
must be rejected whenever Python's strict reader rejects it. `--cases` and
`--seed` change the number and the sequence.

## Differential Checking

A change meant to keep behavior, such as an optimization, is checked by
comparing the conformance executable before and after it:

```sh
nia build conformance -O2
cp build/out/conformance build/out/conformance-old
# ... make the change ...
nia build conformance -O2
python tools/diff.py build/out/conformance-old build/out/conformance
```

`tools/diff.py` requires the same exit status, diagnostic, and output on
every JSONTestSuite case, on hand-written seeds aimed at the vector paths,
and on 3000 random mutations of both. It catches a changed error offset as
surely as a changed value.

## Benchmarks

`tools/bench.py` checks that every harness reports the expected iteration,
value, and input byte counts, so a benchmark run also checks that each
implementation read the whole document. [benchmarks.md](benchmarks.md)
describes them.

## Before A Change Lands

- `nia build test` and `nia build test -O2`
- `python tools/check.py` on an `-O2` conformance build
- `python tools/diff.py` against the previous build, for any change to
  parsing or writing
- for a performance change, an interleaved comparison with `tools/ab.py`
  against the previous build, as described in [benchmarks.md](benchmarks.md)
