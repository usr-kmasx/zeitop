"""Real launcher: lsfg-vk remains loaded, multiplier hot-reloads independently.

Every test operates on a temporary config and runtime with isolated copies
of the wrapper and symlinks to code/build artifacts. Never edits the user's
real lsfg-vk conf.toml, runtime flags or Steam game settings.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path

from fg_config import discover_config, external_fg_available, load_config
from fg_live import remember_config, switch_live

ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = ("DISABLE_LSFGVK", "VK_INSTANCE_LAYERS", "ZEITOP_HOME",
            "LD_PRELOAD", "LSFGVK_CONFIG")

CONFIG = '''version = 2
[global]
allow_fp16 = true

[[profile]]
name = "Test vkcube"
active_in = ["vkcube", "vkcubepp"]
multiplier = 3
flow_scale = 0.85
performance_mode = true
pacing_mode = "vsync"
override_present_mode = true

[[profile]]
name = "Test game"
active_in = "Game.exe"
multiplier = 2
flow_scale = 1.0
performance_mode = false
pacing_mode = "vsync"
'''


class TestIndependentFrameGenerationLaunch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="zeitop_fg_test_", dir=ROOT / "runtime")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("zeitop-run", "fg_live.py", "fg_config.py", "core.py"):
            shutil.copy2(ROOT / name, self.root / name)
        (self.root / "runtime").mkdir()
        (self.root / "runtime/vulkan").symlink_to(ROOT / "runtime/vulkan", target_is_directory=True)
        for name in ("libzeitop-gl.so", "libzeitop-gl32.so"):
            (self.root / "runtime" / name).symlink_to(ROOT / "runtime" / name)
        self.config = self.root / "source.toml"
        self.config.write_text(CONFIG)
        self.environment = dict(os.environ)
        for key in ("VK_LAYER_PATH", "VK_ADD_LAYER_PATH", "VK_INSTANCE_LAYERS",
                    "VK_LOADER_LAYERS_ENABLE", "VK_LOADER_LAYERS_DISABLE"):
            self.environment.pop(key, None)
        self.environment["LSFGVK_CONFIG"] = str(self.config)
        self.environment["DISABLE_LSFGVK"] = "0"  # Must be removed even when OFF.

    def run_case(self, limiter, fg, *, inherited=None):
        (self.root / "runtime/limit.state").write_text("1\n" if limiter else "0\n")
        (self.root / "runtime/fg.state").write_text("1\n" if fg else "0\n")
        env = dict(self.environment)
        if inherited:
            env.update(inherited)
        code = ("import json,os;print(json.dumps({k:os.environ.get(k) for k in "
                + repr(ENV_KEYS) + "}))")
        command = [str(self.root / "zeitop-run"), sys.executable, "-c", code]
        return subprocess.run(command, env=env, cwd=self.root,
                              capture_output=True, text=True, timeout=12)

    def test_four_independent_modes_use_live_bypass(self):
        source = self.config.read_bytes()
        for limiter in (False, True):
            for fg in (False, True):
                with self.subTest(limiter=limiter, fg=fg):
                    run = self.run_case(limiter, fg)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    env = json.loads(run.stdout.strip().splitlines()[-1])
                    self.assertEqual(env["ZEITOP_HOME"], str(self.root))
                    self.assertIsNone(env["DISABLE_LSFGVK"])
                    self.assertTrue(env["VK_INSTANCE_LAYERS"].startswith("VK_LAYER_ZEITOP_pacing"))
                    self.assertIn("libzeitop-gl.so", env["LD_PRELOAD"])
                    live = Path(env["LSFGVK_CONFIG"])
                    self.assertEqual(live, self.root / "runtime/fg-live.conf.toml")
                    got = tomllib.loads(live.read_text())["profile"]
                    self.assertEqual([p["multiplier"] for p in got], [3, 2] if fg else [1, 1])
                    self.assertEqual((self.root / "runtime/limit.state").read_text().strip(),
                                     "1" if limiter else "0")
                    self.assertEqual(self.config.read_bytes(), source)

    def test_off_when_state_missing_is_bypass_not_layer_disable(self):
        (self.root / "runtime/fg.state").unlink(missing_ok=True)
        (self.root / "runtime/limit.state").write_text("0\n")
        cp = subprocess.run([str(self.root / "zeitop-run"), sys.executable, "-c",
                             "import os; print(os.environ.get('DISABLE_LSFGVK')); "
                             "print(os.environ['LSFGVK_CONFIG'])"],
                            cwd=self.root, env=self.environment, capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        lines = cp.stdout.strip().splitlines()
        self.assertEqual(lines[0], "None")
        self.assertEqual(tomllib.loads(Path(lines[1]).read_text())["profile"][0]["multiplier"], 1)

    def test_bad_config_fails_safely_without_blocking_limiter(self):
        self.config.unlink()
        cp = self.run_case(True, True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        env = json.loads(cp.stdout.strip().splitlines()[-1])
        self.assertEqual(env["DISABLE_LSFGVK"], "1")
        self.assertEqual(env["VK_INSTANCE_LAYERS"], "VK_LAYER_ZEITOP_pacing")
        self.assertNotIn("fg-live.conf.toml", str(env["LSFGVK_CONFIG"]))

    def test_force_external_layer_is_rejected_even_when_bypassed(self):
        for fg in (False, True):
            with self.subTest(fg=fg):
                cp = self.run_case(True, fg, inherited={
                    "VK_INSTANCE_LAYERS": "VK_LAYER_MANGOHUD_overlay:VK_LAYER_LSFGVK_frame_generation"
                })
                self.assertEqual(cp.returncode, 2)
                self.assertIn("preserve ordering", cp.stderr)

    def test_vk_loader_forced_enable_is_rejected(self):
        cp = self.run_case(True, False, inherited={"VK_LOADER_LAYERS_ENABLE": "*LSFGVK*"})
        self.assertEqual(cp.returncode, 2)
        self.assertIn("independent FG control", cp.stderr)

    def test_preserves_unrelated_vulkan_layers(self):
        cp = self.run_case(False, True, inherited={
            "VK_INSTANCE_LAYERS": "VK_LAYER_TEST_other"
        })
        self.assertEqual(cp.returncode, 0, cp.stderr)
        env = json.loads(cp.stdout.strip().splitlines()[-1])
        self.assertEqual(env["VK_INSTANCE_LAYERS"],
                         "VK_LAYER_ZEITOP_pacing:VK_LAYER_TEST_other")

    def test_real_vulkan_layer_order_in_off_and_on(self):
        if not shutil.which("vulkaninfo"):
            self.skipTest("vulkaninfo is unavailable")
        if not external_fg_available():
            self.skipTest("External lsfg-vk unavailable")
        self.config.write_bytes(discover_config().read_bytes())
        selected_profile = load_config(self.config)["profiles"][0]["name"]
        for limiter, fg in ((False, False), (True, False),
                            (False, True), (True, True)):
            with self.subTest(limiter=limiter, fg=fg):
                (self.root / "runtime/limit.state").write_text("1\n" if limiter else "0\n")
                (self.root / "runtime/fg.state").write_text("1\n" if fg else "0\n")
                env = dict(self.environment)
                env["VK_LOADER_DEBUG"] = "layer"
                env["LSFGVK_PROFILE"] = selected_profile
                run = subprocess.run([str(self.root / "zeitop-run"),
                                      "vulkaninfo", "--summary"],
                                     env=env, capture_output=True, text=True, timeout=12)
                self.assertEqual(run.returncode, 0, run.stderr[-900:])
                prefix = 'Insert instance layer "'
                layers = [
                    line.split(prefix, 1)[1].split('"', 1)[0]
                    for line in run.stderr.splitlines() if prefix in line
                ]
                zeitop = "VK_LAYER_ZEITOP_pacing"
                lsfg = "VK_LAYER_LSFGVK_frame_generation"
                self.assertIn(zeitop, layers)
                self.assertIn(lsfg, layers)
                self.assertLess(layers.index(zeitop), layers.index(lsfg))
                live = self.root / "runtime/fg-live.conf.toml"
                got = tomllib.loads(live.read_text())["profile"]
                if not fg:
                    self.assertTrue(all(p["multiplier"] == 1 for p in got))

    def test_real_vkcube_hot_toggle_on_one_process(self):
        if not os.environ.get("WAYLAND_DISPLAY") or not shutil.which("vkcube"):
            self.skipTest("A Wayland Vulkan session is required.")
        if not external_fg_available():
            self.skipTest("External lsfg-vk unavailable")
        # Use a copy of the user's already valid config and an isolated log.
        original = discover_config().read_text()
        log = self.root / "fg-vkcube.log"
        original = re.sub(
            r'(?m)^[ \t]*log_file[ \t]*=.*$',
            'log_file = ' + json.dumps(str(log)),
            original
        )
        self.config.write_text(original)
        remember_config(self.root, self.config)
        (self.root / "runtime/limit.state").write_text("1\n")
        (self.root / "runtime/fg.state").write_text("0\n")
        env = dict(self.environment)
        env["LSFGVK_PROFILE"] = load_config(self.config)["profiles"][0]["name"]
        env["VK_LOADER_DEBUG"] = "layer"
        with (self.root / "vkcube.stdout").open("wb") as stdout, (
                self.root / "vkcube.stderr").open("wb") as stderr:
            proc = subprocess.Popen(
                [str(self.root / "zeitop-run"), "vkcube",
                 "--wsi", "wayland", "--width", "320", "--height", "240"],
                env=env, stdout=stdout, stderr=stderr,
                cwd=self.root, start_new_session=True
            )
            try:
                time.sleep(3.5)
                self.assertIsNone(proc.poll(), "vkcube exited before toggle")
                from core import is_fg_enabled
                self.assertFalse(is_fg_enabled(self.root))
                switch_live(self.root, True)
                time.sleep(3.5)
                self.assertIsNone(proc.poll(), "vkcube exited after FG ON")
                switch_live(self.root, False)
                time.sleep(3.5)
                self.assertIsNone(proc.poll(), "vkcube exited after FG OFF")
                self.assertFalse(is_fg_enabled(self.root))
                # Both modules remain mapped even after OFF.
                maps = (Path("/proc") / str(proc.pid) / "maps").read_text(errors="replace")
                self.assertIn("libzeitop-vulkan", maps)
                self.assertIn("liblsfg-vk-layer", maps)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
        events = log.read_text(errors="replace") if log.exists() else ""
        self.assertIn("(Disabled)", events)
        selected = load_config(self.config)["profiles"][0]["multiplier"]
        self.assertIn(f"Multiplier: {selected}", events)
        self.assertGreaterEqual(events.count("Configuration file has changed"), 2)
        self.assertFalse(any("[ERROR]" in line for line in events.splitlines()))


if __name__ == "__main__":
    unittest.main()
