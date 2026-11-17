/* The cJSON comparator for tools/bench.py: cJSON's tree of items, run as
 * bench/main.nia runs the Nia library and printing the same report; see
 * bench/common/harness.h. */
#include "../common/harness.h"
#include "cJSON.h"

/* Every value of the document, counting object keys, as tools/bench.py does. */
static size_t count_nodes(const cJSON *item) {
    size_t count = 1;
    if (cJSON_IsArray(item) || cJSON_IsObject(item)) {
        int object = cJSON_IsObject(item);
        for (const cJSON *child = item->child; child; child = child->next) {
            count += count_nodes(child) + (object ? 1 : 0);
        }
    }
    return count;
}

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
    if (!strcmp(mode, "read")) {
        harness_report(0, 0, length, 0, 1);
        return 0;
    }
    if (!strcmp(mode, "load")) {
        unsigned long long begin = harness_now_ns();
        cJSON *doc = cJSON_ParseWithLength(input, length);
        unsigned long long took = harness_now_ns() - begin;
        if (!doc) return 3;
        harness_report(1, count_nodes(doc), length, 0, took);
        return 0;
    }
    cJSON *initial = cJSON_ParseWithLength(input, length);
    if (!initial) return 3;
    size_t nodes = count_nodes(initial) * iterations;
    unsigned long long start = harness_now_ns();
    if (!strcmp(mode, "write")) {
        for (size_t i = 0; i < iterations; ++i) {
            char *output = cJSON_PrintUnformatted(initial);
            if (!output) return 4;
            output_bytes += strlen(output);
            cJSON_free(output);
        }
    } else {
        for (size_t i = 0; i < iterations; ++i) {
            cJSON *doc = cJSON_ParseWithLength(input, length);
            if (!doc) return 3;
            if (!strcmp(mode, "roundtrip")) {
                char *output = cJSON_PrintUnformatted(doc);
                if (!output) return 4;
                output_bytes += strlen(output);
                cJSON_free(output);
            }
            cJSON_Delete(doc);
        }
    }
    unsigned long long elapsed = harness_now_ns() - start;
    cJSON_Delete(initial);
    free(input);
    harness_report(iterations, nodes, length, output_bytes, elapsed);
    return 0;
}
