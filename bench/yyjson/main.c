/* The yyjson comparator for tools/bench.py: yyjson's ordinary strict,
 * immutable DOM, run as bench/main.nia runs the Nia library and printing the
 * same report. */
#include "yyjson.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif
#ifdef __GLIBC__
#include <malloc.h>
#endif

/* Monotonic nanoseconds, so a sample times only the measured loop. */
static unsigned long long now_ns(void) {
#ifdef _WIN32
    LARGE_INTEGER count, frequency;
    QueryPerformanceCounter(&count);
    QueryPerformanceFrequency(&frequency);
    return (unsigned long long)((double)count.QuadPart * 1e9 / (double)frequency.QuadPart);
#else
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (unsigned long long)now.tv_sec * 1000000000ull + (unsigned long long)now.tv_nsec;
#endif
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    const char *mode = argv[1];
    if (strcmp(mode, "parse") && strcmp(mode, "write") && strcmp(mode, "roundtrip")) return 2;
    size_t iterations = (size_t)strtoull(argv[2], NULL, 10);
    if (!iterations) return 2;
#ifdef __GLIBC__
    /* glibc serves a block past its mmap threshold from fresh pages and
     * returns them on free, so a document's buffer, sized from the input,
     * would fault in again on every iteration; that halved pretty-printed
     * parses. Keep freed memory in the heap, as the Nia allocator does. */
    mallopt(M_MMAP_THRESHOLD, 1 << 30);
    mallopt(M_TRIM_THRESHOLD, 1 << 30);
#endif
    size_t capacity = 4096, length = 0, output_bytes = 0, nodes = 0;
    char *input = malloc(capacity);
    if (!input) return 2;
    for (;;) {
        if (length == capacity) {
            capacity *= 2;
            char *next = realloc(input, capacity);
            if (!next) { free(input); return 2; }
            input = next;
        }
        size_t count = fread(input + length, 1, capacity - length, stdin);
        length += count;
        if (!count) break;
    }
    if (ferror(stdin)) { free(input); return 2; }
    yyjson_doc *initial = yyjson_read(input, length, 0);
    if (!initial) { free(input); return 3; }
    unsigned long long start = now_ns();
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
    unsigned long long elapsed = now_ns() - start;
    if (initial) yyjson_doc_free(initial);
    /* Count once outside the repeated parse path. yyjson's val_count already
       includes object keys as tape values, matching the shared metric. */
    yyjson_doc *doc = yyjson_read(input, length, 0);
    if (!doc) return 3;
    size_t values = yyjson_doc_get_val_count(doc);
    yyjson_doc_free(doc);
    nodes = values * iterations;
    free(input);
    printf("iterations=%zu nodes=%zu input_bytes=%zu output_bytes=%zu elapsed_ns=%llu\n", iterations, nodes, length, output_bytes, elapsed);
    return 0;
}
