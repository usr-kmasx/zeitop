/*
 * Project-local Zeitop Vulkan explicit layer.
 * Negotiates Vulkan loader interface v2 and chains through the next layer.
 * No system installation, no Vulkan API modifications outside this process.
 */
#define VK_NO_PROTOTYPES
#include "vulkan/vk_layer.h"
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <spawn.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <sys/wait.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern void zeitop_before_present(void);
#ifdef ZEITOP_OUTPUT_TELEMETRY
extern void zeitop_output_present(void);
#endif

typedef struct InstanceRecord {
    void *key;
    VkInstance handle;
    PFN_vkGetInstanceProcAddr gipa;
    struct InstanceRecord *next;
} InstanceRecord;

typedef struct DeviceRecord {
    void *key;
    PFN_vkGetDeviceProcAddr gdpa;
    PFN_vkQueuePresentKHR present;
    PFN_vkDestroyDevice destroy;
    struct DeviceRecord *next;
} DeviceRecord;

static pthread_mutex_t records_lock = PTHREAD_MUTEX_INITIALIZER;
static InstanceRecord *instances;
static DeviceRecord *devices;

/* Vulkan dispatchable handles carry a loader dispatch pointer in word 0. */
static void *dispatch_key(const void *handle) {
    return handle ? *(void *const *)handle : NULL;
}

static InstanceRecord find_instance(void *key) {
    InstanceRecord value = {0};
    pthread_mutex_lock(&records_lock);
    for (InstanceRecord *p = instances; p; p = p->next) {
        if (p->key == key) {
            value = *p;
            break;
        }
    }
    pthread_mutex_unlock(&records_lock);
    return value;
}

static DeviceRecord find_device(void *key) {
    DeviceRecord value = {0};
    pthread_mutex_lock(&records_lock);
    for (DeviceRecord *p = devices; p; p = p->next) {
        if (p->key == key) {
            value = *p;
            break;
        }
    }
    pthread_mutex_unlock(&records_lock);
    return value;
}

static VkLayerInstanceCreateInfo *instance_link(const VkInstanceCreateInfo *info) {
    const VkBaseInStructure *node = (const VkBaseInStructure *)info->pNext;
    while (node) {
        if (node->sType == VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO) {
            VkLayerInstanceCreateInfo *link = (VkLayerInstanceCreateInfo *)node;
            if (link->function == VK_LAYER_LINK_INFO) return link;
        }
        node = node->pNext;
    }
    return NULL;
}

static VkLayerDeviceCreateInfo *device_link(const VkDeviceCreateInfo *info) {
    const VkBaseInStructure *node = (const VkBaseInStructure *)info->pNext;
    while (node) {
        if (node->sType == VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO) {
            VkLayerDeviceCreateInfo *link = (VkLayerDeviceCreateInfo *)node;
            if (link->function == VK_LAYER_LINK_INFO) return link;
        }
        node = node->pNext;
    }
    return NULL;
}

VKAPI_ATTR VkResult VKAPI_CALL vkCreateInstance(
        const VkInstanceCreateInfo *info, const VkAllocationCallbacks *allocator,
        VkInstance *instance) {
    if (!info || !instance) return VK_ERROR_INITIALIZATION_FAILED;
    VkLayerInstanceCreateInfo *link = instance_link(info);
    if (!link || !link->u.pLayerInfo) return VK_ERROR_INITIALIZATION_FAILED;
    PFN_vkGetInstanceProcAddr next_gipa = link->u.pLayerInfo->pfnNextGetInstanceProcAddr;
    if (!next_gipa) return VK_ERROR_INITIALIZATION_FAILED;
    PFN_vkCreateInstance next_create = (PFN_vkCreateInstance)next_gipa(NULL, "vkCreateInstance");
    if (!next_create) return VK_ERROR_INITIALIZATION_FAILED;

    link->u.pLayerInfo = link->u.pLayerInfo->pNext;
    VkResult result = next_create(info, allocator, instance);
    if (result != VK_SUCCESS) return result;
    InstanceRecord *rec = calloc(1, sizeof(*rec));
    if (!rec) {
        PFN_vkDestroyInstance destroy = (PFN_vkDestroyInstance)next_gipa(*instance, "vkDestroyInstance");
        if (destroy) destroy(*instance, allocator);
        return VK_ERROR_OUT_OF_HOST_MEMORY;
    }
    rec->handle = *instance;
    rec->key = dispatch_key(*instance);
    rec->gipa = next_gipa;
    pthread_mutex_lock(&records_lock);
    rec->next = instances;
    instances = rec;
    pthread_mutex_unlock(&records_lock);
    if (getenv("ZEITOP_DEBUG"))
        fprintf(stderr, "ZEITOP_VULKAN_INSTANCE_READY pid=%ld\n", (long)getpid());
    return VK_SUCCESS;
}

VKAPI_ATTR void VKAPI_CALL vkDestroyInstance(VkInstance instance,
                                             const VkAllocationCallbacks *allocator) {
    InstanceRecord value = find_instance(dispatch_key(instance));
    pthread_mutex_lock(&records_lock);
    InstanceRecord **cur = &instances;
    while (*cur) {
        if ((*cur)->handle == instance) {
            InstanceRecord *old = *cur;
            *cur = old->next;
            free(old);
            break;
        }
        cur = &(*cur)->next;
    }
    pthread_mutex_unlock(&records_lock);
    if (value.gipa) {
        PFN_vkDestroyInstance next = (PFN_vkDestroyInstance)value.gipa(instance, "vkDestroyInstance");
        if (next) next(instance, allocator);
    }
}

VKAPI_ATTR VkResult VKAPI_CALL vkCreateDevice(VkPhysicalDevice physical,
        const VkDeviceCreateInfo *info, const VkAllocationCallbacks *allocator,
        VkDevice *device) {
    if (!info || !device) return VK_ERROR_INITIALIZATION_FAILED;
    InstanceRecord inst = find_instance(dispatch_key(physical));
    VkLayerDeviceCreateInfo *link = device_link(info);
    if (!link || !link->u.pLayerInfo || !inst.handle) return VK_ERROR_INITIALIZATION_FAILED;
    PFN_vkGetInstanceProcAddr next_gipa = link->u.pLayerInfo->pfnNextGetInstanceProcAddr;
    PFN_vkGetDeviceProcAddr next_gdpa = link->u.pLayerInfo->pfnNextGetDeviceProcAddr;
    if (!next_gipa || !next_gdpa) return VK_ERROR_INITIALIZATION_FAILED;
    PFN_vkCreateDevice next_create = (PFN_vkCreateDevice)next_gipa(inst.handle, "vkCreateDevice");
    if (!next_create) return VK_ERROR_INITIALIZATION_FAILED;

    link->u.pLayerInfo = link->u.pLayerInfo->pNext;
    VkResult result = next_create(physical, info, allocator, device);
    if (result != VK_SUCCESS) return result;
    DeviceRecord *rec = calloc(1, sizeof(*rec));
    if (!rec) {
        PFN_vkDestroyDevice destroy = (PFN_vkDestroyDevice)next_gdpa(*device, "vkDestroyDevice");
        if (destroy) destroy(*device, allocator);
        return VK_ERROR_OUT_OF_HOST_MEMORY;
    }
    rec->key = dispatch_key(*device);
    rec->gdpa = next_gdpa;
    rec->present = (PFN_vkQueuePresentKHR)next_gdpa(*device, "vkQueuePresentKHR");
    rec->destroy = (PFN_vkDestroyDevice)next_gdpa(*device, "vkDestroyDevice");
    pthread_mutex_lock(&records_lock);
    rec->next = devices;
    devices = rec;
    pthread_mutex_unlock(&records_lock);
    if (getenv("ZEITOP_DEBUG"))
        fprintf(stderr, "ZEITOP_VULKAN_DEVICE_READY pid=%ld present=%d\n",
                (long)getpid(), rec->present != NULL);
    return VK_SUCCESS;
}

VKAPI_ATTR void VKAPI_CALL vkDestroyDevice(VkDevice device,
                                          const VkAllocationCallbacks *allocator) {
    DeviceRecord value = find_device(dispatch_key(device));
    pthread_mutex_lock(&records_lock);
    DeviceRecord **cur = &devices;
    while (*cur) {
        if ((*cur)->key == dispatch_key(device)) {
            DeviceRecord *old = *cur;
            *cur = old->next;
            free(old);
            break;
        }
        cur = &(*cur)->next;
    }
    pthread_mutex_unlock(&records_lock);
    if (value.destroy) value.destroy(device, allocator);
}

#if !defined(ZEITOP_OUTPUT_TELEMETRY) && !defined(ZEITOP_PRESENT_PROBE)
/* Per-process, one-shot prewarm: the app's FIRST present is held until
 * Zeitop changes its own private lsfg-vk TOML to bypass (if FG is OFF).
 * This is intentionally before calling the downstream lsfg-vk layer.
 * Do not mutate the canonical ~/.config/lsfg-vk/conf.toml.
 *
 * posix_spawnp is used rather than fork() inside the multithreaded Vulkan
 * process. The 2s deadline prevents deadlocking a game if the helper fails.
 */
static atomic_bool fg_gate_started = ATOMIC_VAR_INIT(false);
extern char **environ;

static void zeitop_fg_first_present_gate(void) {
    const char *token = getenv("ZEITOP_FG_WARMUP_TOKEN");
    if (!token || !*token) return;
    if (atomic_exchange_explicit(&fg_gate_started, true, memory_order_acq_rel))
        return;

    const char *root = getenv("ZEITOP_HOME");
    if (!root || root[0] != '/' || strlen(token) != 24) {
        fprintf(stderr, "Zeitop FG: invalid first-present gate arguments.\n");
        return;
    }
    for (const char *c = token; *c; c++) {
        if (!((*c >= '0' && *c <= '9') || (*c >= 'a' && *c <= 'f'))) {
            fprintf(stderr, "Zeitop FG: invalid session token.\n");
            return;
        }
    }
    char helper[4096];
    int written = snprintf(helper, sizeof helper, "%s/fg_live.py", root);
    if (written < 0 || (size_t)written >= sizeof helper) {
        fprintf(stderr, "Zeitop FG: project path is too long.\n");
        return;
    }
    char game_pid[32];
    snprintf(game_pid, sizeof game_pid, "%ld", (long)getpid());
    char *const argv[] = {
        (char *)"python3", (char *)"-B", helper, (char *)"warmup",
        (char *)root, (char *)token, game_pid, NULL
    };
    pid_t child = -1;
    int error = posix_spawnp(&child, "python3", NULL, NULL, argv, environ);
    if (error) {
        fprintf(stderr, "Zeitop FG: cannot start warmup helper (%d).\n", error);
        return;
    }
    struct timespec poll_delay = {.tv_sec = 0, .tv_nsec = 1000000L};
    int status = 0;
    for (int ms = 0; ms < 2000; ms++) {
        pid_t finished = waitpid(child, &status, WNOHANG);
        if (finished == child) {
            if (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
                fprintf(stderr, "Zeitop FG: first-present bypass failed.\n");
            return;
        }
        if (finished < 0 && errno != EINTR) {
            fprintf(stderr, "Zeitop FG: failed to observe warmup helper.\n");
            return;
        }
        nanosleep(&poll_delay, NULL);
    }
    kill(child, SIGTERM); /* Never hang the Vulkan present indefinitely. */
    (void)waitpid(child, &status, WNOHANG);
    fprintf(stderr, "Zeitop FG: warmup timed out; releasing the present.\n");
}

#endif /* first-present gate belongs only to the pacing layer */

#ifdef ZEITOP_PRESENT_PROBE
/* Compiled only in test fixtures; never included in production builds.
 * Place downstream of lsfg-vk to count generated OUTPUT presentations. */
static void zeitop_probe_output(void) {
    const char *path = getenv("ZEITOP_PROBE_OUTPUT");
    if (!path || path[0] != '/') return;
    int fd = open(path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0600);
    if (fd >= 0) {
        (void)write(fd, "P", 1);
        close(fd);
    }
}
#endif

VKAPI_ATTR VkResult VKAPI_CALL vkQueuePresentKHR(VkQueue queue, const VkPresentInfoKHR *info) {
    DeviceRecord rec = find_device(dispatch_key(queue));
    if (!rec.present) return VK_ERROR_EXTENSION_NOT_PRESENT;
#ifdef ZEITOP_PRESENT_PROBE
    zeitop_probe_output();
#elif defined(ZEITOP_OUTPUT_TELEMETRY)
    /* The last layer observes actual output after lsfg-vk, and must never
     * pace it. Report only successful downstream presentation calls. */
    VkResult result = rec.present(queue, info);
    if (result == VK_SUCCESS || result == VK_SUBOPTIMAL_KHR)
        zeitop_output_present();
    return result;
#else
    zeitop_fg_first_present_gate();
    zeitop_before_present();
#endif
    return rec.present(queue, info);
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetDeviceProcAddr(VkDevice device, const char *name) {
    if (!name) return NULL;
    if (!strcmp(name, "vkGetDeviceProcAddr")) return (PFN_vkVoidFunction)vkGetDeviceProcAddr;
    if (!strcmp(name, "vkQueuePresentKHR")) {
        DeviceRecord rec = find_device(dispatch_key(device));
        return rec.present ? (PFN_vkVoidFunction)vkQueuePresentKHR : NULL;
    }
    if (!strcmp(name, "vkDestroyDevice")) return (PFN_vkVoidFunction)vkDestroyDevice;
    DeviceRecord rec = find_device(dispatch_key(device));
    return rec.gdpa ? rec.gdpa(device, name) : NULL;
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetInstanceProcAddr(VkInstance instance, const char *name) {
    if (!name) return NULL;
    if (!strcmp(name, "vkGetInstanceProcAddr")) return (PFN_vkVoidFunction)vkGetInstanceProcAddr;
    if (!strcmp(name, "vkCreateInstance")) return (PFN_vkVoidFunction)vkCreateInstance;
    if (!strcmp(name, "vkCreateDevice")) return (PFN_vkVoidFunction)vkCreateDevice;
    if (!strcmp(name, "vkDestroyInstance")) return (PFN_vkVoidFunction)vkDestroyInstance;
    if (!strcmp(name, "vkGetDeviceProcAddr")) return (PFN_vkVoidFunction)vkGetDeviceProcAddr;
    if (!strcmp(name, "vkQueuePresentKHR")) return (PFN_vkVoidFunction)vkQueuePresentKHR;
    if (!strcmp(name, "vkDestroyDevice")) return (PFN_vkVoidFunction)vkDestroyDevice;
    InstanceRecord rec = find_instance(dispatch_key(instance));
    return rec.gipa ? rec.gipa(instance, name) : NULL;
}

VKAPI_ATTR VkResult VKAPI_CALL vkNegotiateLoaderLayerInterfaceVersion(VkNegotiateLayerInterface *info) {
    if (!info || info->loaderLayerInterfaceVersion < 2) return VK_ERROR_INITIALIZATION_FAILED;
    info->loaderLayerInterfaceVersion = 2;
    info->pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
    info->pfnGetDeviceProcAddr = vkGetDeviceProcAddr;
    info->pfnGetPhysicalDeviceProcAddr = NULL; /* no physical-device extensions */
    return VK_SUCCESS;
}
