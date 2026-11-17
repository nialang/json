/* The yyjson comparator for tools/bench.py: yyjson's ordinary strict,
 * immutable DOM, run as bench/main.nia runs the Nia library and printing the
 * same report; see bench/common/harness.h. */
#include "../common/harness.h"
#include "yyjson.h"

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    const char *mode = argv[1];
    if (strcmp(mode, "parse") && strcmp(mode, "write") && strcmp(mode, "roundtrip") &&
        strcmp(mode, "read") && strcmp(mode, "load")) return 2;
    size_t iterations = harness_iterations(argv[2]);
    if (!iterations) return 2;
    harness_keep_freed_memory();
    size_t length = 0, output_bytes = 0;
    char *input = harness_read_input(&length, 0);
    if (!input) return 2;
    /* `read` only reads the input; `load` also parses it once and keeps the
     * document, so the difference of their peak resident memory is what the
     * document costs. */
    if (!strcmp(mode, "read")) {
        harness_report(0, 0, length, 0, 1);
        return 0;
    }
    if (!strcmp(mode, "load")) {
        unsigned long long begin = harness_now_ns();
        yyjson_doc *doc = yyjson_read(input, length, 0);
        unsigned long long took = harness_now_ns() - begin;
        if (!doc) return 3;
        harness_report(1, yyjson_doc_get_val_count(doc), length, 0, took);
        return 0;
    }
    yyjson_doc *initial = yyjson_read(input, length, 0);
    if (!initial) return 3;
    unsigned long long start = harness_now_ns();
    if (!strcmp(mode, "write")) {
        for (size_t i = 0; i < iterations; ++i) {
            size_t size = 0;
            char *output = yyjson_write(initial, 0, &size);
            if (!output) return 4;
            output_bytes += size;
            free(output);
        }
    } else {
        yyjson_doc_free(initial);
        initial = NULL;
        for (size_t i = 0; i < iterations; ++i) {
            yyjson_doc *doc = yyjson_read(input, length, 0);
            if (!doc) return 3;
            if (!strcmp(mode, "roundtrip")) {
                size_t size = 0;
                char *output = yyjson_write(doc, 0, &size);
                if (!output) return 4;
                output_bytes += size;
                free(output);
            }
            yyjson_doc_free(doc);
        }
    }
    unsigned long long elapsed = harness_now_ns() - start;
    if (initial) yyjson_doc_free(initial);
    /* Count once outside the measured loop. yyjson's value count already
     * includes object keys, as the shared metric does. */
    yyjson_doc *doc = yyjson_read(input, length, 0);
    if (!doc) return 3;
    size_t nodes = yyjson_doc_get_val_count(doc) * iterations;
    yyjson_doc_free(doc);
    free(input);
    harness_report(iterations, nodes, length, output_bytes, elapsed);
    return 0;
}
