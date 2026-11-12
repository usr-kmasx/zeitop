"""Project-local frame pacing controller contract tests."""
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class TestFrameController(unittest.TestCase):
    def test_unit_controller(self):
        target=ROOT/"runtime"/"frame_controller_test"
        target.parent.mkdir(parents=True,exist_ok=True)
        compile_command=[
            "cc","-std=c11","-Wall","-Wextra","-Werror","-O1",
            "-fsanitize=address,undefined","-fno-omit-frame-pointer",
            "-I"+str(ROOT/"pacing"),
            str(ROOT/"tests"/"frame_controller_test.c"),
            str(ROOT/"pacing"/"frame_controller.c"),
            "-o",str(target),"-pthread"
        ]
        build=subprocess.run(compile_command,cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(build.returncode,0,build.stdout+build.stderr)
        r=subprocess.run([str(target)],cwd=ROOT,capture_output=True,text=True,timeout=12)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn("8 deterministic checks passed",r.stdout)
