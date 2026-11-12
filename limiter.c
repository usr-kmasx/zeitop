/*
 * Zeitop experimental presentation pacing shim (64-bit Linux).
 * Hooks Vulkan, GLX and EGL via LD_PRELOAD; never accelerates slow frames.
 */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#define TARGET_NS 33333333ULL
#if !defined(ZEITOP_GL_ONLY) && !defined(ZEITOP_PACING_ONLY)
typedef int32_t (*PresentFn)(void *, const void *);
typedef void (*VkFn)(void);
typedef VkFn (*ProcLookup)(void *, const char *);
static PresentFn downstream_vk_present = NULL;
#endif
static _Thread_local uint64_t previous_present_ns = 0;
static _Thread_local int telemetry_socket = -1;

static const char *root_dir(void) {
    const char *root = getenv("ZEITOP_HOME");
    return (root && root[0] == '/') ? root : NULL;
}
static uint64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
}
static void wait_until_precise(uint64_t deadline_ns) {
    /*
     * CLOCK_MONOTONIC absolute sleeps overshoot by ~50-100 us on common
     * kernels, so sleep most of the time and finish with a short spin.
     * This does not prevent preemption or GPU/display-induced stalls.
     */
    const uint64_t spin_margin_ns = 400000ULL; /* 0.4 ms */
    uint64_t now = now_ns();
    if (now < deadline_ns && deadline_ns - now > spin_margin_ns) {
        uint64_t sleep_deadline = deadline_ns - spin_margin_ns;
        struct timespec ts = {
            .tv_sec = (time_t)(sleep_deadline / 1000000000ULL),
            .tv_nsec = (long)(sleep_deadline % 1000000000ULL)
        };
        int result;
        do {
            result = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
        } while (result == EINTR);
    }
    while (now_ns() < deadline_ns) {
#if defined(__i386__) || defined(__x86_64__)
        __asm__ __volatile__("pause");
#else
        __asm__ __volatile__("" ::: "memory");
#endif
    }
}

static int limiter_active(void) {
    const char *root = root_dir();
    if (!root) return 0;
    char path[1024];
    int n = snprintf(path, sizeof path, "%s/runtime/limit.state", root);
    if (n < 0 || (size_t)n >= sizeof path) return 0;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    char value = '0';
    ssize_t size = read(fd, &value, 1);
    close(fd);
    return size == 1 && value == '1';
}
static void report_interval(uint64_t elapsed_ns) {
    const char *root = root_dir();
    if (!root || elapsed_ns == 0) return;
    struct sockaddr_un address = {0};
    address.sun_family = AF_UNIX;
    int n = snprintf(address.sun_path, sizeof address.sun_path,
                     "%s/runtime/zeitop.sock", root);
    if (n < 0 || (size_t)n >= sizeof address.sun_path) return;
    if (telemetry_socket < 0) {
        telemetry_socket = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
        if (telemetry_socket < 0) return;
    }
    char message[80];
    n = snprintf(message, sizeof message, "ZEITOP1 %ld %.3f",
                 (long)getpid(), (double)elapsed_ns / 1000000.0);
    if (n <= 0 || (size_t)n >= sizeof message) return;
    (void)sendto(telemetry_socket, message, (size_t)n, MSG_DONTWAIT,
                 (struct sockaddr *)&address, sizeof address);
}
void zeitop_before_present(void) {
    uint64_t current = now_ns();
    if (limiter_active() && previous_present_ns) {
        uint64_t goal = previous_present_ns + TARGET_NS;
        if (current < goal) {
            wait_until_precise(goal);
            current = now_ns();
        }
    }
    if (previous_present_ns && current > previous_present_ns)
        report_interval(current - previous_present_ns);
    previous_present_ns = current;
}
#if !defined(ZEITOP_GL_ONLY) && !defined(ZEITOP_PACING_ONLY)
int32_t vkQueuePresentKHR(void *queue, const void *info) {
    PresentFn next = downstream_vk_present;
    if (!next) next = (PresentFn)dlsym(RTLD_NEXT, "vkQueuePresentKHR");
    if (!next || next == vkQueuePresentKHR) return -3;
    zeitop_before_present();
    return next(queue, info);
}
VkFn vkGetDeviceProcAddr(void *device, const char *name) {
    ProcLookup next = (ProcLookup)dlsym(RTLD_NEXT, "vkGetDeviceProcAddr");
    if (!next) return NULL;
    if (name && !strcmp(name, "vkQueuePresentKHR")) {
        VkFn downstream = next(device, name);
        if (!downstream) return NULL;
        if ((PresentFn)downstream != vkQueuePresentKHR)
            downstream_vk_present = (PresentFn)downstream;
        return (VkFn)vkQueuePresentKHR;
    }
    return next(device, name);
}
VkFn vkGetInstanceProcAddr(void *instance, const char *name) {
    ProcLookup next = (ProcLookup)dlsym(RTLD_NEXT, "vkGetInstanceProcAddr");
    if (!next) return NULL;
    if (name && !strcmp(name, "vkGetDeviceProcAddr"))
        return (VkFn)vkGetDeviceProcAddr;
    if (name && !strcmp(name, "vkQueuePresentKHR")) {
        VkFn downstream = next(instance, name);
        if (!downstream) return NULL;
        if ((PresentFn)downstream != vkQueuePresentKHR)
            downstream_vk_present = (PresentFn)downstream;
        return (VkFn)vkQueuePresentKHR;
    }
    return next(instance, name);
}
#endif
#ifndef ZEITOP_PACING_ONLY
void glXSwapBuffers(void *display, unsigned long drawable) {
    typedef void (*SwapFn)(void *, unsigned long);
    SwapFn next = (SwapFn)dlsym(RTLD_NEXT, "glXSwapBuffers");
    if (!next) return;
    zeitop_before_present();
    next(display, drawable);
}
unsigned int eglSwapBuffers(void *display, void *surface) {
    typedef unsigned int (*SwapFn)(void *, void *);
    SwapFn next = (SwapFn)dlsym(RTLD_NEXT, "eglSwapBuffers");
    if (!next) return 0;
    zeitop_before_present();
    return next(display, surface);
}
#endif
