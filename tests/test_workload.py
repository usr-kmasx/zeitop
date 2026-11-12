"""Workload probe contract (development-only, never installed in game layer)."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class TestVariableWorkload(unittest.TestCase):
    def test_deterministic_workload_program(self):
        binary=ROOT/"runtime"/"variable_workload_test"
        args=["cc","-std=c11","-O1","-Wall","-Wextra","-Werror",
              "-fsanitize=address,undefined","-fno-omit-frame-pointer",
              "-I"+str(ROOT/"pacing"),
              str(ROOT/"tests/workload_test.c"),
              str(ROOT/"pacing/workload.c"),
              "-o",str(binary)]
        built=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=15)
        self.assertEqual(built.returncode,0,built.stderr)
        result=subprocess.run([str(binary)],cwd=ROOT,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("deterministic, variable",result.stdout)
