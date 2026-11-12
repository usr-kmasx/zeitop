"""Actually queue timed Vulkan presents and collect driver timestamps (Wayland)."""
import csv
import os
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT/"runtime"/"stage3"/"present_probe"
FEEDBACK=ROOT/"runtime"/"stage3"/"present_feedback.csv"

class TestActualPresentTiming(unittest.TestCase):
    def test_absolute_target_and_real_driver_feedback(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland needed")
        compile_result=subprocess.run(["sh",str(ROOT/"pacing"/"build_stage3.sh")],
            cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(compile_result.returncode,0,compile_result.stderr)
        env=os.environ.copy()
        for key,rel in (("XDG_CACHE_HOME","runtime/cache"),
                        ("XDG_CONFIG_HOME","runtime/config"),
                        ("XDG_DATA_HOME","runtime/data"),
                        ("MESA_SHADER_CACHE_DIR","runtime/cache/mesa")):
            env[key]=str(ROOT/rel)
        if FEEDBACK.exists(): FEEDBACK.unlink()
        result=subprocess.run([str(EXE),"--frames","48"],
                              cwd=ROOT,env=env,capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("ZEITOP_PRESENTS_SUBMITTED=48",result.stdout)
        self.assertIn("ZEITOP_TARGETING_ACTIVE=1",result.stdout)
        self.assertIn("ZEITOP_REQUESTED_INTERVAL_NS=33333333",result.stdout)
        self.assertIn("ZEITOP_POST_PRESENT_TIMING_PROPERTIES status=0",result.stdout)
        self.assertIn("ZEITOP_PRESENT_FEEDBACK_COUNT=",result.stdout)
        self.assertTrue(FEEDBACK.exists())
        with FEEDBACK.open(newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertGreaterEqual(len(rows),20)
        self.assertTrue(all(int(r["first_pixel_out_ns"])>0 for r in rows))
        self.assertGreater(len(set(r["first_pixel_out_ns"] for r in rows)),20)

    def test_no_target_time_still_produces_real_feedback(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland needed")
        env=os.environ.copy()
        for key,rel in (("XDG_CACHE_HOME","runtime/cache"),
                        ("XDG_CONFIG_HOME","runtime/config"),
                        ("XDG_DATA_HOME","runtime/data")):
            env[key]=str(ROOT/rel)
        untimed=ROOT/"runtime"/"stage3"/"untimed_feedback.csv"
        if untimed.exists():untimed.unlink()
        run=subprocess.run([str(EXE),"--untimed-frames","48"],
                           cwd=ROOT,env=env,capture_output=True,text=True,timeout=25)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn("ZEITOP_PRESENTS_SUBMITTED=48",run.stdout)
        self.assertIn("ZEITOP_TARGETING_ACTIVE=0",run.stdout)
        self.assertTrue(untimed.exists())
        with untimed.open(newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertGreaterEqual(len(rows),20)
        self.assertTrue(all(int(r["target_time_ns"])==0 for r in rows))
        self.assertTrue(all(int(r["first_pixel_out_ns"])>0 for r in rows))
