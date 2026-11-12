#!/usr/bin/env python3
"""Build experimental Zeitop layers without modifying production source."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runtime" / "audit_pacing"
TEMPLATE = (ROOT / "vulkan_layer.c").read_text()

PRESENT = """    zeitop_before_present();
    return rec.present(queue, info);"""
ACQUIRE = """
VKAPI_ATTR VkResult VKAPI_CALL vkAcquireNextImageKHR(
        VkDevice device, VkSwapchainKHR swapchain, uint64_t timeout,
        VkSemaphore semaphore, VkFence fence, uint32_t *image_index) {
    DeviceRecord rec = find_device(dispatch_key(device));
    if (!rec.acquire) return VK_ERROR_EXTENSION_NOT_PRESENT;
    // This call precedes the game's rendering and MangoHud's present hook.
    PLACEHOLDER_WAIT
}
"""

def build(which):
    assert which in {"acquire_before", "acquire_after"}
    path = BASE / f"layer_{which}"
    path.mkdir(parents=True, exist_ok=True)
    source = TEMPLATE
    assert source.count(PRESENT) == 1
    source = source.replace(PRESENT, "    return rec.present(queue, info);")
    old="    PFN_vkQueuePresentKHR present;\n"
    assert source.count(old)==1
    source=source.replace(old, old+"    PFN_vkAcquireNextImageKHR acquire;\n")
    old='    rec->present = (PFN_vkQueuePresentKHR)next_gdpa(*device, "vkQueuePresentKHR");\n'
    assert source.count(old)==1
    source=source.replace(old, old+'    rec->acquire = (PFN_vkAcquireNextImageKHR)next_gdpa(*device, "vkAcquireNextImageKHR");\n')
    old='    if (!strcmp(name, "vkQueuePresentKHR")) {\n'
    assert source.count(old)==1
    source=source.replace(old, '    if (!strcmp(name, "vkAcquireNextImageKHR")) {\n        DeviceRecord rec = find_device(dispatch_key(device));\n        return rec.acquire ? (PFN_vkVoidFunction)vkAcquireNextImageKHR : NULL;\n    }\n'+old)
    old='    if (!strcmp(name, "vkQueuePresentKHR")) return (PFN_vkVoidFunction)vkQueuePresentKHR;\n'
    assert source.count(old)==1
    source=source.replace(old, old+'    if (!strcmp(name, "vkAcquireNextImageKHR")) return (PFN_vkVoidFunction)vkAcquireNextImageKHR;\n')
    place=source.index("VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetDeviceProcAddr")
    source=source[:place]+ACQUIRE+source[place:]
    # Need declaration visible before vkGetInstanceProcAddr / procaddr hook uses.
    if which=="acquire_before":
        code="""    zeitop_before_present();
    return rec.acquire(device, swapchain, timeout, semaphore, fence, image_index);"""
    else:
        code="""    VkResult result = rec.acquire(device, swapchain, timeout, semaphore, fence, image_index);
    if (result == VK_SUCCESS || result == VK_SUBOPTIMAL_KHR)
        zeitop_before_present();
    return result;"""
    source=source.replace("PLACEHOLDER_WAIT",code)
    (path/"vulkan_layer.c").write_text(source)
    (path/"VkLayer_Zeitop.json").write_text("""{
  "file_format_version": "1.0.0",
  "layer": {
    "name": "VK_LAYER_ZEITOP_pacing",
    "type": "GLOBAL",
    "api_version": "1.4.0",
    "library_path": "./libzeitop-audit.so",
    "implementation_version": "1",
    "description": "Project-local frame-cycle pacing experiment"
  }
}
""")
    args=["cc","-std=gnu11","-O2","-Wall","-Wextra","-fPIC","-shared",
          "-Wl,-Bsymbolic-functions","-DZEITOP_PACING_ONLY","-I",str(ROOT/"vendor"/"vulkan"),
          "-o",str(path/"libzeitop-audit.so"),str(path/"vulkan_layer.c"),
          str(ROOT/"limiter.c"),"-pthread","-ldl"]
    check=subprocess.run(args,capture_output=True,text=True,timeout=25)
    if check.returncode:
        raise RuntimeError(check.stdout + check.stderr)
    print(which, "built at", path, flush=True)

if __name__=="__main__":
    for mode in sys.argv[1:] or ["acquire_before","acquire_after"]:
        build(mode)
