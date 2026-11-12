"""External lsfg-vk v2 TOML editor: never touch the user's real config in tests."""
import hashlib
import os
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from fg_config import ConfigError, discover_config, load_config, save_config

SAMPLE = '''# Keep this comment
version = 2

[global]
allow_fp16 = true # important
log_level = "info"
custom_global = "untouched"

[[profile]]
name = "Baseline" # keep name comment
active_in = [ "vkcube", "vkcubepp" ]
multiplier = 2
flow_scale = 0.85
performance_mode = false
pacing_mode = "vsync"
override_present_mode = true
preserve_swapchain_image_count = false
some_future_option = 17

[[profile]]
name = "Windows"
active_in = "Game.exe"
multiplier = 3
flow_scale = 1.0
performance_mode = true
pacing_mode = "vsync"
override_present_mode = true
preserve_swapchain_image_count = false
'''


class TestLsfgConfig(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / ".config" / "lsfg-vk" / "conf.toml"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(SAMPLE, encoding="utf-8")

    def test_discovers_xdg_then_home_but_respects_override(self):
        special = self.home / "special" / "conf.toml"
        special.parent.mkdir()
        special.write_text(SAMPLE)
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "custom")}
        self.assertEqual(discover_config(env=env).resolve(), self.config.resolve())
        custom = self.home / "custom" / "lsfg-vk" / "conf.toml"
        custom.parent.mkdir(parents=True)
        custom.write_text(SAMPLE)
        self.assertEqual(discover_config(env=env), custom)
        env["LSFGVK_CONFIG"] = str(special)
        self.assertEqual(discover_config(env=env), special)

    def test_parse_two_profiles_and_defaults_without_mutation(self):
        before = self.config.read_bytes()
        result = load_config(self.config)
        self.assertEqual(result["version"], 2)
        self.assertEqual(len(result["profiles"]), 2)
        self.assertEqual(result["profiles"][0]["active_in"], ["vkcube", "vkcubepp"])
        self.assertEqual(result["profiles"][1]["active_in"], "Game.exe")
        self.assertEqual(result["global"]["allow_fp16"], True)
        self.assertEqual(result["revision"], hashlib.sha256(before).hexdigest())
        self.assertEqual(self.config.read_bytes(), before)

    def test_preserve_comments_future_keys_and_backup(self):
        os.chmod(self.config, 0o640)
        loaded = load_config(self.config)
        loaded["profiles"][0]["multiplier"] = 4
        loaded["global"]["log_level"] = "debug"
        saved = save_config(self.config, loaded, loaded["revision"], validator=None)
        self.assertTrue(saved["changed"])
        text = self.config.read_text()
        self.assertIn('# Keep this comment', text)
        self.assertIn('allow_fp16 = true # important', text)
        self.assertIn('name = "Baseline" # keep name comment', text)
        self.assertIn('some_future_option = 17', text)
        self.assertIn('custom_global = "untouched"', text)
        self.assertIn('multiplier = 4', text)
        self.assertIn('log_level = "debug"', text)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        b = Path(saved["backup"])
        self.assertTrue(b.exists())
        self.assertEqual(b.read_text(), SAMPLE)
        self.assertEqual(b.stat().st_mode & 0o777, 0o600)
        self.assertEqual(tomllib.loads(text)["profile"][1]["name"], "Windows")

    def test_inline_hash_inside_single_quoted_toml_is_not_a_comment(self):
        source = SAMPLE.replace('name = "Baseline" # keep name comment',
                                "name = 'A#B' # keep name comment")
        self.config.write_text(source)
        loaded = load_config(self.config)
        loaded["profiles"][0]["name"] = "New"
        saved = save_config(self.config, loaded, loaded["revision"], validator=None)
        self.assertTrue(saved["changed"])
        self.assertIn('name = "New" # keep name comment', self.config.read_text())

    def test_noop_does_not_write_or_create_backup(self):
        loaded = load_config(self.config)
        result = save_config(self.config, loaded, loaded["revision"], validator=None)
        self.assertFalse(result["changed"])
        self.assertFalse(list(self.config.parent.glob("*.zeitop-bak-*")))

    def test_reject_external_modification(self):
        state = load_config(self.config)
        self.config.write_text(SAMPLE + "\n# changed outside zeitop\n")
        state["profiles"][0]["multiplier"] = 3
        with self.assertRaisesRegex(ConfigError, "changed outside"):
            save_config(self.config, state, state["revision"], validator=None)
        self.assertIn("# changed outside zeitop", self.config.read_text())

    def test_add_and_remove_profile_without_loss_to_existing(self):
        state = load_config(self.config)
        state["profiles"] = [state["profiles"][1], {
            "source_index": None, "name": "New", "active_in": ["new.exe"],
            "multiplier": 4, "flow_scale": 1.0, "performance_mode": False,
            "pacing_mode": "vsync", "override_present_mode": True,
            "preserve_swapchain_image_count": False
        }]
        save_config(self.config, state, state["revision"], validator=None)
        parsed = tomllib.loads(self.config.read_text())
        self.assertEqual([p["name"] for p in parsed["profile"]], ["Windows", "New"])
        self.assertIn('custom_global = "untouched"', self.config.read_text())
        self.assertNotIn('some_future_option = 17', self.config.read_text())

    def test_invalid_value_leaves_file_unchanged(self):
        state = load_config(self.config)
        old = self.config.read_bytes()
        state["profiles"][0]["multiplier"] = 0
        with self.assertRaises(ConfigError):
            save_config(self.config, state, state["revision"], validator=None)
        self.assertEqual(self.config.read_bytes(), old)

    def test_reject_symlink_and_unsupported_version(self):
        link = self.home / "link.toml"
        link.symlink_to(self.config)
        with self.assertRaises(ConfigError):
            save_config(link, load_config(self.config), load_config(self.config)["revision"], validator=None)
        self.config.write_text(SAMPLE.replace("version = 2", "version = 1"))
        with self.assertRaisesRegex(ConfigError, "version"):
            load_config(self.config)

    def test_custom_multiplier_and_flow_scale_follow_v2_validation(self):
        state = load_config(self.config)
        state["profiles"][0]["multiplier"] = 6
        state["profiles"][0]["flow_scale"] = 0.25
        result = save_config(self.config, state, state["revision"], validator=None)
        self.assertTrue(result["changed"])
        parsed = tomllib.loads(self.config.read_text())
        self.assertEqual(parsed["profile"][0]["multiplier"], 6)
        self.assertEqual(parsed["profile"][0]["flow_scale"], 0.25)
        invalid = load_config(self.config)
        invalid["profiles"][0]["flow_scale"] = 0.1
        with self.assertRaisesRegex(ConfigError, "Flow Scale"):
            save_config(self.config, invalid, invalid["revision"], validator=None)

    def test_missing_file_can_be_created_when_saved(self):
        self.config.unlink()
        state = load_config(self.config)
        self.assertFalse(state["exists"])
        state["profiles"].append({
            "source_index": None, "name": "Default", "active_in": [],
            "multiplier": 2, "flow_scale": 1.0, "performance_mode": False,
            "pacing_mode": "vsync", "override_present_mode": True,
            "preserve_swapchain_image_count": False
        })
        result = save_config(self.config, state, state["revision"], validator=None)
        self.assertTrue(result["changed"])
        self.assertEqual(tomllib.loads(self.config.read_text())["version"], 2)
        self.assertIsNone(result["backup"])

    def test_dll_picker_requires_owned_existing_correct_name(self):
        state = load_config(self.config)
        invalid = self.home / "fake.dll"
        invalid.write_bytes(b"demo")
        state["global"]["dll"] = str(invalid)
        with self.assertRaisesRegex(ConfigError, "lsfg-vk.dll"):
            save_config(self.config, state, state["revision"], validator=None)
        valid = self.home / "lsfg-vk.dll"
        valid.write_bytes(b"owned for test")
        state["global"]["dll"] = str(valid)
        result = save_config(self.config, state, state["revision"], validator=None)
        self.assertTrue(result["changed"])
        self.assertEqual(tomllib.loads(self.config.read_text())["global"]["dll"], str(valid))

    def test_save_rejects_bad_cli_validation_without_touching_original(self):
        state = load_config(self.config)
        state["profiles"][0]["multiplier"] = 4
        original = self.config.read_bytes()
        import subprocess
        with patch("fg_config.subprocess.run", return_value=subprocess.CompletedProcess([], 4, "", "invalid")):
            with self.assertRaisesRegex(ConfigError, "validation"):
                save_config(self.config, state, state["revision"], validator="lsfg-vk-cli")
        self.assertEqual(self.config.read_bytes(), original)

if __name__ == "__main__":
    unittest.main()
