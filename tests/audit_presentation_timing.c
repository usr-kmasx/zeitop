/*
 * Audit-only Wayland presentation-timing capability probe.
 * Creates a temporary Wayland wl_surface, no system settings altered.
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>
#include "vulkan/vulkan_core.h"
#include "vulkan_wayland.h"

static struct wl_compositor *compositor;

static void global_added(void *data, struct wl_registry *registry,
                         uint32_t name, const char *interface, uint32_t version) {
    (void)data;
    if (!strcmp(interface, "wl_compositor")) {
        uint32_t v = version < 4 ? version : 4;
        compositor = wl_registry_bind(registry,name,&wl_compositor_interface,v);
    }
}
static void global_removed(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data;(void)registry;(void)name;
}
static const struct wl_registry_listener listener = {global_added,global_removed};

int main(void) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) {fputs("WAYLAND_CONNECT_FAILED\n",stderr);return 2;}
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry,&listener,NULL);
    if (wl_display_roundtrip(display) < 0 || !compositor) {
        fputs("WAYLAND_COMPOSITOR_NOT_AVAILABLE\n",stderr);return 3;
    }
    struct wl_surface *wl_surface = wl_compositor_create_surface(compositor);
    if (!wl_surface) return 4;

    const char *exts[] = {
        VK_KHR_SURFACE_EXTENSION_NAME,
        VK_KHR_WAYLAND_SURFACE_EXTENSION_NAME,
        VK_KHR_GET_SURFACE_CAPABILITIES_2_EXTENSION_NAME
    };
    VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,
                           .pApplicationName="Zeitop timing capability audit",
                           .apiVersion=VK_API_VERSION_1_3};
    VkInstanceCreateInfo instanceInfo={
        .sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo=&app,
        .enabledExtensionCount=3,
        .ppEnabledExtensionNames=exts
    };
    VkInstance instance=VK_NULL_HANDLE;
    VkResult result=vkCreateInstance(&instanceInfo,NULL,&instance);
    if (result) {fprintf(stderr,"vkCreateInstance=%d\n",result);return 5;}

    VkWaylandSurfaceCreateInfoKHR surfaceInfo = {
        .sType = VK_STRUCTURE_TYPE_WAYLAND_SURFACE_CREATE_INFO_KHR,
        .display = display, .surface = wl_surface
    };
    VkSurfaceKHR surface=VK_NULL_HANDLE;
    result=vkCreateWaylandSurfaceKHR(instance,&surfaceInfo,NULL,&surface);
    if (result) {fprintf(stderr,"vkCreateWaylandSurfaceKHR=%d\n",result);return 6;}

    uint32_t count=0;
    vkEnumeratePhysicalDevices(instance,&count,NULL);
    if (!count) {fputs("NO_VULKAN_PHYSICAL_DEVICE\n",stderr);return 7;}
    VkPhysicalDevice *gpus=calloc(count,sizeof(*gpus));
    vkEnumeratePhysicalDevices(instance,&count,gpus);
    for (uint32_t i=0;i<count;i++) {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(gpus[i],&props);
        printf("GPU=%s\n",props.deviceName);
        uint32_t extcount=0;
        vkEnumerateDeviceExtensionProperties(gpus[i],NULL,&extcount,NULL);
        VkExtensionProperties *props_ext=calloc(extcount,sizeof(*props_ext));
        vkEnumerateDeviceExtensionProperties(gpus[i],NULL,&extcount,props_ext);
        int has_extension=0;
        for(uint32_t j=0;j<extcount;j++) {
            if(!strcmp(props_ext[j].extensionName,VK_EXT_PRESENT_TIMING_EXTENSION_NAME))
                has_extension=1;
        }
        free(props_ext);

        VkPhysicalDevicePresentTimingFeaturesEXT timing_features={
            .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PRESENT_TIMING_FEATURES_EXT
        };
        VkPhysicalDeviceFeatures2 features={
            .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
            .pNext=&timing_features
        };
        vkGetPhysicalDeviceFeatures2(gpus[i],&features);

        VkPresentTimingSurfaceCapabilitiesEXT timing_caps={
            .sType=VK_STRUCTURE_TYPE_PRESENT_TIMING_SURFACE_CAPABILITIES_EXT
        };
        VkSurfaceCapabilities2KHR caps={
            .sType=VK_STRUCTURE_TYPE_SURFACE_CAPABILITIES_2_KHR,
            .pNext=&timing_caps
        };
        VkPhysicalDeviceSurfaceInfo2KHR surfaceInfo2={
            .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SURFACE_INFO_2_KHR,
            .surface=surface
        };
        result=vkGetPhysicalDeviceSurfaceCapabilities2KHR(gpus[i],&surfaceInfo2,&caps);
        printf("VK_EXT_present_timing_device_extension=%d\n",has_extension);
        printf("presentTimingFeature=%u absolute=%u relative=%u\n",
               timing_features.presentTiming,
               timing_features.presentAtAbsoluteTime,
               timing_features.presentAtRelativeTime);
        printf("surfaceCapabilityQuery=%d presentTimingSupported=%u absolute=%u relative=%u stages=0x%08x\n",
               result,timing_caps.presentTimingSupported,
               timing_caps.presentAtAbsoluteTimeSupported,
               timing_caps.presentAtRelativeTimeSupported,
               timing_caps.presentStageQueries);
        uint32_t count_modes=0;
        if (!vkGetPhysicalDeviceSurfacePresentModesKHR(gpus[i],surface,&count_modes,NULL) && count_modes < 16) {
            VkPresentModeKHR modes[16];
            if (!vkGetPhysicalDeviceSurfacePresentModesKHR(gpus[i],surface,&count_modes,modes)) {
                printf("Wayland present modes:");
                for(uint32_t j=0;j<count_modes;j++) printf(" %d",(int)modes[j]);
                puts("");
            }
        }
    }
    free(gpus);
    vkDestroySurfaceKHR(instance,surface,NULL);
    vkDestroyInstance(instance,NULL);
    wl_surface_destroy(wl_surface);
    wl_compositor_destroy(compositor);
    wl_registry_destroy(registry);
    wl_display_disconnect(display);
    return 0;
}
