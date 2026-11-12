import tempfile
import unittest
from pathlib import Path

from core import create_layout, set_enabled, is_enabled, launch_option, profile_launch_option, parse_packet, severity


class TestCore(unittest.TestCase):
    def test_status_changes_without_restarting(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "runtime") as temp:
            root = Path(temp)
            create_layout(root)
            self.assertFalse(is_enabled(root))
            set_enabled(root, True)
            self.assertTrue(is_enabled(root))
            set_enabled(root, False)
            self.assertFalse(is_enabled(root))

    def test_launch_option_points_to_local_wrapper(self):
        root = Path("/home/a folder/zeitop")
        self.assertEqual(launch_option(root), "'/home/a folder/zeitop/zeitop-run' %command%")

    def test_profile_launch_command_has_safe_shell_quoting_and_no_zeitop_layer(self):
        self.assertEqual(
            profile_launch_option("2X"),
            "LSFGVK_PROFILE=2X %command%"
        )
        self.assertEqual(
            profile_launch_option("4x FG / 85% [Performance]"),
            "LSFGVK_PROFILE='4x FG / 85% [Performance]' %command%"
        )
        self.assertEqual(
            profile_launch_option("Do not; execute $(cmd)"),
            "LSFGVK_PROFILE='Do not; execute $(cmd)' %command%"
        )
        self.assertNotIn("zeitop-run", profile_launch_option("2X"))

    def test_parse_only_valid_telemetry(self):
        self.assertEqual(parse_packet(b"ZEITOP1 1202 33.371"), (1202, 33.371))
        for data in [b"oops", b"ZEITOP1 9 -1", b"ZEITOP1 9 nan", b"ZEITOP1 9 5001", b"ZEITOP1 0 32"]:
            self.assertIsNone(parse_packet(data))

    def test_graphed_severity_is_not_clamped(self):
        self.assertEqual(severity(33.3), "good")
        self.assertEqual(severity(36.0), "warn")
        self.assertEqual(severity(45.0), "bad")


if __name__ == "__main__":
    unittest.main()
