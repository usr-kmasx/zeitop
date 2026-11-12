#include <vulkan/vulkan_core.h>
#include <stdio.h>

int main(void) {
    VkApplicationInfo app = {.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion=VK_API_VERSION_1_4};
    VkInstanceCreateInfo inst = {.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app};
    VkInstance vk = VK_NULL_HANDLE;
    VkResult rc = vkCreateInstance(&inst, NULL, &vk);
    if (rc != VK_SUCCESS) {
        fprintf(stderr,"create-instance=%d\n",(int)rc);
        return 2;
    }
    uint32_t n = 0;
    rc = vkEnumeratePhysicalDevices(vk,&n,NULL);
    if (rc != VK_SUCCESS || n == 0) return 3;
    VkPhysicalDevice gpu = VK_NULL_HANDLE;
    n = 1;
    rc = vkEnumeratePhysicalDevices(vk,&n,&gpu);
    if ((rc != VK_SUCCESS && rc != VK_INCOMPLETE) || !gpu) return 4;

    uint32_t count = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(gpu,&count,NULL);
    if (!count) return 5;
    VkQueueFamilyProperties family[64];
    if (count > 64) return 6;
    vkGetPhysicalDeviceQueueFamilyProperties(gpu,&count,family);
    uint32_t index=0;
    while(index < count && !(family[index].queueFlags & VK_QUEUE_GRAPHICS_BIT)) index++;
    if (index == count) return 7;
    float priority = 1.0f;
    VkDeviceQueueCreateInfo qinfo = {
        .sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex=index,
        .queueCount=1,
        .pQueuePriorities=&priority
    };
    const char *ext=VK_KHR_SWAPCHAIN_EXTENSION_NAME;
    VkDeviceCreateInfo deviceinfo = {
        .sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount=1,
        .pQueueCreateInfos=&qinfo,
        .enabledExtensionCount=1,
        .ppEnabledExtensionNames=&ext
    };
    VkDevice device=VK_NULL_HANDLE;
    rc=vkCreateDevice(gpu,&deviceinfo,NULL,&device);
    if (rc != VK_SUCCESS) {
        fprintf(stderr,"create-device=%d\n",(int)rc);
        return 8;
    }
    VkQueue queue=VK_NULL_HANDLE;
    vkGetDeviceQueue(device,index,0,&queue);
    PFN_vkVoidFunction present=vkGetDeviceProcAddr(device,"vkQueuePresentKHR");
    if (!queue || !present) return 9;
    puts("ZEITOP_PRESENT_INTERCEPTOR_OK");
    vkDestroyDevice(device,NULL);
    vkDestroyInstance(vk,NULL);
    return 0;
}
