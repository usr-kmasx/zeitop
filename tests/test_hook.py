import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestNativeLimiter(unittest.TestCase):
    def test_vulkan_function_pointer_paces_and_live_toggle(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "runtime") as temporary:
            folder = Path(temporary)
            (folder / "runtime").mkdir()
            (folder / "runtime" / "limit.state").write_text("1\n")
            dummy = folder / "libfakevulkan.so"
            hook = folder / "libzeitop.so"
            probe = folder / "probe"
            for args in [
                ["gcc", "-shared", "-fPIC", "-o", str(dummy), str(ROOT / "tests/fake_vulkan.c")],
                ["gcc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-o", str(hook), str(ROOT / "limiter.c"), "-ldl"],
                ["gcc", "-o", str(probe), str(ROOT / "tests/probe.c"), "-L", str(folder), "-lfakevulkan", f"-Wl,-rpath,{folder}"],
            ]:
                result = subprocess.run(args, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            env = dict(os.environ, LD_PRELOAD=str(hook), ZEITOP_HOME=str(folder))
            output = subprocess.run([str(probe)], capture_output=True, text=True, env=env, timeout=10)
            self.assertEqual(output.returncode, 0, output.stderr)
            intervals = [float(n) for n in output.stdout.strip().splitlines()]
            self.assertEqual(len(intervals), 8)
            self.assertTrue(all(28.5 <= n < 65 for n in intervals[:4]), intervals)
            self.assertTrue(all(n < 15 for n in intervals[5:]), intervals)


if __name__ == "__main__":
    unittest.main()
