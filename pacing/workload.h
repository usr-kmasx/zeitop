#ifndef ZEITOP_WORKLOAD_H
#define ZEITOP_WORKLOAD_H
#include <stdint.h>
/* Synthetic CPU-only test work; not linked into the game Vulkan layer.
 * UINT64_MAX means an unsupported input. NULL means no test workload.
 */
uint64_t zp_workload_ns(const char *pattern, uint32_t frame, uint32_t seed);
void zp_busy_work(uint64_t duration_ns);
#endif
