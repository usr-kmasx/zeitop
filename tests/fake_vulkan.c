#include <stdint.h>
#include <string.h>

typedef void (*VkFn)(void);
int32_t vkQueuePresentKHR(void *queue, const void *info) {
    (void)queue; (void)info;
    return 0;
}
VkFn vkGetDeviceProcAddr(void *device, const char *name) {
    (void)device;
    return !strcmp(name, "vkQueuePresentKHR") ? (VkFn)vkQueuePresentKHR : (VkFn)0;
}
