// The nlohmann/json comparator for tools/bench.py: `nlohmann::json`, run as
// bench/main.nia runs the Nia library and printing the same report; see
// bench/common/harness.h.
#include "../common/harness.h"
#include "nlohmann/json.hpp"

#include <string>

using nlohmann::json;

// Every value of the document, counting object keys, as tools/bench.py does.
static size_t count_nodes(const json &value) {
    if (value.is_array()) {
        size_t count = 1;
        for (const json &child : value) count += count_nodes(child);
        return count;
    }
    if (value.is_object()) {
        size_t count = 1;
        for (const auto &member : value.items()) count += 1 + count_nodes(member.value());
        return count;
    }
    return 1;
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
    const char *begin = input;
    const char *end = input + length;
    if (mode == "read") {
        harness_report(0, 0, length, 0, 1);
        return 0;
    }
    if (mode == "load") {
        unsigned long long started = harness_now_ns();
        auto *document = new json(json::parse(begin, end, nullptr, false));
        unsigned long long took = harness_now_ns() - started;
        if (document->is_discarded()) return 3;
        harness_report(1, count_nodes(*document), length, 0, took);
        return 0;
    }
    json initial = json::parse(begin, end, nullptr, false);
    if (initial.is_discarded()) return 3;
    size_t nodes = count_nodes(initial) * iterations;
    unsigned long long start = harness_now_ns();
    if (mode == "write") {
        for (size_t i = 0; i < iterations; ++i) {
            std::string output = initial.dump();
            output_bytes += output.size();
        }
    } else {
        for (size_t i = 0; i < iterations; ++i) {
            json document = json::parse(begin, end, nullptr, false);
            if (document.is_discarded()) return 3;
            if (mode == "roundtrip") {
                std::string output = document.dump();
                output_bytes += output.size();
            }
        }
    }
    unsigned long long elapsed = harness_now_ns() - start;
    free(input);
    harness_report(iterations, nodes, length, output_bytes, elapsed);
    return 0;
}
