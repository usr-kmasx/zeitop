import os
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TestFrameRuntime(unittest.TestCase):
    def test_local_flag_and_precise_monotonic_clock(self):
        exe=ROOT/"runtime"/"test_frame_runtime"
        compiled=subprocess.run([
            "cc","-std=gnu11","-Wall","-Wextra","-Werror","-O2",
            "-I"+str(ROOT/"pacing"),
            str(ROOT/"tests"/"frame_runtime_test.c"),
            str(ROOT/"pacing"/"frame_runtime.c"),
            "-o",str(exe),"-pthread"
        ],capture_output=True,text=True,timeout=20)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        with tempfile.TemporaryDirectory(dir=ROOT/"runtime",prefix="zp_test_") as temp:
            runtime=Path(temp)/"runtime"
            runtime.mkdir()
            (runtime/"limit.state").write_text("1")
            test=subprocess.run([str(exe),temp],capture_output=True,text=True,timeout=15)
            self.assertEqual(test.returncode,0,test.stdout+test.stderr)
            self.assertIn("Runtime flag and monotonic wait passed",test.stdout)
