#define _GNU_SOURCE
#include "frame_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    assert(argc==2);
    assert(!setenv("ZEITOP_HOME",argv[1],1));
    assert(zp_runtime_enabled()==1);
    /* A nonblocking Vulkan acquire (timeout == 0) must not be delayed. */
    assert(zp_acquire_can_wait(0)==0);
    assert(zp_acquire_can_wait(1000000ULL)==1);
    assert(zp_acquire_can_wait(UINT64_MAX)==1);
    zp_clock clock=zp_runtime_clock();
    assert(clock.now_ns && clock.sleep_until_ns);
    uint64_t now=clock.now_ns(clock.ctx);
    assert(now > 0);
    clock.sleep_until_ns(now+3000000ULL,clock.ctx); /* 3 ms */
    uint64_t after=clock.now_ns(clock.ctx);
    assert(after >= now+3000000ULL);
    assert(after < now+1000000000ULL);
    puts("Runtime flag and monotonic wait passed");
    return 0;
}
