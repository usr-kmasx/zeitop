import tempfile
import unittest
from pathlib import Path

from core import create_layout, set_enabled, is_enabled, set_fg_enabled, is_fg_enabled, launch_option, parse_packet, parse_output_packet, severity


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

    def test_fg_and_limiter_have_independent_persisted_state(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "runtime") as temp:
            root = Path(temp)
            create_layout(root)
            self.assertFalse(is_fg_enabled(root))
            self.assertFalse(is_enabled(root))
            set_fg_enabled(root, True)
            self.assertTrue(is_fg_enabled(root))
            self.assertFalse(is_enabled(root))
            set_enabled(root, True)
            self.assertTrue(is_fg_enabled(root))
            self.assertTrue(is_enabled(root))
            set_fg_enabled(root, False)
            self.assertFalse(is_fg_enabled(root))
            self.assertTrue(is_enabled(root))
            self.assertEqual((root / "runtime/fg.state").read_text(), "0\n")

    def test_launch_option_points_to_local_wrapper(self):
        root = Path("/home/a folder/zeitop")
        self.assertEqual(launch_option(root), "'/home/a folder/zeitop/zeitop-run' %command%")

    def test_parse_only_valid_telemetry(self):
        self.assertEqual(parse_packet(b"ZEITOP1 1202 33.371"), (1202, 33.371))
        for data in [b"oops", b"ZEITOP1 9 -1", b"ZEITOP1 9 nan", b"ZEITOP1 9 5001", b"ZEITOP1 0 32"]:
            self.assertIsNone(parse_packet(data))

    def test_output_packet_rejects_malformed_or_source_data(self):
        self.assertEqual(parse_output_packet(b"ZEITOP2 1202 123456789"), (1202, 123456789))
        for packet in (b"ZEITOP1 1202 16.6", b"ZEITOP2 0 100",
                       b"ZEITOP2 1 -1", b"ZEITOP2 1 nan",
                       b"ZEITOP2 1 99 extra", b"ZEITOP2 2 0"):
            self.assertIsNone(parse_output_packet(packet))

    def test_graphed_severity_is_not_clamped(self):
        self.assertEqual(severity(33.3), "good")
        self.assertEqual(severity(36.0), "warn")
        self.assertEqual(severity(45.0), "bad")


if __name__ == "__main__":
    unittest.main()
