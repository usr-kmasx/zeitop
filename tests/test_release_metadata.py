"""Keep release naming consistent without changing pacing behavior."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "V12-1.11.26"


class TestReleaseMetadata(unittest.TestCase):
    def test_release_version_is_canonical(self):
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), RELEASE)

    def test_readme_and_release_notes_match(self):
        self.assertIn(RELEASE, (ROOT / "README.md").read_text(encoding="utf-8"))
        notes = (ROOT / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        self.assertIn("# Zeitop " + RELEASE, notes)
        self.assertIn("Mortal Kombat 11", notes)

    def test_desktop_window_uses_canonical_version(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('(ROOT / "VERSION").read_text', app)
        self.assertIn('self.window.set_title(f"Zeitop {VERSION}")', app)
