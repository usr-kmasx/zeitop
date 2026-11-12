#!/usr/bin/env python3
"""One-off test layer: pace first vkQueueSubmit after each present call."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/"runtime/audit_pacing/layer_submit_before"
path.mkdir(parents=True,exist_ok=True)
code=(ROOT/"vulkan_layer.c").read_text()
old="    PFN_vkQueuePresentKHR present;\n"
assert code.count(old)==1
code=code.replace(old,old+"    PFN_vkQueueSubmit submit;\n")
old='    rec->present = (PFN_vkQueuePresentKHR)next_gdpa(*device, "vkQueuePresentKHR");\n'
assert code.count(old)==1
code=code.replace(old,old+'    rec->submit = (PFN_vkQueueSubmit)next_gdpa(*device, "vkQueueSubmit");\n')
old="    zeitop_before_present();\n    return rec.present(queue, info);"
assert code.count(old)==1
code=code.replace(old,"    VkResult result = rec.present(queue, info);\n    submit_paced = 0;\n    return result;")
old="static pthread_mutex_t records_lock = PTHREAD_MUTEX_INITIALIZER;\n"
assert code.count(old)==1
code=code.replace(old,old+"static _Thread_local int submit_paced = 0;\n")
old='    if (!strcmp(name, "vkQueuePresentKHR")) {\n'
assert code.count(old)==1
code=code.replace(old,'    if (!strcmp(name, "vkQueueSubmit")) {\n        DeviceRecord rec = find_device(dispatch_key(device));\n        return rec.submit ? (PFN_vkVoidFunction)vkQueueSubmit : NULL;\n    }\n'+old)
old='    if (!strcmp(name, "vkQueuePresentKHR")) return (PFN_vkVoidFunction)vkQueuePresentKHR;\n'
assert code.count(old)==1
code=code.replace(old,old+'    if (!strcmp(name, "vkQueueSubmit")) return (PFN_vkVoidFunction)vkQueueSubmit;\n')
hook="""
VKAPI_ATTR VkResult VKAPI_CALL vkQueueSubmit(VkQueue queue, uint32_t submitCount,
        const VkSubmitInfo *pSubmits, VkFence fence) {
    DeviceRecord rec = find_device(dispatch_key(queue));
    if (!rec.submit) return VK_ERROR_INITIALIZATION_FAILED;
    if (!submit_paced) {
        zeitop_before_present();
        submit_paced = 1;
    }
    return rec.submit(queue, submitCount, pSubmits, fence);
}
"""
pos=code.index("VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetDeviceProcAddr")
code=code[:pos]+hook+"\n"+code[pos:]
(path/"vulkan_layer.c").write_text(code)
(path/"VkLayer_Zeitop.json").write_text("""{
  "file_format_version": "1.0.0",
  "layer": {
    "name": "VK_LAYER_ZEITOP_pacing",
    "type": "GLOBAL",
    "api_version": "1.4.0",
    "library_path": "./libzeitop-audit.so",
    "implementation_version": "1",
    "description": "Temporary project-local first-submit pacing experiment"
  }
}
""")
cmd=["cc","-std=gnu11","-O2","-Wall","-Wextra","-fPIC","-shared",
     "-Wl,-Bsymbolic-functions","-DZEITOP_PACING_ONLY","-I",str(ROOT/"vendor/vulkan"),
     "-o",str(path/"libzeitop-audit.so"),str(path/"vulkan_layer.c"),
     str(ROOT/"limiter.c"),"-pthread","-ldl"]
r=subprocess.run(cmd,capture_output=True,text=True)
assert r.returncode==0,r.stdout+r.stderr
print("Generated submit probe, no production source changed")
