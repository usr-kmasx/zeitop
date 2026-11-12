"""Independent FG and limiter flags through the real Steam wrapper.

All state and launch paths are isolated temporary fixtures: no edits to the
user's real settings or external lsfg-vk installation.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = ("DISABLE_LSFGVK", "VK_INSTANCE_LAYERS", "ZEITOP_HOME", "LD_PRELOAD")


class TestIndependentFrameGenerationLaunch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="zeitop_fg_test_", dir=ROOT / "runtime")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copy2(ROOT / "zeitop-run", self.root / "zeitop-run")
        (self.root / "runtime").mkdir()
        (self.root / "runtime/vulkan").symlink_to(ROOT / "runtime/vulkan", target_is_directory=True)
        for name in ("libzeitop-gl.so", "libzeitop-gl32.so"):
            (self.root / "runtime" / name).symlink_to(ROOT / "runtime" / name)

    def run_case(self, limiter, fg, *, inherited=None):
        (self.root / "runtime/limit.state").write_text("1\n" if limiter else "0\n")
        (self.root / "runtime/fg.state").write_text("1\n" if fg else "0\n")
        env = dict(os.environ)
        env.pop("VK_LAYER_PATH", None)
        env.pop("VK_ADD_LAYER_PATH", None)
        env.pop("VK_INSTANCE_LAYERS", None)
        env.pop("VK_LOADER_LAYERS_ENABLE", None)
        env["DISABLE_LSFGVK"] = "0"  # Presence still disables, tests required unset behavior.
        if inherited:
            env.update(inherited)
        command = [str(self.root / "zeitop-run"), sys.executable, "-c",
                   "import json,os;print(json.dumps({k:os.environ.get(k) for k in " +
                   repr(ENV_KEYS) + "}))"]
        return subprocess.run(command, env=env, cwd=self.root,
                              capture_output=True, text=True, timeout=12)

    def test_four_independent_modes(self):
        for limiter in (False, True):
            for fg in (False, True):
                with self.subTest(limiter=limiter, fg=fg):
                    run = self.run_case(limiter, fg)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    values = json.loads(run.stdout.strip().splitlines()[-1])
                    self.assertEqual(values["ZEITOP_HOME"], str(self.root))
                    self.assertEqual(values["DISABLE_LSFGVK"], None if fg else "1")
                    self.assertTrue(values["VK_INSTANCE_LAYERS"].startswith("VK_LAYER_ZEITOP_pacing"))
                    self.assertIn("libzeitop-gl.so", values["LD_PRELOAD"])
                    self.assertEqual((self.root / "runtime/limit.state").read_text().strip(),
                                     "1" if limiter else "0")

    def test_off_when_state_missing_is_safe(self):
        (self.root / "runtime/fg.state").unlink(missing_ok=True)
        (self.root / "runtime/limit.state").write_text("0\n")
        env = dict(os.environ, DISABLE_LSFGVK="0")
        env.pop("VK_INSTANCE_LAYERS", None)
        cp = subprocess.run([str(self.root / "zeitop-run"), sys.executable, "-c",
                             "import os; print(os.environ.get('DISABLE_LSFGVK'))"],
                            cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(cp.stdout.strip(), "1")

    def test_environment_which_forces_external_layer_is_rejected(self):
        for fg in (False, True):
            with self.subTest(fg=fg):
                cp = self.run_case(True, fg, inherited={
                    "VK_INSTANCE_LAYERS": "VK_LAYER_MANGOHUD_overlay:VK_LAYER_LSFGVK_frame_generation"
                })
                self.assertEqual(cp.returncode, 2)
                self.assertIn("preserve ordering", cp.stderr)

    def test_vk_loader_forced_enable_is_rejected(self):
        cp = self.run_case(True, False, inherited={
            "VK_LOADER_LAYERS_ENABLE": "*LSFGVK*"
        })
        self.assertEqual(cp.returncode, 2)
        self.assertIn("independent FG control", cp.stderr)

    def test_real_vulkan_layer_order_when_lsfg_installed(self):
        from fg_config import external_fg_available, discover_config, load_config
        if not shutil.which("vulkaninfo"):
            self.skipTest("vulkaninfo is unavailable")
        if not external_fg_available():
            self.skipTest("External lsfg-vk is not installed with a valid config")
        profile = load_config(discover_config())["profiles"][0]["name"]
        for limiter, fg in ((False, False), (True, False),
                            (False, True), (True, True)):
            with self.subTest(limiter=limiter, fg=fg):
                (self.root / "runtime/limit.state").write_text("1\n" if limiter else "0\n")
                (self.root / "runtime/fg.state").write_text("1\n" if fg else "0\n")
                env = dict(os.environ)
                for key in ("VK_INSTANCE_LAYERS", "VK_LOADER_LAYERS_ENABLE",
                            "VK_LOADER_LAYERS_DISABLE", "DISABLE_LSFGVK"):
                    env.pop(key, None)
                env["VK_LOADER_DEBUG"] = "layer"
                env["LSFGVK_PROFILE"] = profile
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
                self.assertEqual(lsfg in layers, fg)
                if fg:
                    self.assertLess(layers.index(zeitop), layers.index(lsfg))

    def test_preserves_unrelated_vulkan_layers(self):
        cp = self.run_case(False, True, inherited={
            "VK_INSTANCE_LAYERS": "VK_LAYER_TEST_other"
        })
        self.assertEqual(cp.returncode, 0, cp.stderr)
        env = json.loads(cp.stdout.strip().splitlines()[-1])
        self.assertEqual(env["VK_INSTANCE_LAYERS"],
                         "VK_LAYER_ZEITOP_pacing:VK_LAYER_TEST_other")


if __name__ == "__main__":
    unittest.main()
