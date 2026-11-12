"""Verify Vulkan loader actually loads and initializes the project-local layer."""
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestVulkanLayer(unittest.TestCase):
    def test_32bit_loader_initializes_matching_layer(self):
        probe = ROOT / "tests" / "vulkan_instance_probe.c"
        binary = ROOT / "runtime" / "zeitop-vulkan-probe32"
        built = subprocess.run(
            ["gcc", "-m32", "-std=c11", "-O2", "-Wall", "-Wextra",
             "-I"+str(ROOT/"vendor"/"vulkan"), str(probe),
             "-o", str(binary), "-lvulkan"],
            capture_output=True,text=True,timeout=20)
        self.assertEqual(built.returncode,0,built.stderr)
        env = dict(os.environ, ZEITOP_DEBUG="1",
                   XDG_CACHE_HOME=str(ROOT/"runtime"/"cache"),
                   MESA_SHADER_CACHE_DIR=str(ROOT/"runtime"/"cache"/"mesa"))
        result = subprocess.run([str(ROOT/"zeitop-run"),str(binary)],
                                env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("ZEITOP_VULKAN_INSTANCE_READY",result.stderr)
        self.assertIn("ZEITOP_INSTANCE_OK",result.stdout)

    def test_loader_initializes_real_layer_through_wrapper(self):
        env = dict(os.environ)
        env["ZEITOP_DEBUG"] = "1"
        env["XDG_CACHE_HOME"] = str(ROOT/"runtime"/"cache")
        env["MESA_SHADER_CACHE_DIR"] = str(ROOT/"runtime"/"cache"/"mesa")
        r = subprocess.run([str(ROOT/"zeitop-run"),"vulkaninfo","--summary"],
                           env=env,capture_output=True,text=True,timeout=25)
        self.assertEqual(r.returncode,0,r.stderr[-2500:])
        self.assertIn("ZEITOP_VULKAN_INSTANCE_READY",r.stderr)

    def test_device_with_swapchain_can_get_present_interceptor(self):
        probe = ROOT / "tests" / "vulkan_probe.c"
        binary = ROOT / "runtime" / "zeitop-vulkan-probe"
        compile_result = subprocess.run(
            ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra",
             "-I"+str(ROOT/"vendor"/"vulkan"), str(probe),
             "-o", str(binary), "-lvulkan"],
            capture_output=True,text=True,timeout=20)
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
        env = dict(os.environ, ZEITOP_DEBUG="1",
                   XDG_CACHE_HOME=str(ROOT/"runtime"/"cache"),
                   MESA_SHADER_CACHE_DIR=str(ROOT/"runtime"/"cache"/"mesa"))
        result = subprocess.run([str(ROOT/"zeitop-run"),str(binary)],
                                env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn("ZEITOP_VULKAN_DEVICE_READY", result.stderr)
        self.assertIn("present=1", result.stderr)
        self.assertIn("ZEITOP_PRESENT_INTERCEPTOR_OK",result.stdout)
