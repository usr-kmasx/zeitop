#include <vulkan/vulkan_core.h>
#include <stdio.h>

int main(void) {
    VkApplicationInfo application = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .apiVersion = VK_API_VERSION_1_0
    };
    VkInstanceCreateInfo create = {
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &application
    };
    VkInstance instance = VK_NULL_HANDLE;
    VkResult result = vkCreateInstance(&create, NULL, &instance);
    if (result != VK_SUCCESS || instance == VK_NULL_HANDLE) {
        fprintf(stderr, "create-instance=%d\n", (int)result);
        return 2;
    }
    vkDestroyInstance(instance, NULL);
    puts("ZEITOP_INSTANCE_OK");
    return 0;
}
