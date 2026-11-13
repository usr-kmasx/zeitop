"""End-to-end smoke: click copy, inspect actual GTK clipboard, click X."""
import os
import fcntl
import subprocess
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class TestGuiSmoke(unittest.TestCase):
    def test_copy_and_close_via_actual_html_buttons(self):
        # Do not interfere with the user's running Zeitop GUI.
        lock_path = ROOT / "runtime" / "zeitop.lock"
        if lock_path.exists():
            with lock_path.open("rb") as current_lock:
                try:
                    fcntl.flock(current_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self.skipTest("Zeitop GUI is already running")
                else:
                    fcntl.flock(current_lock.fileno(), fcntl.LOCK_UN)
        env = os.environ.copy()
        env["ZEITOP_SMOKE_TEST"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            cp = subprocess.run(
                [str(ROOT / "run.sh")], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=12
            )
        except subprocess.TimeoutExpired as exc:
            self.fail(f"GUI smoke did not exit after the close click: {exc}")
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        self.assertIn("ZEITOP_SMOKE_DRAG_READY", cp.stdout, cp.stdout + cp.stderr)
        self.assertIn("ZEITOP_SMOKE_ICON_READY", cp.stdout, cp.stdout + cp.stderr)
        self.assertIn("ZEITOP_SMOKE_COPY_HANDLER_OK", cp.stdout, cp.stdout + cp.stderr)
        self.assertTrue(
            "ZEITOP_SMOKE_COPY_OK" in cp.stdout
            or "ZEITOP_SMOKE_COPY_UNVERIFIED_WAYLAND" in cp.stdout,
            cp.stdout + cp.stderr,
        )
        self.assertIn("ZEITOP_SMOKE_CLOSE_OK", cp.stdout, cp.stdout + cp.stderr)
