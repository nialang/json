# Changelog

## 0.1.0 (unreleased)

The first release: the document model.

- Strict RFC 8259 parsing of UTF-8 text into a `Document`, with limits on
  input length, nesting, values, string length, and number length, and
  diagnostics with byte offset, line, and column.
- Reading through `Value`, `Array`, `Object`, and `Member` views and their
  iterators, and RFC 6901 JSON Pointer lookup.
- `Number`, which keeps a number as written, with checked integer and
  correctly rounded floating-point conversions.
- Writing compact or indented text to any `std::io::Writer` without
  allocating.
