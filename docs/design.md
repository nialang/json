# Design

This document describes how the library is built and why: the document's
layout, the parser, the writer, and the decisions that measurements settled.
It is for readers of the source and for anyone changing it. The
[guide](guide.md) describes the behavior that the design must keep.

## Goals

The library is Nia's foundational JSON library, so it is held to three
standards at once. It must be correct: strict RFC 8259, exact numbers,
precise errors, and no state an allocation failure can corrupt. It must be
fast, at the level of the fastest C libraries for the same document model.
And it must read as idiomatic Nia, since it is an example of how Nia code is
written.

## Source Layout

| File | Contents |
| --- | --- |
| `lib/root.nia` | The public facade: modules and re-exports. |
| `lib/document.nia` | `Document`, `Options`, and the document's lifecycle. |
| `lib/tape.nia` | The value tape: `Node`, `Kind`, and the node flags. |
| `lib/parse.nia` | The grammar: one loop that fills the tape. |
| `lib/lexical.nia` | Scanning strings, numbers, literals, and whitespace, and UTF-8 validation. |
| `lib/value.nia` | `Value`, `Array`, `Object`, `Member`, and their iterators. |
| `lib/number.nia` | `Number` and its conversions. |
| `lib/pointer.nia` | RFC 6901 JSON Pointer. |
| `lib/write.nia` | Writing values as text. |
| `lib/error.nia` | `Error`, `Code`, and `Diagnostic`. |
| `lib/storage.nia` | `Growable`, the capacity that parsing writes into. |

## The Document

A document owns three pieces of storage, each a `Growable`: the image, the
tape, and the frame stack.

### The Image

Parsing first copies the input into the image, then decodes every string in
place there. A decoded string starts where its source starts and is never
longer, since every escape decodes to fewer bytes than it spells, so writing
never overtakes reading. Strings, keys, and numbers are then slices of the
image, and the document allocates nothing per value.

Owning a copy costs one `memcpy` of the input, and buys the caller freedom:
the input may be a reused read buffer, and nothing in the document points
into memory it does not own.

### The Tape

Values are stored in preorder in one array of 12-byte nodes: a container is
followed by its contents, and an object's contents alternate key and value.

```nia
pub(root) struct Node {
    kind: Kind,
    flags: u8,
    len: u32,
    data: u32,
}
```

| Kind | `flags` | `len` | `data` |
| --- | --- | --- | --- |
| null | | | |
| boolean | the value | | |
| number | negative, integer | the length as written | its offset in the image |
| string, key | escaped | the decoded length | its offset in the image |
| array, object | | the element or member count | the index just past its subtree |

A container's `data` lets a reader step over a whole subtree at once, which
is how iterators move from one element to the next and how `Object::get`
skips the values of members it passes. Offsets rather than pointers keep the
tape valid when the image moves, and 32-bit fields keep a node at 12 bytes;
they limit a document to 4 GiB of text.

Numbers are stored as their text. Conversion happens when a program asks
for a value, through `Number`, so a parse never pays for conversions nobody
reads, and a number keeps its exact digits.

### Lifecycle

A document is in one of four states. `Empty` holds no value: it was never
parsed, was cleared, or its last parse failed. `Parsed` holds a value.
`Released` has given its storage back. `Retired` is the state of a document
whose `deinit` failed to release some storage: it still owns that storage and
can only `deinit` again. `Growable` keeps an allocation whose release failed
as `retired`, so that no allocation is ever dropped.

## Parsing

`parseTape` in `lib/parse.nia` fills the tape in one pass over the image. It
is one function, so the hot state lives in registers: the read position, the
node count, and the innermost open container's index, child count, and
kind.

### Containers Without Recursion

Opening a container pushes the enclosing container's index and child count
onto the frame stack, one `Frame` of two `u32` per level; closing it pops
them back and writes the closed container's count and subtree end into its
node. The stack starts in a 32-level array in `parseTape`'s own frame and
moves to the document's storage only for documents nested deeper, so most
parses allocate nothing for it.

Arrays and objects each have their own loop. An array's loop reads elements,
an object's reads key, colon, and value, and each runs until its container
closes or a child opens, so neither asks which kind of container it is in.
An outer loop switches to whichever container is then innermost.

### The Expected Byte First

Compact text almost never has whitespace between tokens, so each loop first
tests the byte the grammar expects next, a comma, colon, or quote, and skips
whitespace only when that byte is not there. Pretty-printed text is the
other common case; there, `skipWhitespace` steps over indentation two spaces
at a time.

### Fast Paths For Short Tokens

Most strings and numbers are short. `shortString` reads the sixteen bytes
after an opening quote as one vector and finds the closing quote with one
mask; when the string is plain ASCII and closes in that window, the node is
written with no further scanning. `shortInteger` does the same for integers,
and tells a single digit, the most common number, with two compares.
Anything else, such as a long string, one with escapes or non-ASCII text, or
a number with a fraction or exponent, falls back to `decodeString` or
`scanNumber`, which also report every error. A differential test parses
every short spelling both ways and requires the same result.

`parseTape` takes the compile-time parameter `ShortLimits`, which says
whether a string or number limit is below sixteen bytes. Under the default
limits it is false, and the fast paths check no limit at all; only the slow
paths, which handle the tokens that could exceed one, do.

### Strings

`decodeString` moves through plain text sixteen bytes at a time: a chunk with
no quote, backslash, control character, or byte of 0x80 or more is copied
down as it is. Chunks with non-ASCII bytes are validated as UTF-8 in the same
vector pass, by comparing each byte with the leads one, two, and three bytes
before it; only a chunk that is malformed, or that a sequence crosses, falls
back to the byte-wise path, which reports the exact offset. Escapes are
decoded in runs, since they tend to come together.

Every vector load stays inside the image, so the input needs no padding past
its end.

### Room On The Tape

The tape grows as values are added. Before each node is written, `roomAt`
checks that it fits and grows the tape when it does not; the growth is a
separate function marked `@[inlineNever]`, so the loop carries no code for
it. Each parse first makes room for one value per two bytes of input, so the
tape rarely grows mid-parse.

## Writing

`writeTokens` walks the tape in order, as the parser filled it, so writing
needs no recursion either. It remembers the outermost 64 open containers and
finds deeper ones by descending the tape from the deepest it remembers.

Output is staged in a 4 KiB buffer and handed to the writer a block at a
time, as a writer that builds its text in memory would, so the cost of a
writer call does not multiply by the number of tokens. Short runs, such as
most keys and numbers, move as one sixteen-byte block.

A string whose source had no escapes is copied from the image with its
quotes, since such a string cannot hold a byte that needs escaping. The
parser marks the others with the escaped flag, set exactly when the decoded
string is shorter than its source. Those are written sixteen bytes at a
time: a chunk is staged as it is, and when some bytes in it need escaping,
the run from the first to the last of them is spelled over the copy from a
256-entry table, built at compile time, that holds each byte's spelling
padded to eight bytes.

## Decisions Measurements Settled

These alternatives were built and measured, and rejected; they are recorded
so that they are not tried again without a new reason.

**A two-stage, simdjson-style index.** A first stage that classifies 64
bytes at a time and records every structural position took a third to two
fifths of the time of the whole single-pass parse, but the second stage, which still
had to find the ends of strings and numbers, was then slower than the
single pass it replaced. The single pass already spends almost nothing on
the whitespace an index skips. It is worth trying again only with a second
stage that takes string and number ends from the index.

**Vector whitespace skipping.** Classifying sixteen or sixty-four bytes of
whitespace at once ran fewer instructions and was still 6 to 11 percent
slower. Parsing is a chain of dependent positions: a position computed from
a vector mask makes the processor wait for the mask, while a correctly
predicted branch lets it run ahead to the next token.

**Padding the image.** Copying the input into an allocation with sixteen
spare bytes would let every load skip its length check, but deciding with
lane masks instead added more work on the critical path than the checks it
removed.

**AVX2 dispatch.** A parser compiled for AVX2 and chosen at run time was
within measurement noise of the baseline on most corpora, since the parser's
vectors are sixteen bytes wide and its scalar loop gains little from the
newer instructions. The library is built for the baseline of each target.

**A smaller first tape.** Making room for one value per five bytes of
input, and extrapolating when a denser document runs out, saved no memory:
the tape pages a parse never reaches are never made resident, so peak memory
was the same. It cost 10 percent on indented text and the citm catalog, for
the growth's copy and the extra state in the loop.

**Keeping only the content.** Parsing straight from the caller's input and
copying only string and number bytes into the document, instead of copying
the whole text first, cut the memory of a document by a quarter to a half on
structured text, and parsed long strings up to half again as fast, since a
string is then copied once rather than copied and decoded. But writing keys
and short values became 9 to 14 percent slower, and parsing small and
indented documents 3 to 9 percent slower, with the same instructions
executed; placing the content at the offsets of the text did not recover
it. The document keeps its copy of the whole text until that cost is
understood.

**Eager number conversion.** Converting numbers while parsing, as some
libraries do, costs every parse the conversion of numbers that are never
read. Numbers stay as text until a program asks.

## Checked Arithmetic

Nia checks every integer operation and index, and the library keeps those
checks. Its only unchecked operations are unaligned vector loads and stores,
each preceded by a check that the bytes it touches are in bounds. Its speed
comes from writing code whose checks the compiler can prove away: reading through windows of a fixed
length, so that offsets in them need no checks; computing a token's length and
end where it is scanned, so that callers do no arithmetic of their own; and
re-checking room after growth in the caller, where it proves the next write
in bounds. The Nia compiler removes the checks it can prove after inlining,
including those that hold on every path into a merge. Where a check remains in
a hot loop, the code is shaped so that it can be proven, rather than the check
removed.
