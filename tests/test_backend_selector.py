"""Backend selection must never select an unsupported presentation scheduler."""
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TestBackendSelection(unittest.TestCase):
    def test_capability_gating_and_fallbacks(self):
        binary=ROOT/"runtime"/"test_backend_selector"
        built=subprocess.run(["cc","-std=c11","-O2","-Werror","-Wall","-Wextra",
             "-I"+str(ROOT/"pacing"),
             str(ROOT/"tests"/"backend_selector_test.c"),
             str(ROOT/"pacing"/"backend_selector.c"),
             "-o",str(binary)],capture_output=True,text=True,timeout=15)
        self.assertEqual(built.returncode,0,built.stdout+built.stderr)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("12 capability/fallback checks passed",result.stdout)
