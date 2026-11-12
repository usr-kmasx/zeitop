#include "backend_selector.h"
#include <stddef.h>
zp_backend zp_choose_backend(const zp_backend_caps *c) {
    if (!c) return ZP_BACKEND_DISABLED;
    if (c->fifo_mode && c->ext_advertised && c->ext_enabled &&
        c->ext_feature_enabled && c->ext_surface_absolute &&
        c->ext_swapchain_enabled && c->ext_queue_ready)
        return ZP_BACKEND_EXT_TIMING;
    if (c->fifo_mode && c->google_enabled && c->google_surface_supported)
        return ZP_BACKEND_GOOGLE_TIMING;
    if (c->acquire_supported) return ZP_BACKEND_FRAME_ACQUIRE;
    if (c->submit_supported) return ZP_BACKEND_FRAME_SUBMIT;
    return ZP_BACKEND_DISABLED;
}
const char *zp_backend_name(zp_backend backend) {
    switch(backend) {
    case ZP_BACKEND_EXT_TIMING:return "Presentation timing (EXT)";
    case ZP_BACKEND_GOOGLE_TIMING:return "Presentation timing (GOOGLE)";
    case ZP_BACKEND_FRAME_ACQUIRE:return "Frame acquisition pacing";
    case ZP_BACKEND_FRAME_SUBMIT:return "Frame submission pacing";
    default:return "Unavailable";
    }
}
