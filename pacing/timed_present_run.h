#ifndef ZEITOP_TIMED_PRESENT_RUN_H
#define ZEITOP_TIMED_PRESENT_RUN_H
#include <stdint.h>
#include "vulkan/vulkan_core.h"
typedef struct {
    VkDevice device;
    VkQueue queue;
    uint32_t queue_family;
    VkSwapchainKHR swapchain;
    uint32_t frame_count;
    int schedule_enabled;
    uint64_t target_interval_ns; /* 0 = default 33,333,333 ns */
    int nearest_refresh; /* request Vulkan's nearest-refresh scheduling */
    const char *cpu_work_pattern; /* test only; no effect in game layer */
    uint32_t cpu_work_seed;
    uint64_t stage_local_domain_id;
    PFN_vkGetCalibratedTimestampsKHR calibrate;
    PFN_vkGetPastPresentationTimingEXT get_past;
    const char *feedback_path;
} zp_timed_present_options;

/* Returns 0 on success; output contains true WSI feedback, not clock emulation. */
int zp_run_timed_present(const zp_timed_present_options *opts);
#endif
