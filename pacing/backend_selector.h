#ifndef ZEITOP_BACKEND_SELECTOR_H
#define ZEITOP_BACKEND_SELECTOR_H
typedef enum {
    ZP_BACKEND_DISABLED=0,
    ZP_BACKEND_FRAME_ACQUIRE=1,
    ZP_BACKEND_FRAME_SUBMIT=2,
    ZP_BACKEND_GOOGLE_TIMING=3,
    ZP_BACKEND_EXT_TIMING=4
} zp_backend;
typedef struct {
    int ext_advertised;
    int ext_enabled;
    int ext_feature_enabled;
    int ext_surface_absolute;
    int ext_swapchain_enabled;
    int ext_queue_ready;
    int google_enabled;
    int google_surface_supported;
    int fifo_mode;
    int acquire_supported;
    int submit_supported;
} zp_backend_caps;

/* Requires *enabled* capabilities, not just advertised extensions. */
zp_backend zp_choose_backend(const zp_backend_caps *capabilities);
const char *zp_backend_name(zp_backend backend);
#endif
