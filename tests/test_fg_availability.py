"""External lsfg-vk detection does not mutate user config or install anything."""
import json
import tempfile
import unittest
from pathlib import Path

from fg_config import external_fg_available


class TestExternalFgAvailability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / ".config/lsfg-vk/conf.toml"
        self.config.parent.mkdir(parents=True)
        self.config.write_text("""version = 2
[global]
allow_fp16 = true
[[profile]]
name = "Test"
multiplier = 2
flow_scale = 1.0
pacing_mode = "vsync"
""")
        self.manifest = self.home / ".local/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json"
        self.manifest.parent.mkdir(parents=True)
        self.library = self.home / "liblsfg.so"
        self.library.write_bytes(b"external library placeholder")
        self.manifest.write_text(json.dumps({"layer": {
            "name": "VK_LAYER_LSFGVK_frame_generation",
            "library_path": str(self.library)
        }}))
        self.env = {"HOME": str(self.home), "XDG_DATA_HOME": str(self.home / ".local/share")}

    def test_installed_external_config_and_layer_available(self):
        before = self.config.read_bytes()
        self.assertTrue(external_fg_available(env=self.env))
        self.assertEqual(self.config.read_bytes(), before)

    def test_missing_library_does_not_claim_fg_available(self):
        self.library.unlink()
        self.assertFalse(external_fg_available(env=self.env))

    def test_missing_configuration_does_not_claim_fg_available(self):
        self.config.unlink()
        self.assertFalse(external_fg_available(env=self.env))

    def test_missing_proprietary_dll_path_does_not_claim_fg_available(self):
        self.config.write_text(self.config.read_text().replace(
            "allow_fp16 = true", 'dll = "/unavailable/lsfg-vk.dll"'))
        self.assertFalse(external_fg_available(env=self.env))


if __name__ == "__main__":
    unittest.main()
