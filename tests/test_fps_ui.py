"""DOM regression for measured source and generated-output FPS."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestFpsUi(unittest.TestCase):
    def test_fps_card_toggles_real_output_without_guess(self):
        result = subprocess.run(["node", "tests/fps_ui_dom.js"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FPS DOM controls OK", result.stdout)
