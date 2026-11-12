"""Execute JS DOM guards without adding node packages."""
import subprocess
import unittest
from pathlib import Path

class TestUiGuards(unittest.TestCase):
    def test_right_click_keyboard_selection_and_brand_cursor(self):
        project = Path(__file__).resolve().parents[1]
        r = subprocess.run(["node", "tests/ui_guards.js"], cwd=project,
                           text=True, capture_output=True, timeout=12)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
