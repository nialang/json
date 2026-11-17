/* What every C and C++ comparator harness shares: the report format of
 * bench/main.nia, a monotonic clock, reading standard input, and the heap
 * setting that keeps the comparison about the libraries.
 *
 * Every harness is run as
 *
 *     harness <mode> <iterations> < input.json
 *
 * and prints one line, `iterations=N nodes=N input_bytes=N output_bytes=N
 * elapsed_ns=N`. Exit status 2 means bad arguments or input, 3 a failed
 * parse, and 4 a failed write. */
#ifndef NIA_JSON_BENCH_HARNESS_H
#define NIA_JSON_BENCH_HARNESS_H

/* clock_gettime is POSIX, which strict ISO modes leave undeclared. A harness
 * includes this header before any other. */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif

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
static unsigned long long harness_now_ns(void) {
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

/* glibc serves a block past its mmap threshold from fresh pages and returns
 * them on free, so a document's buffer, sized from the input, would fault in
 * again on every iteration; that halved pretty-printed parses. Keep freed
 * memory in the heap, as the Nia allocator does. */
static void harness_keep_freed_memory(void) {
#ifdef __GLIBC__
    mallopt(M_MMAP_THRESHOLD, 1 << 30);
    mallopt(M_TRIM_THRESHOLD, 1 << 30);
#endif
}

/* The iteration count of argv[2], or 0 when it is not a positive number. */
static size_t harness_iterations(const char *text) {
    return (size_t)strtoull(text, NULL, 10);
}

/* Reads standard input into a malloc'd buffer with `spare` bytes after it,
 * set to zero. Returns NULL on failure. */
static char *harness_read_input(size_t *length, size_t spare) {
    size_t capacity = 4096, used = 0;
    char *input = (char *)malloc(capacity + spare);
    if (!input) return NULL;
    for (;;) {
        if (used == capacity) {
            capacity *= 2;
            char *next = (char *)realloc(input, capacity + spare);
            if (!next) { free(input); return NULL; }
            input = next;
        }
        size_t count = fread(input + used, 1, capacity - used, stdin);
        used += count;
        if (!count) break;
    }
    if (ferror(stdin)) { free(input); return NULL; }
    memset(input + used, 0, spare);
    *length = used;
    return input;
}

static void harness_report(size_t iterations, size_t nodes, size_t input_bytes,
                           size_t output_bytes, unsigned long long elapsed_ns) {
    printf("iterations=%zu nodes=%zu input_bytes=%zu output_bytes=%zu elapsed_ns=%llu\n",
           iterations, nodes, input_bytes, output_bytes, elapsed_ns);
}

#endif
