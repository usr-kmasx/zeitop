/*
 * Project-local Zeitop Vulkan explicit layer.
 * Negotiates Vulkan loader interface v2 and chains through the next layer.
 * No system installation, no Vulkan API modifications outside this process.
 */
#define VK_NO_PROTOTYPES
#include "vulkan/vk_layer.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "frame_controller.h"
#include "frame_runtime.h"
#include "present_telemetry.h"

typedef struct InstanceRecord {
    void *key;
    VkInstance handle;
    PFN_vkGetInstanceProcAddr gipa;
    struct InstanceRecord *next;
} InstanceRecord;

typedef struct DeviceRecord {
    void *key;
    VkDevice handle;
    PFN_vkGetDeviceProcAddr gdpa;
    PFN_vkQueuePresentKHR present;
    PFN_vkAcquireNextImageKHR acquire;
    PFN_vkAcquireNextImage2KHR acquire2;
    PFN_vkDestroySwapchainKHR destroy_swapchain;
    PFN_vkDestroyDevice destroy;
    struct DeviceRecord *next;
} DeviceRecord;

static pthread_mutex_t records_lock = PTHREAD_MUTEX_INITIALIZER;
static InstanceRecord *instances;
static DeviceRecord *devices;
static zp_controller *pacer;
static pthread_once_t pacer_once = PTHREAD_ONCE_INIT;

static void init_pacer(void) {
    pacer = zp_controller_new(33333333ULL, zp_runtime_clock());
}
static zp_ticket reserve_acquisition(VkDevice device, VkSwapchainKHR swapchain) {
    pthread_once(&pacer_once, init_pacer);
    if (!pacer || !swapchain) return (zp_ticket){0};
    return zp_frame_reserve(pacer, (uintptr_t)device, (uint64_t)swapchain,
                            zp_runtime_enabled());
}

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
    rec->handle = *device;
    rec->gdpa = next_gdpa;
    rec->present = (PFN_vkQueuePresentKHR)next_gdpa(*device, "vkQueuePresentKHR");
    rec->acquire = (PFN_vkAcquireNextImageKHR)next_gdpa(*device, "vkAcquireNextImageKHR");
    rec->acquire2 = (PFN_vkAcquireNextImage2KHR)next_gdpa(*device, "vkAcquireNextImage2KHR");
    rec->destroy_swapchain = (PFN_vkDestroySwapchainKHR)next_gdpa(*device, "vkDestroySwapchainKHR");
    rec->destroy = (PFN_vkDestroyDevice)next_gdpa(*device, "vkDestroyDevice");
    pthread_mutex_lock(&records_lock);
    rec->next = devices;
    devices = rec;
    pthread_mutex_unlock(&records_lock);
    pthread_once(&pacer_once, init_pacer);
    if (getenv("ZEITOP_DEBUG")) {
        fprintf(stderr, "ZEITOP_VULKAN_DEVICE_READY pid=%ld present=%d\n",
                (long)getpid(), rec->present != NULL);
        if (pacer)
            fprintf(stderr, "ZEITOP_FRAME_CONTROLLER_READY pid=%ld acquire=%d acquire2=%d\n",
                    (long)getpid(), rec->acquire != NULL, rec->acquire2 != NULL);
    }
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
    zp_present_forget_device((uintptr_t)device);
    if (pacer) zp_device_forget(pacer, (uintptr_t)device);
    if (value.destroy) value.destroy(device, allocator);
}

VKAPI_ATTR VkResult VKAPI_CALL vkQueuePresentKHR(VkQueue queue, const VkPresentInfoKHR *info) {
    DeviceRecord rec = find_device(dispatch_key(queue));
    if (!rec.present) return VK_ERROR_EXTENSION_NOT_PRESENT;
    /* Record hook-to-hook cadence; NEVER wait on the telemetry path. */
    if (info && info->pSwapchains) {
        zp_clock clock=zp_runtime_clock();
        uint64_t now=clock.now_ns(clock.ctx);
        for (uint32_t i=0;i<info->swapchainCount;i++) {
            uint64_t elapsed=zp_present_elapsed((uintptr_t)rec.handle,
                               (uint64_t)info->pSwapchains[i],now);
            if (elapsed) (void)zp_present_send(elapsed);
        }
    }
    return rec.present(queue, info);
}


VKAPI_ATTR VkResult VKAPI_CALL vkAcquireNextImageKHR(
        VkDevice device, VkSwapchainKHR swapchain, uint64_t timeout,
        VkSemaphore semaphore, VkFence fence, uint32_t *index) {
    DeviceRecord rec = find_device(dispatch_key(device));
    if (!rec.acquire) return VK_ERROR_EXTENSION_NOT_PRESENT;
    zp_ticket ticket=zp_acquire_can_wait(timeout) ? reserve_acquisition(device,swapchain) : (zp_ticket){0};
    if (pacer) zp_frame_wait(pacer,ticket);
    VkResult result=rec.acquire(device,swapchain,timeout,semaphore,fence,index);
    if (pacer) zp_frame_complete(pacer,ticket,
                                  result==VK_SUCCESS || result==VK_SUBOPTIMAL_KHR);
    return result;
}
VKAPI_ATTR VkResult VKAPI_CALL vkAcquireNextImage2KHR(
        VkDevice device, const VkAcquireNextImageInfoKHR *info, uint32_t *index) {
    DeviceRecord rec = find_device(dispatch_key(device));
    if (!rec.acquire2) return VK_ERROR_EXTENSION_NOT_PRESENT;
    zp_ticket ticket={0};
    if (info && zp_acquire_can_wait(info->timeout)) ticket=reserve_acquisition(device,info->swapchain);
    if (pacer) zp_frame_wait(pacer,ticket);
    VkResult result=rec.acquire2(device,info,index);
    if (pacer) zp_frame_complete(pacer,ticket,
                                  result==VK_SUCCESS || result==VK_SUBOPTIMAL_KHR);
    return result;
}
VKAPI_ATTR void VKAPI_CALL vkDestroySwapchainKHR(
        VkDevice device, VkSwapchainKHR swapchain,
        const VkAllocationCallbacks *allocator) {
    DeviceRecord rec=find_device(dispatch_key(device));
    zp_present_forget((uintptr_t)device,(uint64_t)swapchain);
    if (pacer) zp_frame_forget(pacer,(uintptr_t)device,(uint64_t)swapchain);
    if (rec.destroy_swapchain) rec.destroy_swapchain(device,swapchain,allocator);
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetDeviceProcAddr(VkDevice device, const char *name) {
    if (!name) return NULL;
    if (!strcmp(name, "vkGetDeviceProcAddr")) return (PFN_vkVoidFunction)vkGetDeviceProcAddr;
    if (!strcmp(name, "vkAcquireNextImageKHR")) {
        DeviceRecord rec = find_device(dispatch_key(device));
        return rec.acquire ? (PFN_vkVoidFunction)vkAcquireNextImageKHR : NULL;
    }
    if (!strcmp(name, "vkAcquireNextImage2KHR")) {
        DeviceRecord rec = find_device(dispatch_key(device));
        return rec.acquire2 ? (PFN_vkVoidFunction)vkAcquireNextImage2KHR : NULL;
    }
    if (!strcmp(name, "vkDestroySwapchainKHR")) {
        DeviceRecord rec = find_device(dispatch_key(device));
        return rec.destroy_swapchain ? (PFN_vkVoidFunction)vkDestroySwapchainKHR : NULL;
    }
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
    if (!strcmp(name, "vkAcquireNextImageKHR")) return (PFN_vkVoidFunction)vkAcquireNextImageKHR;
    if (!strcmp(name, "vkAcquireNextImage2KHR")) return (PFN_vkVoidFunction)vkAcquireNextImage2KHR;
    if (!strcmp(name, "vkDestroySwapchainKHR")) return (PFN_vkVoidFunction)vkDestroySwapchainKHR;
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
