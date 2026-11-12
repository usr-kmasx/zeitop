"""Real VK_EXT_present_timing: explicit device/swapchain setup on Wayland."""
import os
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/"runtime"/"stage3"

class TestRealPresentationTiming(unittest.TestCase):
    def test_stage3_swapchain_timing_setup(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("No Wayland display")
        build=subprocess.run(["sh",str(ROOT/"pacing"/"build_stage3.sh")],
            cwd=ROOT,capture_output=True,text=True,timeout=25)
        self.assertEqual(build.returncode,0,build.stdout+build.stderr)
        env=os.environ.copy()
        for key,relative in (
            ("XDG_CACHE_HOME","runtime/cache"),("XDG_CONFIG_HOME","runtime/config"),
            ("XDG_DATA_HOME","runtime/data"),("MESA_SHADER_CACHE_DIR","runtime/cache/mesa")):
            env[key]=str(ROOT/relative)
        run=subprocess.run([str(STAGE/"present_probe"),"--setup-only"],
            cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn("STAGE3_SWAPCHAIN_TIMING_READY",run.stdout)
        self.assertIn("STAGE3_TIMING_DOMAIN_COUNT=",run.stdout)
        self.assertIn("STAGE3_TIMING_QUEUE_READY",run.stdout)
        self.assertIn("ZEITOP_PRESENT_CLOCK=",run.stdout)
