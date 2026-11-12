"""Prevent personal computer paths from being committed to Zeitop."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestPortablePaths(unittest.TestCase):
    def test_no_personal_home_or_mounted_user_paths(self):
        files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                               cwd=ROOT, text=True, capture_output=True, check=True).stdout.splitlines()
        bad = []
        for relative in files:
            p = ROOT / relative
            if not p.is_file():
                continue
            content = p.read_bytes()
            if b"\\x00" in content:
                continue
            text = content.decode("utf-8", "replace")
            # Fake fixtures with spaces are not real private user directories.
            if re.search(r"/home/[A-Za-z0-9_-]+/", text):
                bad.append(relative)
            if re.search(r"/run/media/[A-Za-z0-9_-]+/", text):
                bad.append(relative)
        self.assertEqual(sorted(set(bad)), [])

    def test_steam_example_is_generic_and_runtime_copy_is_dynamic(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("'/absolute/path/to/zeitop/zeitop-run' %command%", readme)
        self.assertIn("computed from your installation directory", readme)
        from core import launch_option
        self.assertEqual(launch_option(Path("/opt/another location/zeitop")),
                         "'/opt/another location/zeitop/zeitop-run' %command%")

    def test_timing_probe_does_not_store_computer_specific_output_paths(self):
        source = (ROOT / "tests/stage3_present_probe.c").read_text(encoding="utf-8")
        self.assertIn('"runtime/stage3/present_feedback.csv"', source)
        self.assertIn('"runtime/stage3/untimed_feedback.csv"', source)
