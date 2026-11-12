"""The experimental Vulkan layer is an independent maintained source."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class TestSourceOwnership(unittest.TestCase):
    def test_candidate_is_source_not_generated_from_production(self):
        direct=(ROOT/"pacing/vulkan_frame_layer.c")
        build=(ROOT/"pacing/build_candidate.sh").read_text()
        self.assertTrue(direct.is_file())
        self.assertIn('"$ROOT/pacing/vulkan_frame_layer.c"',build)
        self.assertFalse((ROOT/"pacing/create_candidate.py").exists(),
                         "do not regenerate candidate via brittle source substitutions")
