#ifndef ZEITOP_PRESENT_TELEMETRY_H
#define ZEITOP_PRESENT_TELEMETRY_H
#include <stdint.h>
/* Observe presentation hook intervals; never wait or limit here. */
uint64_t zp_present_elapsed(uintptr_t device, uint64_t swapchain, uint64_t time_ns);
void zp_present_forget(uintptr_t device, uint64_t swapchain);
void zp_present_forget_device(uintptr_t device);
/* Emit the existing UI protocol ZEITOP1 without applying pacing. */
int zp_present_send(uint64_t elapsed_ns);
#endif
