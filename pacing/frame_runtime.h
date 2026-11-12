#ifndef ZEITOP_FRAME_RUNTIME_H
#define ZEITOP_FRAME_RUNTIME_H
#include "frame_controller.h"
zp_clock zp_runtime_clock(void);
int zp_runtime_enabled(void);
/* Never make a nonblocking Vulkan acquire block in Zeitop. */
int zp_acquire_can_wait(uint64_t timeout_ns);
#endif
