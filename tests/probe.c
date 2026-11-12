#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>

typedef int32_t (*PresentFn)(void*, const void*);
typedef void (*VkFn)(void);
extern VkFn vkGetDeviceProcAddr(void*, const char*);
static double ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1000000.0;
}
int main(void) {
    VkFn f = vkGetDeviceProcAddr(NULL, "vkQueuePresentKHR");
    if (!f) return 5;
    PresentFn present = (PresentFn)f;
    const char *root = getenv("ZEITOP_HOME");
    if (!root) return 6;
    char state[1024];
    snprintf(state, sizeof(state), "%s/runtime/limit.state", root);
    double prev = 0;
    for (int i = 0; i < 9; ++i) {
        if (present(NULL, NULL) != 0) return 7;
        double t = ms();
        if (i > 0) printf("%.3f\n", t - prev);
        fflush(stdout);
        prev = t;
        if (i == 4) {
            FILE *out = fopen(state, "w");
            if (!out) return 8;
            fputs("0\n", out);
            fclose(out);
        }
    }
    return 0;
}
