#define _POSIX_C_SOURCE 200809L
#include "frame_runtime.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static uint64_t monotonic_now(void *ctx) {
    (void)ctx;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC,&ts);
    return (uint64_t)ts.tv_sec*1000000000ULL+(uint64_t)ts.tv_nsec;
}
static void precise_sleep_until(uint64_t deadline, void *ctx) {
    const uint64_t margin=400000ULL;
    uint64_t now=monotonic_now(ctx);
    if (deadline > now && deadline-now > margin) {
        uint64_t until=deadline-margin;
        struct timespec ts={
            .tv_sec=(time_t)(until/1000000000ULL),
            .tv_nsec=(long)(until%1000000000ULL)
        };
        int status;
        do {
            status=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&ts,NULL);
        } while (status==EINTR);
    }
    while (monotonic_now(ctx) < deadline) {
#if defined(__x86_64__) || defined(__i386__)
        __asm__ __volatile__("pause");
#else
        __asm__ __volatile__("" ::: "memory");
#endif
    }
}
zp_clock zp_runtime_clock(void) {
    zp_clock clock={.now_ns=monotonic_now,
                    .sleep_until_ns=precise_sleep_until,.ctx=NULL};
    return clock;
}
int zp_acquire_can_wait(uint64_t timeout_ns) {
    return timeout_ns != 0;
}
int zp_runtime_enabled(void) {
    const char *root=getenv("ZEITOP_HOME");
    if (!root || root[0]!='/') return 0;
    char name[1024];
    int size=snprintf(name,sizeof(name),"%s/runtime/limit.state",root);
    if (size<0 || (size_t)size>=sizeof(name)) return 0;
    int fd=open(name,O_RDONLY|O_CLOEXEC);
    if (fd<0) return 0;
    char state='0';
    ssize_t result=read(fd,&state,1);
    close(fd);
    return result==1 && state=='1';
}
