/*
 * Zeitop Stage 3: Wayland swapchain and VK_EXT_present_timing experiment.
 * Test program only: does not patch games, applications, or the Zeitop layer.
 */
#define VK_USE_PLATFORM_WAYLAND_KHR
#include <stdio.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include "vulkan/vulkan_core.h"
#include "vulkan_wayland.h"
#include "xdg-shell-client-protocol.h"
#include "timed_present_run.h"

static struct wl_compositor *compositor;
static struct xdg_wm_base *wm_base;
static int configured;
static int should_close;

static void registry_add(void *user, struct wl_registry *registry,
                         uint32_t name, const char *interface, uint32_t version) {
    (void)user;
    if (!strcmp(interface,wl_compositor_interface.name)) {
        compositor=wl_registry_bind(registry,name,&wl_compositor_interface,
                                     version<4?version:4);
    } else if (!strcmp(interface,xdg_wm_base_interface.name)) {
        wm_base=wl_registry_bind(registry,name,&xdg_wm_base_interface,
                                  version<3?version:3);
    }
}
static void registry_remove(void *user,struct wl_registry *registry,uint32_t name) {
    (void)user;(void)registry;(void)name;
}
static const struct wl_registry_listener registry_listener={registry_add,registry_remove};
static void wm_ping(void *user,struct xdg_wm_base *wm,uint32_t serial) {
    (void)user;xdg_wm_base_pong(wm,serial);
}
static const struct xdg_wm_base_listener wm_listener={.ping=wm_ping};
static void toplevel_configure(void *user,struct xdg_toplevel *top,
                               int32_t w,int32_t h,struct wl_array *states) {
    (void)user;(void)top;(void)w;(void)h;(void)states;
}
static void toplevel_close(void *user,struct xdg_toplevel *top) {
    (void)user;(void)top;should_close=1;
}
static const struct xdg_toplevel_listener toplevel_listener={
    .configure=toplevel_configure,.close=toplevel_close
};
static void surface_configure(void *user,struct xdg_surface *surface,uint32_t serial) {
    (void)user;
    xdg_surface_ack_configure(surface,serial);
    configured=1;
}
static const struct xdg_surface_listener surface_listener={.configure=surface_configure};
#define VK_CHECK(what,expr) do { \
    VkResult checked=(expr); \
    if (checked!=VK_SUCCESS) { \
        fprintf(stderr,"STAGE3_ERROR %s=%d\n",what,(int)checked); \
        return 20; \
    } \
} while(0)

static int enabled_device_extension(VkPhysicalDevice gpu,const char *name) {
    uint32_t count=0;
    if (vkEnumerateDeviceExtensionProperties(gpu,NULL,&count,NULL)!=VK_SUCCESS || !count)
        return 0;
    VkExtensionProperties *extensions=calloc(count,sizeof(*extensions));
    if (!extensions)return 0;
    VkResult result=vkEnumerateDeviceExtensionProperties(gpu,NULL,&count,extensions);
    int found=0;
    if (result==VK_SUCCESS) {
        for(uint32_t i=0;i<count;i++)
            if(!strcmp(name,extensions[i].extensionName)) found=1;
    }
    free(extensions);
    return found;
}

int main(int argc,char **argv) {
    int setup_only=argc>1 && !strcmp(argv[1],"--setup-only");
    struct wl_display *display=wl_display_connect(NULL);
    if(!display) {fputs("ZEITOP_WAYLAND_CONNECT_FAILED\n",stderr);return 2;}
    struct wl_registry *registry=wl_display_get_registry(display);
    wl_registry_add_listener(registry,&registry_listener,NULL);
    if(wl_display_roundtrip(display)<0 || !compositor || !wm_base) {
        fputs("ZEITOP_XDG_SHELL_UNAVAILABLE\n",stderr);return 3;
    }
    xdg_wm_base_add_listener(wm_base,&wm_listener,NULL);
    struct wl_surface *window=wl_compositor_create_surface(compositor);
    struct xdg_surface *xdg=xdg_wm_base_get_xdg_surface(wm_base,window);
    xdg_surface_add_listener(xdg,&surface_listener,NULL);
    struct xdg_toplevel *top=xdg_surface_get_toplevel(xdg);
    xdg_toplevel_add_listener(top,&toplevel_listener,NULL);
    xdg_toplevel_set_title(top,"Zeitop");
    xdg_toplevel_set_app_id(top,"zeitop-presentation-probe");
    wl_surface_commit(window);
    for(int attempts=0;attempts<5 && !configured;attempts++) {
        if(wl_display_roundtrip(display)<0) {
            fputs("ZEITOP_WAYLAND_CONFIGURE_FAILED\n",stderr);return 4;
        }
    }
    if(!configured) {fputs("ZEITOP_NO_XDG_CONFIGURE\n",stderr);return 4;}

    VkApplicationInfo app={
        .sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName="Zeitop",
        .apiVersion=VK_API_VERSION_1_3
    };
    const char *instance_extensions[]={
        VK_KHR_SURFACE_EXTENSION_NAME,
        VK_KHR_WAYLAND_SURFACE_EXTENSION_NAME,
        VK_KHR_GET_SURFACE_CAPABILITIES_2_EXTENSION_NAME
    };
    VkInstanceCreateInfo instance_create={
        .sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo=&app,
        .enabledExtensionCount=3,
        .ppEnabledExtensionNames=instance_extensions
    };
    VkInstance instance=VK_NULL_HANDLE;
    VK_CHECK("create_instance",vkCreateInstance(&instance_create,NULL,&instance));
    VkWaylandSurfaceCreateInfoKHR surface_create={
        .sType=VK_STRUCTURE_TYPE_WAYLAND_SURFACE_CREATE_INFO_KHR,
        .display=display,.surface=window
    };
    VkSurfaceKHR surface=VK_NULL_HANDLE;
    VK_CHECK("create_surface",vkCreateWaylandSurfaceKHR(instance,&surface_create,NULL,&surface));

    uint32_t gpu_count=0;
    VK_CHECK("enumerate_gpus",vkEnumeratePhysicalDevices(instance,&gpu_count,NULL));
    if(gpu_count==0 || gpu_count>16){fputs("ZEITOP_GPU_COUNT_UNSUPPORTED\n",stderr);return 5;}
    VkPhysicalDevice physical[16];
    VK_CHECK("enumerate_gpu_handles",vkEnumeratePhysicalDevices(instance,&gpu_count,physical));
    VkPhysicalDevice gpu=VK_NULL_HANDLE;
    uint32_t queue_family=UINT32_MAX;
    VkPresentTimingSurfaceCapabilitiesEXT timing_surface={
        .sType=VK_STRUCTURE_TYPE_PRESENT_TIMING_SURFACE_CAPABILITIES_EXT
    };
    for(uint32_t i=0;i<gpu_count;i++) {
        VkPhysicalDeviceProperties properties;
        vkGetPhysicalDeviceProperties(physical[i],&properties);
        if(properties.deviceType!=VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) continue;
        if(!enabled_device_extension(physical[i],VK_KHR_SWAPCHAIN_EXTENSION_NAME) ||
           !enabled_device_extension(physical[i],VK_EXT_PRESENT_TIMING_EXTENSION_NAME))
            continue;
        uint32_t families=0;
        vkGetPhysicalDeviceQueueFamilyProperties(physical[i],&families,NULL);
        if(families==0 || families>64)continue;
        VkQueueFamilyProperties family[64];
        vkGetPhysicalDeviceQueueFamilyProperties(physical[i],&families,family);
        for(uint32_t j=0;j<families;j++) {
            VkBool32 present=VK_FALSE;
            vkGetPhysicalDeviceSurfaceSupportKHR(physical[i],j,surface,&present);
            if((family[j].queueFlags & VK_QUEUE_GRAPHICS_BIT) && present) {
                queue_family=j;break;
            }
        }
        if(queue_family==UINT32_MAX) continue;
        VkPhysicalDeviceSurfaceInfo2KHR surfaceinfo={
            .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SURFACE_INFO_2_KHR,
            .surface=surface
        };
        VkSurfaceCapabilities2KHR caps={
            .sType=VK_STRUCTURE_TYPE_SURFACE_CAPABILITIES_2_KHR,
            .pNext=&timing_surface
        };
        if(vkGetPhysicalDeviceSurfaceCapabilities2KHR(physical[i],&surfaceinfo,&caps)!=VK_SUCCESS ||
           !timing_surface.presentTimingSupported ||
           !timing_surface.presentAtAbsoluteTimeSupported)continue;
        gpu=physical[i];
        fprintf(stderr,"ZEITOP_PROBE_GPU=%s\n",properties.deviceName);
        break;
    }
    if(!gpu){fputs("ZEITOP_NO_PRESENT_TIMING_GPU\n",stderr);return 6;}

    VkPhysicalDevicePresentTimingFeaturesEXT supported={
        .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PRESENT_TIMING_FEATURES_EXT
    };
    VkPhysicalDeviceFeatures2 gpu_features={
        .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
        .pNext=&supported
    };
    vkGetPhysicalDeviceFeatures2(gpu,&gpu_features);
    if(!supported.presentTiming || !supported.presentAtAbsoluteTime) {
        fputs("ZEITOP_PRESENT_TIMING_FEATURE_NOT_SUPPORTED\n",stderr);return 7;
    }
    float priority=1.f;
    VkDeviceQueueCreateInfo queuecreate={
        .sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex=queue_family,.queueCount=1,
        .pQueuePriorities=&priority
    };
    VkPhysicalDevicePresentTimingFeaturesEXT enabled={
        .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PRESENT_TIMING_FEATURES_EXT,
        .presentTiming=VK_TRUE,
        .presentAtAbsoluteTime=VK_TRUE
    };
    int calibration_extension=enabled_device_extension(
        gpu,VK_KHR_CALIBRATED_TIMESTAMPS_EXTENSION_NAME);
    const char *device_extensions[]={VK_KHR_SWAPCHAIN_EXTENSION_NAME,
                                    VK_EXT_PRESENT_TIMING_EXTENSION_NAME,
                                    VK_KHR_CALIBRATED_TIMESTAMPS_EXTENSION_NAME};
    VkDeviceCreateInfo create_device={
        .sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .pNext=&enabled,
        .queueCreateInfoCount=1,
        .pQueueCreateInfos=&queuecreate,
        .enabledExtensionCount=calibration_extension?3u:2u,
        .ppEnabledExtensionNames=device_extensions
    };
    VkDevice device=VK_NULL_HANDLE;
    VK_CHECK("create_device_with_timing",vkCreateDevice(gpu,&create_device,NULL,&device));
    VkQueue queue=VK_NULL_HANDLE;
    vkGetDeviceQueue(device,queue_family,0,&queue);

    VkSurfaceCapabilitiesKHR caps;
    VK_CHECK("surface_capabilities",vkGetPhysicalDeviceSurfaceCapabilitiesKHR(gpu,surface,&caps));
    if(!(caps.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT)) {
        fputs("ZEITOP_TRANSFER_DST_UNSUPPORTED\n",stderr);return 8;
    }
    uint32_t fmt_count=0;
    VK_CHECK("surface_formats_count",vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&fmt_count,NULL));
    if(!fmt_count || fmt_count>256) { fprintf(stderr,"ZEITOP_UNEXPECTED_SURFACE_FORMAT_COUNT=%u\n",fmt_count); return 9; }
    VkSurfaceFormatKHR formats[256];
    VK_CHECK("surface_formats",vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&fmt_count,formats));
    VkSurfaceFormatKHR fmt=formats[0];
    for(uint32_t i=0;i<fmt_count;i++) {
        if(formats[i].format==VK_FORMAT_B8G8R8A8_UNORM) {fmt=formats[i];break;}
    }
    VkExtent2D extent=caps.currentExtent;
    if(extent.width==UINT32_MAX) {
        extent.width=320;extent.height=200;
        if(extent.width<caps.minImageExtent.width)extent.width=caps.minImageExtent.width;
        if(extent.height<caps.minImageExtent.height)extent.height=caps.minImageExtent.height;
        if(extent.width>caps.maxImageExtent.width)extent.width=caps.maxImageExtent.width;
        if(extent.height>caps.maxImageExtent.height)extent.height=caps.maxImageExtent.height;
    }
    uint32_t image_count=caps.minImageCount+1;
    if(caps.maxImageCount && image_count>caps.maxImageCount)image_count=caps.maxImageCount;
    VkCompositeAlphaFlagBitsKHR alpha=VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    if(!(caps.supportedCompositeAlpha & alpha)) {
        for(uint32_t bit=1;bit<=8;bit*=2) {
            if(caps.supportedCompositeAlpha & bit) {
                alpha=(VkCompositeAlphaFlagBitsKHR)bit;break;
            }
        }
    }
    VkSwapchainCreateInfoKHR swap_create={
        .sType=VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
        .flags=VK_SWAPCHAIN_CREATE_PRESENT_TIMING_BIT_EXT,
        .surface=surface,
        .minImageCount=image_count,
        .imageFormat=fmt.format,
        .imageColorSpace=fmt.colorSpace,
        .imageExtent=extent,
        .imageArrayLayers=1,
        .imageUsage=VK_IMAGE_USAGE_TRANSFER_DST_BIT,
        .imageSharingMode=VK_SHARING_MODE_EXCLUSIVE,
        .preTransform=caps.currentTransform,
        .compositeAlpha=alpha,
        .presentMode=VK_PRESENT_MODE_FIFO_KHR,
        .clipped=VK_TRUE
    };
    VkSwapchainKHR swapchain=VK_NULL_HANDLE;
    VK_CHECK("create_timing_swapchain",vkCreateSwapchainKHR(device,&swap_create,NULL,&swapchain));
    puts("STAGE3_SWAPCHAIN_TIMING_READY");

    PFN_vkSetSwapchainPresentTimingQueueSizeEXT set_queue=
      (PFN_vkSetSwapchainPresentTimingQueueSizeEXT)vkGetDeviceProcAddr(device,
                   "vkSetSwapchainPresentTimingQueueSizeEXT");
    PFN_vkGetSwapchainTimeDomainPropertiesEXT get_domains=
      (PFN_vkGetSwapchainTimeDomainPropertiesEXT)vkGetDeviceProcAddr(device,
                   "vkGetSwapchainTimeDomainPropertiesEXT");
    PFN_vkGetSwapchainTimingPropertiesEXT get_properties=
      (PFN_vkGetSwapchainTimingPropertiesEXT)vkGetDeviceProcAddr(device,
                   "vkGetSwapchainTimingPropertiesEXT");
    PFN_vkGetPastPresentationTimingEXT get_past=
      (PFN_vkGetPastPresentationTimingEXT)vkGetDeviceProcAddr(device,
                   "vkGetPastPresentationTimingEXT");
    if(!set_queue || !get_domains || !get_properties || !get_past) {
        fputs("ZEITOP_TIMING_ENTRY_POINTS_MISSING\n",stderr);return 10;
    }

    VkSwapchainTimingPropertiesEXT properties={
        .sType=VK_STRUCTURE_TYPE_SWAPCHAIN_TIMING_PROPERTIES_EXT
    };
    uint64_t properties_counter=0;
    VK_CHECK("get_swapchain_timing_properties",
             get_properties(device,swapchain,&properties,&properties_counter));
    printf("ZEITOP_TIMING_REFRESH_DURATION=%" PRIu64 "\n",properties.refreshDuration);

    VkSwapchainTimeDomainPropertiesEXT domains={
        .sType=VK_STRUCTURE_TYPE_SWAPCHAIN_TIME_DOMAIN_PROPERTIES_EXT
    };
    uint64_t domain_counter=0;
    VK_CHECK("query_timing_domains",
             get_domains(device,swapchain,&domains,&domain_counter));
    printf("STAGE3_TIMING_DOMAIN_COUNT=%u\n",domains.timeDomainCount);
    if(domains.timeDomainCount==0 || domains.timeDomainCount>32) {
        fputs("ZEITOP_UNUSABLE_TIME_DOMAINS\n",stderr);return 11;
    }
    VkTimeDomainKHR time_domains[32]={0};
    uint64_t domain_ids[32]={0};
    domains.pTimeDomains=time_domains;
    domains.pTimeDomainIds=domain_ids;
    VK_CHECK("read_timing_domains",
             get_domains(device,swapchain,&domains,&domain_counter));
    for(uint32_t i=0;i<domains.timeDomainCount;i++) {
        printf("ZEITOP_TIMING_DOMAIN[%u]=%d id=%" PRIu64 "\n",
               i,time_domains[i],domain_ids[i]);
    }
    VK_CHECK("set_timing_queue_size",
             set_queue(device,swapchain,16));
    puts("STAGE3_TIMING_QUEUE_READY");
    int calibrated=0;
    if (calibration_extension) {
        PFN_vkGetCalibratedTimestampsKHR calibrate=
            (PFN_vkGetCalibratedTimestampsKHR)vkGetDeviceProcAddr(
                device,"vkGetCalibratedTimestampsKHR");
        if (calibrate) {
            for(uint32_t i=0;i<domains.timeDomainCount;i++) {
                if(time_domains[i]!=VK_TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT)continue;
                VkSwapchainCalibratedTimestampInfoEXT local={
                    .sType=VK_STRUCTURE_TYPE_SWAPCHAIN_CALIBRATED_TIMESTAMP_INFO_EXT,
                    .swapchain=swapchain,
                    .presentStage=VK_PRESENT_STAGE_IMAGE_FIRST_PIXEL_OUT_BIT_EXT,
                    .timeDomainId=domain_ids[i]
                };
                VkCalibratedTimestampInfoKHR info={
                    .sType=VK_STRUCTURE_TYPE_CALIBRATED_TIMESTAMP_INFO_KHR,
                    .pNext=&local,
                    .timeDomain=VK_TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT
                };
                uint64_t timestamp=0, deviation=0;
                VkResult rc=calibrate(device,1,&info,&timestamp,&deviation);
                printf("ZEITOP_CALIBRATE_RESULT=%d local_ns=%" PRIu64
                       " deviation_ns=%" PRIu64 "\n",rc,timestamp,deviation);
                if(rc==VK_SUCCESS && timestamp!=0) {
                    printf("ZEITOP_PRESENT_CLOCK=calibrated domain_id=%" PRIu64 "\n",
                           domain_ids[i]);
                    calibrated=1;
                }
                break;
            }
        }
    }
    if(!calibrated)puts("ZEITOP_PRESENT_CLOCK=unavailable");
    fflush(stdout);

    if (!setup_only) {
        if (!calibrated) {
            fputs("ZEITOP_CALIBRATED_CLOCK_REQUIRED\n",stderr);
            return 12;
        }
        unsigned frames=48;
        int schedule_enabled=!(argc==3 && !strcmp(argv[1],"--untimed-frames"));
        if(argc==3 && (!strcmp(argv[1],"--frames") ||
                       !strcmp(argv[1],"--untimed-frames"))) {
            unsigned long parsed=strtoul(argv[2],NULL,10);
            if(parsed<1 || parsed>240)return 13;
            frames=(unsigned)parsed;
        }
        uint64_t stage_domain_id=0;
        int stage_found=0;
        for(uint32_t i=0;i<domains.timeDomainCount;i++) {
            if(time_domains[i]==VK_TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT) {
                stage_domain_id=domain_ids[i];
                stage_found=1;
                break;
            }
        }
        if(!stage_found)return 14;
        PFN_vkGetCalibratedTimestampsKHR calibration=
          (PFN_vkGetCalibratedTimestampsKHR)vkGetDeviceProcAddr(
              device,"vkGetCalibratedTimestampsKHR");
        zp_timed_present_options run={
            .device=device,
            .queue=queue,
            .queue_family=queue_family,
            .swapchain=swapchain,
            .frame_count=frames,
            .schedule_enabled=schedule_enabled,
            .target_interval_ns=getenv("ZEITOP_TEST_TARGET_INTERVAL_NS") ?
                strtoull(getenv("ZEITOP_TEST_TARGET_INTERVAL_NS"),NULL,10) : 33333333ULL,
            .nearest_refresh=getenv("ZEITOP_TEST_NEAREST_REFRESH") &&
                !strcmp(getenv("ZEITOP_TEST_NEAREST_REFRESH"),"1"),
            .cpu_work_pattern=getenv("ZEITOP_TEST_WORK_PATTERN"),
            .cpu_work_seed=getenv("ZEITOP_TEST_WORK_SEED") ?
                (uint32_t)strtoul(getenv("ZEITOP_TEST_WORK_SEED"),NULL,10) : 1U,
            .stage_local_domain_id=stage_domain_id,
            .calibrate=calibration,
            .get_past=get_past,
            .feedback_path=schedule_enabled ?
                "runtime/stage3/present_feedback.csv" :
                "runtime/stage3/untimed_feedback.csv"
        };
        int result=zp_run_timed_present(&run);
        if(result!=0)return 40+result;
        VkSwapchainTimingPropertiesEXT after={
            .sType=VK_STRUCTURE_TYPE_SWAPCHAIN_TIMING_PROPERTIES_EXT
        };
        uint64_t after_counter=0;
        VkResult after_status=get_properties(device,swapchain,&after,&after_counter);
        printf("ZEITOP_POST_PRESENT_TIMING_PROPERTIES status=%d refreshDuration=%" PRIu64
               " refreshInterval=%" PRIu64 "\n",after_status,
               after.refreshDuration,after.refreshInterval);
    }

    vkDestroySwapchainKHR(device,swapchain,NULL);
    vkDestroyDevice(device,NULL);
    vkDestroySurfaceKHR(instance,surface,NULL);
    vkDestroyInstance(instance,NULL);
    xdg_toplevel_destroy(top);
    xdg_surface_destroy(xdg);
    wl_surface_destroy(window);
    xdg_wm_base_destroy(wm_base);
    wl_registry_destroy(registry);
    wl_compositor_destroy(compositor);
    wl_display_disconnect(display);
    return 0;
}
