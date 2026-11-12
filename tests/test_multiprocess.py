"""Never let an active launcher erase the game's frame-time history."""
import unittest
from core import TelemetryTracker

class TestTelemetryMultiprocess(unittest.TestCase):
    def test_child_game_keeps_history_when_launcher_still_presents(self):
        track = TelemetryTracker()
        for n in range(10):
            track.record(100, 33.3, now=10.0+n*.03)
        self.assertEqual(track.snapshot(now=10.5)["pid"], 100)
        for n in range(5):
            track.record(200, 34.0+n, now=11.0+n*.04)
        track.record(100, 20.0, now=11.3)
        selected=track.snapshot(now=11.4)
        self.assertEqual(selected["pid"],200)
        self.assertEqual(len(selected["samples"]),5)
        self.assertEqual(selected["samples"][-1],38.0)

    def test_older_launcher_is_fallback_after_game_exits(self):
        track=TelemetryTracker()
        for n in range(5):
            track.record(100, 31.0, now=10+n*.1)
            track.record(200, 33.0, now=11+n*.1)
        self.assertEqual(track.snapshot(now=11.6)["pid"],200)
        track.record(100, 32.0,now=14)
        self.assertEqual(track.snapshot(now=14.1)["pid"],100)
        self.assertEqual(track.snapshot(now=17)["pid"],None)

    def test_short_splash_process_does_not_take_over(self):
        track=TelemetryTracker()
        for n in range(6):
            track.record(100,33.0,now=20+n*.03)
        track.record(200,10.0,now=21.0)
        self.assertEqual(track.snapshot(now=21.1)["pid"],100)
