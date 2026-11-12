"""Read real Vulkan present-timing caps without installing anything."""
import os
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class TestPresentTimingCapabilities(unittest.TestCase):
    def test_probe_reports_surface_scoped_feature_and_fallback_inputs(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Needs Wayland compositor session")
        binary=ROOT/"runtime"/"stage2"/"present_capability_probe"
        command=[
            "cc","-O2","-Wall","-Wextra","-Werror","-std=gnu11",
            "-I"+str(ROOT/"vendor"/"vulkan"),
            "-I"+str(ROOT/"runtime"/"audit_pacing"/"source"),
            str(ROOT/"tests"/"audit_presentation_timing.c"),
            "-o",str(binary),"-lvulkan","-lwayland-client"
        ]
        compiled=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        env=os.environ.copy()
        env["XDG_CACHE_HOME"]=str(ROOT/"runtime"/"cache")
        env["XDG_CONFIG_HOME"]=str(ROOT/"runtime"/"config")
        env["XDG_DATA_HOME"]=str(ROOT/"runtime"/"data")
        result=subprocess.run([str(binary)],cwd=ROOT,env=env,
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("GPU=",result.stdout)
        self.assertIn("presentTimingSupported=",result.stdout)
        self.assertIn("presentTimingFeature=",result.stdout)
        self.assertIn("VK_EXT_present_timing_device_extension=",result.stdout)
