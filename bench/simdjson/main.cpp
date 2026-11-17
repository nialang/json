// The simdjson comparator for tools/bench.py: simdjson's DOM API, run as
// bench/main.nia runs the Nia library and printing the same report; see
// bench/common/harness.h.
//
// `parse` builds a new `dom::parser` for each document, as a fresh document
// is built in every other harness; `reuse` parses every document with one
// parser, which keeps its buffers, as simdjson recommends.
#include "../common/harness.h"
#include "simdjson.h"

#include <string>

using namespace simdjson;

// Every value of the document, counting object keys, as tools/bench.py does.
static size_t count_nodes(dom::element element) {
    switch (element.type()) {
    case dom::element_type::ARRAY: {
        size_t count = 1;
        for (dom::element child : dom::array(element)) count += count_nodes(child);
        return count;
    }
    case dom::element_type::OBJECT: {
        size_t count = 1;
        for (dom::key_value_pair field : dom::object(element)) count += 1 + count_nodes(field.value);
        return count;
    }
    default:
        return 1;
    }
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::string mode = argv[1];
    if (mode != "parse" && mode != "reuse" && mode != "write" && mode != "roundtrip" &&
        mode != "read" && mode != "load")
        return 2;
    size_t iterations = harness_iterations(argv[2]);
    if (!iterations) return 2;
    harness_keep_freed_memory();
    size_t length = 0, output_bytes = 0;
    // simdjson reads past the end of its input; read straight into a buffer
    // with the padding it needs.
    char *bytes = harness_read_input(&length, SIMDJSON_PADDING);
    if (!bytes) return 2;
    if (mode == "read") {
        harness_report(0, 0, length, 0, 1);
        return 0;
    }
    if (mode == "load") {
        unsigned long long begin = harness_now_ns();
        auto *parser = new dom::parser();
        dom::element doc;
        if (parser->parse(bytes, length, false).get(doc)) return 3;
        unsigned long long took = harness_now_ns() - begin;
        harness_report(1, count_nodes(doc), length, 0, took);
        return 0;
    }
    dom::parser counting;
    dom::element initial;
    if (counting.parse(bytes, length, false).get(initial)) return 3;
    size_t nodes = count_nodes(initial) * iterations;
    dom::parser reused;
    unsigned long long start = harness_now_ns();
    if (mode == "write") {
        for (size_t i = 0; i < iterations; ++i) {
            std::string output = minify(initial);
            output_bytes += output.size();
        }
    } else {
        for (size_t i = 0; i < iterations; ++i) {
            dom::parser fresh;
            dom::parser &parser = mode == "reuse" ? reused : fresh;
            dom::element doc;
            if (parser.parse(bytes, length, false).get(doc)) return 3;
            if (mode == "roundtrip") {
                std::string output = minify(doc);
                output_bytes += output.size();
            }
        }
    }
    unsigned long long elapsed = harness_now_ns() - start;
    free(bytes);
    harness_report(iterations, nodes, length, output_bytes, elapsed);
    return 0;
}
