#include "backend_selector.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    zp_backend_caps c={0};
    assert(zp_choose_backend(&c)==ZP_BACKEND_DISABLED);
    c.acquire_supported=1;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_ACQUIRE);
    c.submit_supported=1;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_ACQUIRE);
    c.ext_advertised=1; c.ext_enabled=1; c.ext_feature_enabled=1;
    c.ext_surface_absolute=1; c.ext_swapchain_enabled=1;
    c.ext_queue_ready=1; c.fifo_mode=1;
    assert(zp_choose_backend(&c)==ZP_BACKEND_EXT_TIMING);
    c.ext_feature_enabled=0;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_ACQUIRE);
    c.ext_feature_enabled=1; c.ext_queue_ready=0;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_ACQUIRE);
    c.ext_queue_ready=1; c.fifo_mode=0;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_ACQUIRE);
    c.google_enabled=1; c.google_surface_supported=1;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_ACQUIRE);
    c.fifo_mode=1; c.ext_surface_absolute=0;
    assert(zp_choose_backend(&c)==ZP_BACKEND_GOOGLE_TIMING);
    c.google_surface_supported=0;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_ACQUIRE);
    c.acquire_supported=0;
    assert(zp_choose_backend(&c)==ZP_BACKEND_FRAME_SUBMIT);
    c.submit_supported=0;
    assert(zp_choose_backend(&c)==ZP_BACKEND_DISABLED);
    assert(zp_backend_name(ZP_BACKEND_EXT_TIMING)!=NULL);
    puts("Backend: 12 capability/fallback checks passed");
    return 0;
}
