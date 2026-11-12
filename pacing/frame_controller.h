#ifndef ZEITOP_FRAME_CONTROLLER_H
#define ZEITOP_FRAME_CONTROLLER_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct zp_controller zp_controller;
typedef struct zp_stream zp_stream;
typedef struct {
    uint64_t (*now_ns)(void *ctx);
    void (*sleep_until_ns)(uint64_t deadline_ns, void *ctx);
    void *ctx;
} zp_clock;

/* Reservation pins a stream even if destroyed; complete every ticket once. */
typedef struct {
    zp_stream *stream;
    uint64_t deadline_ns;
    uint64_t previous_ns;
} zp_ticket;

zp_controller *zp_controller_new(uint64_t period_ns, zp_clock clock);
/* Call delete only after the application's acquire calls have joined. */
void zp_controller_delete(zp_controller *controller);
/* Reserves unique deadlines for overlapping acquisitions of one swapchain. */
zp_ticket zp_frame_reserve(zp_controller *controller, uintptr_t device,
                           uint64_t swapchain, int enabled);
void zp_frame_wait(zp_controller *controller, zp_ticket ticket);
void zp_frame_complete(zp_controller *controller, zp_ticket ticket, int success);
void zp_frame_forget(zp_controller *controller, uintptr_t device, uint64_t swapchain);
void zp_device_forget(zp_controller *controller, uintptr_t device);
#ifdef __cplusplus
}
#endif
#endif
