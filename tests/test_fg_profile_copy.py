"""Regression: selecting another saved profile must offer an actionable Steam command."""
import fcntl
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONFIG = """version = 2
[global]
allow_fp16 = true

[[profile]]
name = "First Profile"
active_in = "first.exe"
multiplier = 2
flow_scale = 1.0
pacing_mode = "vsync"
performance_mode = false
override_present_mode = true
preserve_swapchain_image_count = false

[[profile]]
name = "Test Profile With Spaces"
multiplier = 3
flow_scale = 0.85
pacing_mode = "vsync"
performance_mode = true
override_present_mode = true
preserve_swapchain_image_count = false
"""


class TestFgProfileCopy(unittest.TestCase):
    def test_switch_profile_and_copy_without_editing_disk(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland session not available")
        lock_path = ROOT / "runtime" / "zeitop.lock"
        if lock_path.is_file():
            with lock_path.open("rb") as fh:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self.skipTest("Zeitop GUI is already running")
                else:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        with tempfile.TemporaryDirectory(dir=ROOT / "runtime", prefix="fg_copy_") as tmp:
            config = Path(tmp) / "conf.toml"
            config.write_text(CONFIG, encoding="utf-8")
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                       LSFGVK_CONFIG=str(config), ZEITOP_FG_COPY_TEST="1")
            run = subprocess.run([str(ROOT / "run.sh")], cwd=ROOT, env=env,
                                 capture_output=True, text=True, timeout=12)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ZEITOP_FG_COPY_PROFILE_OK", run.stdout,
                          run.stdout + run.stderr)
            self.assertEqual(config.read_text(), CONFIG)
            self.assertFalse(list(Path(tmp).glob("*.zeitop-bak-*")))
