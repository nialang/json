// The RapidJSON comparator for tools/bench.py: RapidJSON's `Document` with
// its default allocator and parse flags, run as bench/main.nia runs the Nia
// library and printing the same report; see bench/common/harness.h.
#include "../common/harness.h"
#include "rapidjson/document.h"
#include "rapidjson/stringbuffer.h"
#include "rapidjson/writer.h"

#include <string>

using namespace rapidjson;

// Every value of the document, counting object keys, as tools/bench.py does.
static size_t count_nodes(const Value &value) {
    if (value.IsArray()) {
        size_t count = 1;
        for (const Value &child : value.GetArray()) count += count_nodes(child);
        return count;
    }
    if (value.IsObject()) {
        size_t count = 1;
        for (const auto &member : value.GetObject()) count += 1 + count_nodes(member.value);
        return count;
    }
    return 1;
}

// Writes `document` as compact text into `buffer`, which is reused.
static size_t write(const Document &document, StringBuffer &buffer) {
    buffer.Clear();
    Writer<StringBuffer> writer(buffer);
    if (!document.Accept(writer)) return 0;
    return buffer.GetSize();
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::string mode = argv[1];
    if (mode != "parse" && mode != "write" && mode != "roundtrip" && mode != "read" && mode != "load")
        return 2;
    size_t iterations = harness_iterations(argv[2]);
    if (!iterations) return 2;
    harness_keep_freed_memory();
    size_t length = 0, output_bytes = 0;
    char *input = harness_read_input(&length, 0);
    if (!input) return 2;
    if (mode == "read") {
        harness_report(0, 0, length, 0, 1);
        return 0;
    }
    if (mode == "load") {
        unsigned long long begin = harness_now_ns();
        auto *document = new Document();
        document->Parse(input, length);
        unsigned long long took = harness_now_ns() - begin;
        if (document->HasParseError()) return 3;
        harness_report(1, count_nodes(*document), length, 0, took);
        return 0;
    }
    Document initial;
    initial.Parse(input, length);
    if (initial.HasParseError()) return 3;
    size_t nodes = count_nodes(initial) * iterations;
    StringBuffer buffer;
    unsigned long long start = harness_now_ns();
    if (mode == "write") {
        for (size_t i = 0; i < iterations; ++i) {
            size_t size = write(initial, buffer);
            if (!size) return 4;
            output_bytes += size;
        }
    } else {
        for (size_t i = 0; i < iterations; ++i) {
            Document document;
            document.Parse(input, length);
            if (document.HasParseError()) return 3;
            if (mode == "roundtrip") {
                size_t size = write(document, buffer);
                if (!size) return 4;
                output_bytes += size;
            }
        }
    }
    unsigned long long elapsed = harness_now_ns() - start;
    free(input);
    harness_report(iterations, nodes, length, output_bytes, elapsed);
    return 0;
}
