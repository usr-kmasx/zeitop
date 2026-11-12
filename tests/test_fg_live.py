"""lsfg-vk live bypass: canonical TOML untouched, runtime copy hot-reloads."""
import hashlib
import os
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path

from core import create_layout, is_enabled, is_fg_enabled, set_enabled
from fg_live import (LiveConfigError, prepare_live, remember_config,
                     render_effective, source_config, switch_live)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = '''# User's personal settings
version = 2

[global]
dll = "/test/owned/lsfg-vk.dll"
log_level = "info"
custom_global = "keep me"

[[profile]]
name = "Example One"
active_in = ["vkcube", "vkcubepp"]
multiplier = 3 # user comment
flow_scale = 0.85
performance_mode = true
pacing_mode = "vsync"
custom_field = 18

[[profile]]
name = "Example Two"
active_in = "Game.exe"
multiplier = 2
flow_scale = 1.0
performance_mode = false
pacing_mode = "vsync"
'''


class TestLiveFg(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fg_live_test_", dir=ROOT / "runtime")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        create_layout(self.root)
        self.config = self.root / "canonical.toml"
        self.config.write_text(SAMPLE)
        self.env = {"HOME": str(self.root), "LSFGVK_CONFIG": str(self.config)}

    def test_off_bypasses_all_profiles_and_keeps_unrelated_fields(self):
        source = self.config.read_bytes()
        result = render_effective(source, enabled=False)
        parsed = tomllib.loads(result.decode("utf-8"))
        self.assertEqual([p["multiplier"] for p in parsed["profile"]], [1, 1])
        self.assertIn("multiplier = 1 # user comment", result.decode())
        self.assertIn("custom_field = 18", result.decode())
        self.assertIn('custom_global = "keep me"', result.decode())
        self.assertEqual(self.config.read_bytes(), source)
        self.assertEqual(render_effective(source, enabled=True), source)

    def test_runtime_off_on_off_uses_single_private_generated_file(self):
        original = self.config.read_bytes()
        set_enabled(self.root, True)
        off_file = prepare_live(self.root, enabled=False, env=self.env)
        self.assertEqual([p["multiplier"] for p in tomllib.loads(off_file.read_text())["profile"]], [1, 1])
        self.assertEqual(stat.S_IMODE(off_file.stat().st_mode), 0o600)
        self.assertEqual(self.config.read_bytes(), original)
        on_file = prepare_live(self.root, enabled=True, env=self.env)
        self.assertEqual(on_file, off_file)
        self.assertEqual(on_file.read_bytes(), original)
        again = prepare_live(self.root, enabled=False, env=self.env)
        self.assertEqual([p["multiplier"] for p in tomllib.loads(again.read_text())["profile"]], [1, 1])
        self.assertTrue(is_enabled(self.root))
        self.assertFalse(is_fg_enabled(self.root))
        self.assertEqual(self.config.read_bytes(), original)

    def test_live_source_updates_do_not_require_restarting_game(self):
        live = prepare_live(self.root, enabled=True, env=self.env)
        text = self.config.read_text().replace("multiplier = 3", "multiplier = 4")
        self.config.write_text(text)
        prepare_live(self.root, enabled=True, env=self.env)
        self.assertEqual(tomllib.loads(live.read_text())["profile"][0]["multiplier"], 4)
        prepare_live(self.root, enabled=False, env=self.env)
        self.assertEqual(tomllib.loads(live.read_text())["profile"][0]["multiplier"], 1)
        self.assertIn("multiplier = 4", self.config.read_text())

    def test_selected_source_and_explicit_override(self):
        remember_config(self.root, self.config)
        self.assertEqual(source_config(self.root, env={"HOME": str(self.root)}), self.config)
        other = self.root / "other.toml"
        other.write_text(SAMPLE.replace("Example One", "Alternate"))
        self.assertEqual(source_config(self.root, env={"LSFGVK_CONFIG": str(other)}), other)
        self.assertEqual((self.root / "runtime/fg.selected-config").stat().st_mode & 0o777, 0o600)

    def test_child_inherited_runtime_copy_never_becomes_canonical(self):
        remember_config(self.root, self.config)
        live = prepare_live(self.root, enabled=False, env=self.env)
        selected = source_config(self.root, env={
            "HOME": str(self.root), "LSFGVK_CONFIG": str(live)
        })
        self.assertEqual(selected, self.config)
        with self.assertRaises(LiveConfigError):
            remember_config(self.root, live)
        self.assertEqual(self.config.read_text(), SAMPLE)

    def test_invalid_original_never_changes_state_or_source(self):
        remember_config(self.root, self.config)
        self.config.write_text("version = 1\n")
        with self.assertRaises(LiveConfigError):
            switch_live(self.root, True)
        self.assertFalse(is_fg_enabled(self.root))
        self.assertEqual(self.config.read_text(), "version = 1\n")

    def test_reject_symlinked_live_output(self):
        destination = self.root / "runtime/fg-live.conf.toml"
        destination.symlink_to(self.config)
        with self.assertRaises(LiveConfigError):
            prepare_live(self.root, enabled=False, env=self.env)
        self.assertEqual(self.config.read_text(), SAMPLE)

    def test_cli_preparation_stays_in_ignored_runtime(self):
        output = prepare_live(self.root, enabled=False, env=self.env)
        self.assertTrue(str(output).startswith(str(self.root / "runtime")))
        self.assertNotEqual(output, self.config)
        self.assertEqual(hashlib.sha256(self.config.read_bytes()).hexdigest(),
                         hashlib.sha256(SAMPLE.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
