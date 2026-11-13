"""Real 64-bit Vulkan integration: Zeitop source FPS and downstream lsfg output.

All mutable paths are test-local under ignored runtime/. Never writes the
user's lsfg-vk config, main GUI socket, game settings or system Vulkan files.
"""
import collections
import json
import os
import re
import select
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from core import TelemetryTracker, parse_output_packet, parse_packet
from fg_config import discover_config, external_fg_available, load_config
from fg_live import remember_config, remember_profile, switch_live

ROOT = Path(__file__).resolve().parents[1]


class TestFpsLive(unittest.TestCase):
    def test_downstream_output_is_measured_without_relimiting_generated_frames(self):
        if not os.environ.get("WAYLAND_DISPLAY") or not shutil.which("vkcube"):
            self.skipTest("Wayland + vkcube unavailable")
        if not external_fg_available():
            self.skipTest("External lsfg-vk unavailable")
        profiles = load_config(discover_config())["profiles"]
        selected = next((p for p in profiles if p["multiplier"] == 2), None)
        if selected is None:
            self.skipTest("No external 2x profile available")

        with tempfile.TemporaryDirectory(prefix="zeitop_fps_live_", dir=ROOT / "runtime") as temp:
            root = Path(temp)
            for name in ("zeitop-run", "fg_live.py", "fg_ipc.py", "fg_config.py", "core.py"):
                shutil.copy2(ROOT / name, root / name)
            (root / "runtime").mkdir()
            (root / "runtime/vulkan").symlink_to(ROOT / "runtime/vulkan", target_is_directory=True)
            for name in ("libzeitop-gl.so", "libzeitop-gl32.so"):
                (root / "runtime" / name).symlink_to(ROOT / "runtime" / name)
            text = discover_config().read_text(encoding="utf-8")
            text = re.sub(r'(?m)^[ \t]*log_file[ \t]*=.*$',
                          'log_file = ' + json.dumps(str(root / "fg.log")), text)
            source = root / "config.toml"
            source.write_text(text)
            original = source.read_bytes()
            remember_config(root, source)
            remember_profile(root, source, selected["name"])
            (root / "runtime/limit.state").write_text("0\n")
            (root / "runtime/fg.state").write_text("0\n")
            env = dict(os.environ)
            for key in ("VK_LAYER_PATH", "VK_ADD_LAYER_PATH", "VK_INSTANCE_LAYERS",
                        "VK_LOADER_LAYERS_ENABLE", "VK_LOADER_LAYERS_DISABLE"):
                env.pop(key, None)
            env["LSFGVK_CONFIG"] = str(source)
            env["LSFGVK_PROFILE"] = selected["name"]
            proc = None
            listener = None
            try:
                with (root / "stdout.log").open("wb") as out, (
                        root / "stderr.log").open("wb") as err:
                    proc = subprocess.Popen(
                        [str(root / "zeitop-run"), "vkcube", "--wsi", "wayland",
                         "--width", "320", "--height", "240", "--suppress_popups"],
                        env=env, cwd=root, stdout=out, stderr=err, start_new_session=True,
                    )
                    # A missing GUI intentionally uses the synchronous native
                    # warmup. Do not bind an unserved IPC socket before it completes.
                    deadline = time.monotonic() + 6
                    while time.monotonic() < deadline:
                        self.assertIsNone(proc.poll(), (root / "stderr.log").read_text(errors="replace")[-800:])
                        records = list((root / "runtime/fg-sessions").glob("*.json"))
                        if records and not json.loads(records[0].read_text())["pending"]:
                            break
                        time.sleep(0.05)
                    else:
                        self.fail("First-present bypass did not finish")

                    listener = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                    listener.bind(str(root / "runtime/zeitop.sock"))
                    listener.setblocking(False)

                    def drain(collector=None):
                        while True:
                            try:
                                packet = listener.recv(256)
                            except BlockingIOError:
                                break
                            if collector is None:
                                continue
                            now = time.monotonic()
                            source_event = parse_packet(packet)
                            output_event = parse_output_packet(packet)
                            if source_event:
                                collector[0].record(*source_event, now=now)
                                collector[1]["source"][source_event[0]] += 1
                            elif output_event:
                                collector[0].record_output(*output_event, now=now)
                                collector[1]["output"][output_event[0]] += 1

                    def phase(name, limiter, fg):
                        (root / "runtime/limit.state").write_text("1\n" if limiter else "0\n")
                        switch_live(root, fg)
                        time.sleep(0.55)
                        drain()
                        tracker = TelemetryTracker()
                        counts = {"source": collections.Counter(), "output": collections.Counter()}
                        start = time.monotonic()
                        while time.monotonic() - start < 2.0:
                            self.assertIsNone(proc.poll(), "vkcube exited during " + name)
                            select.select([listener], [], [], 0.04)
                            drain((tracker, counts))
                        drain((tracker, counts))
                        elapsed = time.monotonic() - start
                        result = tracker.snapshot()
                        pid = result["pid"]
                        self.assertIsNotNone(pid, f"No source FPS in {name}")
                        base = counts["source"][pid] / elapsed
                        output = counts["output"][pid] / elapsed
                        self.assertGreater(base, 20, name)
                        self.assertIsNotNone(result["source_fps"], name)
                        self.assertIsNotNone(result["output_fps"], name)
                        self.assertAlmostEqual(base, result["source_fps"], delta=4, msg=name)
                        self.assertAlmostEqual(output, result["output_fps"], delta=5, msg=name)
                        print(f"ZEITOP_FPS_PRODUCTION {name} source={base:.1f} "
                              f"output={output:.1f} source_pid={pid}", flush=True)
                        return base, output

                    off_source, off_output = phase("limiter_on_fg_off", True, False)
                    on_source, on_output = phase("limiter_on_fg_on", True, True)
                    back_source, back_output = phase("fg_off_again", True, False)
                    self.assertTrue(24 < off_source < 36)
                    self.assertTrue(24 < on_source < 36)
                    self.assertTrue(24 < back_source < 36)
                    self.assertTrue(0.8 < off_output / off_source < 1.2)
                    self.assertTrue(1.7 < on_output / on_source < 2.3,
                                    "Generated output was paced or not observed")
                    self.assertTrue(0.8 < back_output / back_source < 1.2)
                    self.assertEqual(source.read_bytes(), original)
                    self.assertIn(b"libzeitop-output.so",
                                  (Path("/proc") / str(proc.pid) / "maps").read_bytes())
            finally:
                if listener:
                    listener.close()
                if proc:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
