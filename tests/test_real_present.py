"""Real native Vulkan presentation test using system vkcube.

Writes only in the Zeitop project. Does not alter games or Steam.
Skips rather than interfering with an open Zeitop GUI.
"""
import os
import shutil
import socket
import statistics
import subprocess
import unittest
from pathlib import Path

from core import is_enabled, parse_packet, set_enabled

ROOT = Path(__file__).resolve().parents[1]


class TestRealPresent(unittest.TestCase):
    def test_vkcube_sends_actual_frametime_and_paces(self):
        if not shutil.which("vkcube"):
            self.skipTest("vkcube not available")
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland not available")
        socket_path = ROOT / "runtime" / "zeitop.sock"
        if socket_path.exists():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                probe.connect(str(socket_path))
            except OSError:
                socket_path.unlink()  # stale project-only UNIX socket
            else:
                self.skipTest("Zeitop GUI already owns the telemetry socket")
            finally:
                probe.close()
        initial_state = is_enabled(ROOT)
        receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            receiver.bind(str(socket_path))
            receiver.settimeout(.25)
            set_enabled(ROOT, True)
            env = os.environ.copy()
            env["XDG_CACHE_HOME"] = str(ROOT / "runtime" / "cache")
            env["XDG_CONFIG_HOME"] = str(ROOT / "runtime" / "config")
            env["XDG_DATA_HOME"] = str(ROOT / "runtime" / "data")
            env["MESA_SHADER_CACHE_DIR"] = str(ROOT / "runtime" / "cache" / "mesa")
            command = [str(ROOT / "zeitop-run"), "vkcube", "--c", "60",
                       "--wsi", "wayland", "--width", "360", "--height", "240",
                       "--suppress_popups"]
            result = subprocess.run(command, env=env, capture_output=True,
                                    text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr[-2500:])
            samples = []
            while True:
                try:
                    data = receiver.recv(128)
                except socket.timeout:
                    break
                decoded = parse_packet(data)
                if decoded is not None:
                    samples.append(decoded[1])
            self.assertGreaterEqual(len(samples), 20, samples)
            median = statistics.median(samples)
            self.assertGreaterEqual(median, 29, samples)
            self.assertLess(median, 33.365, f'Pacing oversleep: median {median:.3f} ms')
        finally:
            set_enabled(ROOT, initial_state)
            receiver.close()
            if socket_path.exists():
                socket_path.unlink()
