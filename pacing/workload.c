#define _POSIX_C_SOURCE 200809L
#include "workload.h"
#include <stdint.h>
#include <string.h>
#include <time.h>
static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}
uint64_t zp_workload_ns(const char *pattern, uint32_t frame, uint32_t seed) {
    if(!pattern || !*pattern || !strcmp(pattern,"0")) return 0;
    if(!strcmp(pattern,"5")) return 5000000ULL;
    if(!strcmp(pattern,"20")) return 20000000ULL;
    if(!strcmp(pattern,"33")) return 33000000ULL;
    if(!strcmp(pattern,"40")) return 40000000ULL;
    if(!strcmp(pattern,"random")) {
        /* Stateless and reproducible: identical frame/seed in paired runs. */
        uint32_t x = frame ^ (seed * 0x9e3779b9U);
        x ^= x >> 16; x *= 0x7feb352dU;
        x ^= x >> 15; x *= 0x846ca68bU;
        x ^= x >> 16;
        static const uint64_t choices[] = {
            5000000ULL,20000000ULL,33000000ULL,40000000ULL
        };
        return choices[x % 4U];
    }
    return UINT64_MAX;
}
void zp_busy_work(uint64_t duration_ns) {
    if (!duration_ns || duration_ns == UINT64_MAX) return;
    const uint64_t start=now_ns();
    while (now_ns()-start < duration_ns) {
#if defined(__x86_64__) || defined(__i386__)
        __asm__ __volatile__("pause");
#else
        __asm__ __volatile__("" ::: "memory");
#endif
    }
}
