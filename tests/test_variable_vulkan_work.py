"""Integration test: synthetic CPU work runs on the app's rendering path."""
import os
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TestVulkanVariableWork(unittest.TestCase):
    def test_probe_applies_real_cpu_work_before_submit(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland unavailable")
        built=subprocess.run(["sh","pacing/build_stage3.sh"],cwd=ROOT,
                             capture_output=True,text=True,timeout=20)
        self.assertEqual(built.returncode,0,built.stderr)
        env=os.environ.copy()
        env.update({
            "ZEITOP_TEST_WORK_PATTERN":"40",
            "ZEITOP_TEST_WORK_SEED":"773",
            "XDG_CACHE_HOME":str(ROOT/"runtime/cache"),
            "XDG_CONFIG_HOME":str(ROOT/"runtime/config"),
            "XDG_DATA_HOME":str(ROOT/"runtime/data"),
            "MESA_SHADER_CACHE_DIR":str(ROOT/"runtime/cache/mesa"),
        })
        run=subprocess.run([str(ROOT/"runtime/stage3/present_probe"),
                            "--untimed-frames","12"],env=env,cwd=ROOT,
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn("ZEITOP_TEST_WORK_PATTERN=40",run.stdout)
        self.assertIn("ZEITOP_CPU_WORK_NS_TOTAL=480000000",run.stdout)
        self.assertIn("ZEITOP_PRESENTS_SUBMITTED=12",run.stdout)
