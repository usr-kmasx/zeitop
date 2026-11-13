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

    def test_brand_uses_shared_app_icon_asset(self):
        """The header keeps the wordmark and uses the packaged app icon."""
        import struct
        project = Path(__file__).resolve().parents[1]
        html = (project / "ui/index.html").read_text(encoding="utf-8")
        css = (project / "ui/style.css").read_text(encoding="utf-8")
        asset = project / "ui/assets/zeitop-icon.png"
        self.assertIn('src="assets/zeitop-icon.png"', html)
        self.assertIn('class="brand"', html)
        self.assertIn('class="subbrand"', html)
        self.assertNotIn('<div class="mark"', html)
        self.assertIn('.mark{width:24px;height:24px;', css)
        data = asset.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", data[16:24]), (128, 128))
