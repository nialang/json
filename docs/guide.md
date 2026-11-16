# Guide

This guide covers everything the library does: parsing, reading values,
numbers, JSON Pointer, writing, limits, errors, and how a document owns its
storage. Every example assumes `using json;` and an allocator, such as

```nia
let mut page: mem::PageAllocator = .init();
let mut allocator: mem::GeneralPurposeAllocator = .init(page);
defer allocator.deinit().?;
```

## Documents

A `json::Document` holds one parsed value and the storage behind it. Create
one, register its release, and parse into it:

```nia
let mut document = json::Document::init();
defer document.deinit(allocator).?;
document.parse(allocator, text).?;
let top = document.value().?;
```

`parse` copies the text, so the input may change or go away afterwards.
`value` returns the top-level value, or `null` when the document holds none:
before the first parse, after `clear`, and after a parse that failed.

A document can parse again. Each parse replaces the value it held and reuses
its storage, so a program that reads many documents of similar size, such as
messages from a socket, stops allocating after the first few. `clear` drops
the value but keeps the storage. `nodeCount` returns how many values the
document holds, counting object keys as values.

A document owns allocations and must not be copied. Release it with
`deinit` on the allocator it parsed with. After `deinit` succeeds, the
document cannot parse again; make a new one with `Document::init`.

## Reading Values

A `json::Value` is a view of one value in a document. Views are two words,
are copied freely, and allocate nothing. Each one borrows the document: a
later `parse`, `clear`, or `deinit` invalidates every view of it, including
the strings and numbers read through them.

`kind` tells which of the six JSON kinds a value is, as a `json::Kind`:
`Null`, `Boolean`, `Number`, `String`, `Array`, or `Object`. The `as` methods
return the contents when the value is of that kind and `null` otherwise:

| Method | Returns |
| --- | --- |
| `isNull()` | `bool` |
| `asBool()` | `?bool` |
| `asNumber()` | `?json::Number`, see [Numbers](#numbers) |
| `asString()` | `?&[u8]`, the decoded UTF-8 bytes |
| `asArray()` | `?json::Array` |
| `asObject()` | `?json::Object` |

With `.?` they chain into a lookup that gives up at the first value that is
missing or of the wrong kind:

```nia
fun userName(document: &json::Document) ?&[u8] {
    let user = document.value().?.asObject().?.get(b"user").?;
    user.asObject().?.get(b"name").?.asString()
}
```

Strings are decoded when the document is parsed: escapes are replaced by the
bytes they stand for, and `\u` escapes, surrogate pairs included, become
UTF-8. The text is checked to be well-formed UTF-8 throughout, so a string
read from a document is always valid UTF-8. It is not normalized: `"\u00e9"`
and `"e\u0301"` both spell é, and are different strings.

### Arrays

`json::Array` has `len`, `isEmpty`, `get(index)`, and `iter`, and a `for`
loop walks its elements in order:

```nia
let mut total: u64 = 0;
for element in array {
    if element.asNumber() is ?number {
        total += number.toU64().?;
    }
}
```

`get` walks the array to the element it returns, since elements take
different amounts of storage; to visit many elements, iterate instead.

### Objects

`json::Object` has `len`, `isEmpty`, `get(key)`, and `iter`. Iterating an
object yields each member as a `json::Member`, with `key()` and `value()`:

```nia
for member in object {
    io::debugPrint("{}\n", [member.key()]).?;
}
```

Members keep the order they were written in. An object may name the same key
more than once; every member is kept, `iter` yields each of them, and `get`
returns the value of the last one, as most JSON readers do. `get` compares
keys byte for byte and walks the members, so for many lookups in one large
object, iterate once and dispatch on the key.

`asValue` turns an array or object back into a `json::Value`.

## Numbers

A `json::Number` keeps the number exactly as it was written. `raw` returns
that text, which is how a program reads a number that no machine type holds
exactly, such as a 30-digit integer or a decimal amount of money.

`isInteger` tells whether it was written without a fraction or exponent, and
`isNegative` whether it has a minus sign. The conversions say when a value
does not fit, and never round an integer:

| Method | Result |
| --- | --- |
| `toU64()` | `json::NumberError!u64` |
| `toI64()` | `json::NumberError!i64` |
| `toF64()` | `std::parse::Error!f64` |
| `toF32()` | `std::parse::Error!f32` |

The integer conversions fail with `NotInteger` for a number written with a
fraction or exponent, even one that has an integer value such as `1.0` or
`1e2`, and with `OutOfRange` for one that does not fit. `-0` converts to
zero. The floating-point conversions round correctly to the nearest value; a
magnitude too large for the type is an error, and one too small rounds to a
zero of the same sign.

## JSON Pointer

`Value::pointer` selects a value by an [RFC 6901](https://www.rfc-editor.org/rfc/rfc6901)
JSON Pointer:

```nia
let memory = top.pointer(b"/limits/memory").?;
let first = top.pointer(b"/hosts/0").?;
```

The empty pointer selects the value itself. In a token, `~1` stands for `/`
and `~0` for `~`. An object step takes the last member with a matching key,
as `get` does, and an array step needs a decimal index without leading zeros.
A failed lookup returns a `json::PointerError`:

| Error | Meaning |
| --- | --- |
| `InvalidPath` | The pointer is not empty and does not start with `/`. |
| `InvalidEscape` | A `~` is not followed by `0` or `1`. |
| `NotFound` | A token names no member or element, or steps into a value that is neither an object nor an array. |
| `InvalidArrayIndex` | A token applied to an array is not a decimal index. |

## Writing

`Value::writeTo` writes a value and everything in it to any `std::io::Writer`,
with a `json::WriteOptions`:

```nia
let mut buffer: [u8; 4096] = [0; 4096];
let mut stdout = io::FileWriter::stdout(buffer);
top.writeTo(&mut stdout, json::WriteOptions::compact()).?;
stdout.flush().?;
```

`WriteOptions::compact()` writes no whitespace. `WriteOptions::pretty(indent)`
puts each member and element on its own line, indented by `indent` spaces
per level, with a space after each colon; empty arrays and objects stay `[]`
and `{}`.

Writing allocates nothing. Output is staged in a buffer on the stack and
handed to the writer in blocks of 4 KiB, so writing to an unbuffered writer
costs one call per block. If the writer fails, `writeTo` returns its error,
and the text written so far may be incomplete.

What is written is equivalent to what was read, and close to how it was
spelled:

- Numbers are written exactly as they were read.
- A string or key written without escapes is written as it was. One written
  with escapes is written from its decoded bytes: `"` and `\` and the control
  characters are escaped, with the short forms `\b \f \n \r \t` where they
  exist and `\u00XX` with lowercase digits otherwise; every other byte,
  including non-ASCII UTF-8 and `/`, is written as it is.
- Object members, duplicates included, are written in their order.

## Limits

`Document::parse` uses the default limits. `parseWith` takes a
`json::Options` that sets them:

```nia
let options = json::Options::init()
    .withMaxDepth(32)
    .withMaxInputBytes(1024 * 1024);
document.parseWith(allocator, text, options).?;
```

| Limit | Default | Bounds |
| --- | --- | --- |
| `withMaxInputBytes` | 64 MiB | the length of the text |
| `withMaxDepth` | 128 | how deeply arrays and objects nest; scalars alone are depth 0 |
| `withMaxNodes` | 1,000,000 | how many values the document holds, counting object keys |
| `withMaxStringBytes` | 16 MiB | the decoded length of any one string or key |
| `withMaxNumberBytes` | 4096 | the length of any one number as written |

Together they bound the work and memory of a parse, which matters for text
from an untrusted source. Text of at most 4 GiB can be parsed whatever the
limits, since the document records offsets in 32 bits.

A document holds a copy of the text and 12 bytes for each value it has room
for. A parse makes room for one value per two bytes of text, up to
`maxNodes`, since a value takes at least two bytes of text with its
separator, so that it rarely grows while parsing:
parsing text of `n` bytes takes about `7n` bytes, which a later parse of
smaller text reuses. Nesting deeper than 32 levels takes another 8 bytes per
level.

## Errors

A failed parse returns a `json::Error`:

| Error | Meaning |
| --- | --- |
| `Syntax(diagnostic)` | The text is not JSON, or it exceeds a limit. |
| `Allocation(error)` | The allocator could not provide storage. |
| `InvalidState` | The document was released by `deinit`, or retired by a failed `deinit`. |

After a failure the document holds no value, keeps its storage, and can parse
again.

A `json::Diagnostic` says what was wrong, as a `json::Code`, and where:
`offset` is the byte offset in the text, and `line` and `column` count from
one, with columns in bytes. The location is computed only when a parse
fails.

```nia
match document.parse(allocator, text) {
    !() => (),
    json::Error::Syntax(diagnostic)! => {
        io::debugPrint("line {} column {}\n", [diagnostic.line(), diagnostic.column()]).?;
    },
    failure! => return failure!,
}
```

| Code | Meaning |
| --- | --- |
| `UnexpectedEnd` | The text ends inside a value. |
| `UnexpectedToken` | A byte cannot start a value, or `true`, `false`, or `null` is misspelled. |
| `TrailingContent` | Something other than whitespace follows the top-level value. |
| `ExpectedColon` | A key is not followed by `:`. |
| `ExpectedCommaOrEnd` | A member or element is not followed by `,` or the closing bracket. |
| `ExpectedKey` | An object member does not start with a string. |
| `InvalidNumber` | A number is malformed, such as `01`, `1.`, `.5`, `-`, or `1e`. |
| `InvalidEscape` | A backslash is followed by a byte that starts no escape. |
| `InvalidUnicodeEscape` | `\u` is not followed by four hexadecimal digits. |
| `UnpairedSurrogate` | A `\u` escape of a surrogate is not one half of a pair. |
| `ControlCharacter` | A string holds a byte below 0x20, which must be escaped. |
| `InvalidUtf8` | The text is not well-formed UTF-8. |
| `DepthLimit`, `NodeLimit`, `InputLimit`, `StringLimit`, `NumberLimit` | A limit in `Options` is exceeded. |

What the parser accepts is exactly RFC 8259 JSON in UTF-8. It rejects a byte
order mark, comments, trailing commas, single quotes, unquoted keys, `NaN`
and `Infinity`, leading zeros and `+` signs in numbers, and unpaired
surrogates, whether written raw or as `\u` escapes. Any value may be the
top-level value, not only an object or array, and a number of any size or
precision is accepted and kept as written.

## Ownership And Failure

Every allocation goes through the allocator passed to `parse`; the library
has no global state. A document must be released on the same allocator.

An allocation failure at any point of a parse leaves the document
consistent: it holds no value, owns everything it allocated, and can parse
again or be released. If the allocator fails to release some storage,
`deinit` returns the error and keeps that storage; the document can then do
nothing but `deinit` again, which retries what failed and releases nothing
twice.

Parsing, reading, and writing never recurse, so deeply nested text cannot
overflow the stack, whatever `maxDepth` allows.

A document is not synchronized. Several threads may read one document and
its views at once, but not while any thread parses into it, clears it, or
releases it.
