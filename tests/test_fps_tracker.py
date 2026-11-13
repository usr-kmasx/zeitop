"""Measured (never multiplier-estimated) source and downstream FPS."""
import unittest
from core import TelemetryTracker


class TestFpsTracker(unittest.TestCase):
    def test_source_and_output_are_independent_and_pid_scoped(self):
        track = TelemetryTracker()
        for i in range(81):
            t = 100.0 + i / 60.0
            # 30 source FPS, 60 output FPS: output timestamps are real events
            if i % 2 == 0:
                track.record(700, 1000.0 / 30.0, now=t)
            track.record_output(700, int(round(t * 1_000_000_000)), now=t)
        result = track.snapshot(now=100.0 + 80.0 / 60.0)
        self.assertEqual(result["pid"], 700)
        self.assertAlmostEqual(result["source_fps"], 30.0, delta=0.2)
        self.assertAlmostEqual(result["output_fps"], 60.0, delta=0.2)
        # An unrelated renderer must not be added to this process's FPS.
        for i in range(70):
            t = 100 + i / 120
            track.record_output(701, int(t * 1e9), now=t)
        self.assertAlmostEqual(track.snapshot(now=101.34)["output_fps"], 60.0, delta=0.2)

    def test_output_is_not_guessed_if_not_observed(self):
        track = TelemetryTracker()
        for i in range(45):
            track.record(800, 33.333, now=10.0 + i / 30.0)
        result = track.snapshot(now=11.48)
        self.assertAlmostEqual(result["source_fps"], 30.0, delta=0.2)
        self.assertIsNone(result["output_fps"])

    def test_reset_and_stale_frames_are_not_displayed(self):
        track = TelemetryTracker()
        for i in range(55):
            t = 50.0 + i / 60.0
            track.record(7, 16.667, now=t)
            track.record_output(7, int(t * 1e9), now=t)
        self.assertIsNotNone(track.snapshot(now=50.9)["output_fps"])
        track.reset_output()
        self.assertIsNone(track.snapshot(now=50.9)["output_fps"])
        # Source-frame and output-frame rates expire before the PID is pruned.
        self.assertIsNone(track.snapshot(now=52.12)["source_fps"])
        self.assertIsNone(track.snapshot(now=52.12)["output_fps"])

    def test_new_pid_does_not_inherit_output_from_previous_game(self):
        track = TelemetryTracker()
        for i in range(35):
            t=20.0 + i / 30
            track.record(123, 33.333, now=t)
            track.record_output(123, int(t * 1e9), now=t)
        for i in range(35):
            track.record(456, 33.333, now=21.5 + i / 30)
        current=track.snapshot(now=22.7)
        self.assertEqual(current["pid"], 456)
        self.assertIsNone(current["output_fps"])


if __name__ == "__main__":
    unittest.main()
