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
from fg_live import remember_config, remember_profile, switch_live

ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = ("DISABLE_LSFGVK", "VK_INSTANCE_LAYERS", "ZEITOP_HOME",
            "LD_PRELOAD", "LSFGVK_CONFIG", "LSFGVK_PROFILE",
            "ZEITOP_FG_WARMUP_TOKEN")

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
                    self.assertTrue(env["VK_INSTANCE_LAYERS"].startswith(
                        "VK_LAYER_ZEITOP_pacing:VK_LAYER_LSFGVK_frame_generation"
                    ))
                    self.assertIn("libzeitop-gl.so", env["LD_PRELOAD"])
                    live = Path(env["LSFGVK_CONFIG"])
                    self.assertEqual(live.parent, self.root / "runtime/fg-sessions")
                    self.assertTrue(live.is_file())
                    meta = json.loads(live.with_suffix(".json").read_text())
                    self.assertTrue(meta["pending"])
                    self.assertEqual(env["ZEITOP_FG_WARMUP_TOKEN"],
                                     live.stem)
                    got = tomllib.loads(live.read_text())["profile"]
                    # OFF starts at the real multiplier but the first present
                    # must block until the per-process bypass has been written.
                    self.assertEqual([p["multiplier"] for p in got], [3, 2])
                    self.assertEqual((self.root / "runtime/limit.state").read_text().strip(),
                                     "1" if limiter else "0")
                    self.assertEqual(self.config.read_bytes(), source)

    def test_saved_selection_is_propagated_to_child_and_preserves_canonical(self):
        source = self.config.read_bytes()
        remember_profile(self.root, self.config, "Test game")
        cp = self.run_case(False, True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        environment = json.loads(cp.stdout.strip().splitlines()[-1])
        self.assertEqual(environment["LSFGVK_PROFILE"], "Test game")
        self.assertEqual(self.config.read_bytes(), source)
        self.assertEqual(
            json.loads((self.root / "runtime/fg.active-launch.json").read_text())["name"],
            "Test game"
        )
        remember_profile(self.root, self.config, "Test vkcube")
        cp = self.run_case(False, True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(json.loads(cp.stdout.strip().splitlines()[-1])["LSFGVK_PROFILE"],
                         "Test vkcube")

    def test_explicit_caller_profile_override_still_has_priority(self):
        remember_profile(self.root, self.config, "Test game")
        cp = self.run_case(False, True, inherited={"LSFGVK_PROFILE": "Test vkcube"})
        self.assertEqual(cp.returncode, 0, cp.stderr)
        env = json.loads(cp.stdout.strip().splitlines()[-1])
        self.assertEqual(env["LSFGVK_PROFILE"], "Test vkcube")

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
        self.assertEqual(tomllib.loads(Path(lines[1]).read_text())["profile"][0]["multiplier"], 3)
        self.assertTrue(json.loads(Path(lines[1]).with_suffix(".json").read_text())["pending"])

    def test_bad_config_fails_safely_without_blocking_limiter(self):
        self.config.unlink()
        cp = self.run_case(True, True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        env = json.loads(cp.stdout.strip().splitlines()[-1])
        self.assertEqual(env["DISABLE_LSFGVK"], "1")
        self.assertEqual(env["VK_INSTANCE_LAYERS"], "VK_LAYER_ZEITOP_pacing")
        self.assertNotIn("fg-live.conf.toml", str(env["LSFGVK_CONFIG"]))

    def test_inherited_lsfg_layer_is_normalized_without_duplicates(self):
        for fg in (False, True):
            with self.subTest(fg=fg):
                cp = self.run_case(True, fg, inherited={
                    "VK_INSTANCE_LAYERS": "VK_LAYER_MANGOHUD_overlay:VK_LAYER_LSFGVK_frame_generation"
                })
                self.assertEqual(cp.returncode, 0, cp.stderr)
                env = json.loads(cp.stdout.strip().splitlines()[-1])
                self.assertEqual(env["VK_INSTANCE_LAYERS"],
                    "VK_LAYER_ZEITOP_pacing:VK_LAYER_LSFGVK_frame_generation:VK_LAYER_MANGOHUD_overlay")

    def test_vk_loader_forced_enable_is_rejected(self):
        cp = self.run_case(True, False, inherited={"VK_LOADER_LAYERS_ENABLE": "*LSFGVK*"})
        self.assertEqual(cp.returncode, 2)
        self.assertIn("manages the layer order", cp.stderr)

    def test_preserves_unrelated_vulkan_layers(self):
        cp = self.run_case(False, True, inherited={
            "VK_INSTANCE_LAYERS": "VK_LAYER_TEST_other"
        })
        self.assertEqual(cp.returncode, 0, cp.stderr)
        env = json.loads(cp.stdout.strip().splitlines()[-1])
        self.assertEqual(env["VK_INSTANCE_LAYERS"],
                         "VK_LAYER_ZEITOP_pacing:VK_LAYER_LSFGVK_frame_generation:VK_LAYER_TEST_other")

    def test_real_vkcube_profile_selected_without_active_in_match(self):
        """Saved next-launch profile must work without vkcube in Active In."""
        if not os.environ.get("WAYLAND_DISPLAY") or not shutil.which("vkcube"):
            self.skipTest("Wayland vkcube session unavailable")
        if not external_fg_available():
            self.skipTest("External lsfg-vk installation unavailable")
        original = discover_config().read_text(encoding="utf-8")
        log = self.root / "override-profile-vkcube.log"
        original = re.sub(
            r'(?m)^[ \\t]*log_file[ \\t]*=.*$',
            'log_file = ' + json.dumps(str(log)),
            original
        )
        self.config.write_text(original)
        profiles = load_config(self.config)["profiles"]
        others = [p for p in profiles if "vkcube" not in (
            p["active_in"] if isinstance(p["active_in"], list) else
            [p["active_in"]]
        )]
        if not others:
            self.skipTest("No profile with a non-vkcube Active In")
        selected = others[0]["name"]
        remember_profile(self.root, self.config, selected)
        (self.root / "runtime/limit.state").write_text("0\n")
        (self.root / "runtime/fg.state").write_text("1\n")
        env = dict(self.environment)
        env.pop("LSFGVK_PROFILE", None)
        with (self.root / "override-vkcube.stdout").open("wb") as out, (
             self.root / "override-vkcube.stderr").open("wb") as err:
            proc = subprocess.Popen(
                [str(self.root / "zeitop-run"), "vkcube",
                 "--wsi", "wayland", "--width", "320", "--height", "240"],
                env=env, stdout=out, stderr=err, cwd=self.root, start_new_session=True
            )
            try:
                time.sleep(3.2)
                self.assertIsNone(proc.poll())
                mapping = (Path("/proc") / str(proc.pid) / "maps").read_text(errors="replace")
                self.assertIn("liblsfg-vk-layer", mapping)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
        output = log.read_text(errors="replace") if log.exists() else ""
        self.assertIn(f"Using profile with name '{selected}'", output)
        self.assertIn("identified via environment", output)
        self.assertNotIn("[ERROR]", output)

    def test_real_vkcube_selected_profile_hot_fields_without_restart(self):
        """Vulkan and external layer: selected A -> B -> A on one process."""
        if not os.environ.get("WAYLAND_DISPLAY") or not shutil.which("vkcube"):
            self.skipTest("Wayland vkcube session unavailable")
        if not external_fg_available():
            self.skipTest("External lsfg-vk installation unavailable")
        source = discover_config().read_text(encoding="utf-8")
        log = self.root / "profile-change-vkcube.log"
        source = re.sub(
            r'(?m)^[ \\t]*log_file[ \\t]*=.*$',
            'log_file = ' + json.dumps(str(log)),
            source
        )
        self.config.write_text(source)
        original = self.config.read_bytes()
        profiles = load_config(self.config)["profiles"]
        if len(profiles) < 2:
            self.skipTest("Need two installed profiles")
        first, second = profiles[:2]
        if first["multiplier"] == second["multiplier"]:
            self.skipTest("Need distinguishable multiplier values")
        remember_profile(self.root, self.config, first["name"])
        (self.root / "runtime/limit.state").write_text("1\n")
        (self.root / "runtime/fg.state").write_text("1\n")
        env = dict(self.environment)
        env.pop("LSFGVK_PROFILE", None)
        with (self.root / "selected-vkcube.out").open("wb") as stdout, (
                self.root / "selected-vkcube.err").open("wb") as stderr:
            proc = subprocess.Popen(
                [str(self.root / "zeitop-run"), "vkcube",
                 "--wsi", "wayland", "--width", "320", "--height", "240"],
                env=env, stdout=stdout, stderr=stderr,
                cwd=self.root, start_new_session=True
            )
            try:
                time.sleep(3.0)
                self.assertIsNone(proc.poll(), "vkcube exited before switching")
                environ = dict(
                    part.split("=", 1)
                    for part in (Path("/proc") / str(proc.pid) / "environ").read_bytes()
                        .decode(errors="replace").strip("\x00").split("\x00")
                    if "=" in part
                )
                self.assertEqual(environ.get("LSFGVK_PROFILE"), first["name"])
                self.assertEqual(environ.get("DISABLE_LSFGVK"), None)
                remember_profile(self.root, self.config, second["name"])
                from fg_live import prepare_live
                prepare_live(self.root, enabled=True, env=self.environment)
                time.sleep(3.0)
                self.assertIsNone(proc.poll(), "vkcube exited when hot values changed")
                expected = tomllib.loads(
                    (self.root / "runtime/fg-live.conf.toml").read_text()
                )["profile"][0]
                self.assertEqual(expected["multiplier"], second["multiplier"])
                self.assertEqual(expected["flow_scale"], second["flow_scale"])
                self.assertEqual(expected["performance_mode"], second["performance_mode"])
                self.assertEqual(expected["active_in"], first["active_in"])
                remember_profile(self.root, self.config, first["name"])
                prepare_live(self.root, enabled=True, env=self.environment)
                time.sleep(3.0)
                self.assertIsNone(proc.poll(), "vkcube exited when restoring profile")
                mapped = (Path("/proc") / str(proc.pid) / "maps").read_text(errors="replace")
                self.assertIn("libzeitop-vulkan", mapped)
                self.assertIn("liblsfg-vk-layer", mapped)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
        events = log.read_text(errors="replace") if log.exists() else ""
        self.assertIn(f"Multiplier: {first['multiplier']}", events)
        self.assertIn(f"Multiplier: {second['multiplier']}", events)
        self.assertGreaterEqual(events.count("Configuration file has changed"), 2)
        self.assertFalse(any("[ERROR]" in x for x in events.splitlines()))
        self.assertEqual(self.config.read_bytes(), original)

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
                # Vulkan Loader logs the insertion order from driver toward
                # app; the application-first list in the environment is
                # the opposite (verified using caller-address tracing).
                self.assertGreater(layers.index(zeitop), layers.index(lsfg))
                sessions = list((self.root / "runtime/fg-sessions").glob("*.json"))
                self.assertTrue(sessions)
                recent = max(sessions, key=lambda x: x.stat().st_mtime_ns)
                got = tomllib.loads(recent.with_suffix(".toml").read_text())["profile"]
                self.assertEqual(got[0]["multiplier"], load_config(self.config)["profiles"][0]["multiplier"])
                self.assertTrue(json.loads(recent.read_text())["pending"])

    def test_real_vkcube_first_present_handshake_and_live_output(self):
        """Check actual OUTPUT downstream of lsfg-vk, not a game's overlay."""
        if not os.environ.get("WAYLAND_DISPLAY") or not shutil.which("vkcube"):
            self.skipTest("Wayland / vkcube unavailable")
        if not shutil.which("gcc"):
            self.skipTest("C compiler unavailable")
        if not external_fg_available():
            self.skipTest("External lsfg-vk installation unavailable")
        config = discover_config().read_text(encoding="utf-8")
        log = self.root / "handshake.log"
        config = re.sub(
            r'(?m)^[ \\t]*log_file[ \\t]*=.*$',
            'log_file = ' + json.dumps(str(log)), config
        )
        self.config.write_text(config)
        original = self.config.read_bytes()
        profiles = load_config(self.config)["profiles"]
        chosen = next((p for p in profiles if p["multiplier"] == 2), None)
        if chosen is None:
            self.skipTest("No 2x lsfg-vk profile available")
        remember_config(self.root, self.config)
        remember_profile(self.root, self.config, chosen["name"])
        (self.root / "runtime/limit.state").write_text("1\n")
        (self.root / "runtime/fg.state").write_text("0\n")

        # Probe is a separate, test-only Vulkan layer placed after lsfg-vk.
        # The normal Zeitop binary never includes ZEITOP_PRESENT_PROBE.
        probe_dir = self.root / "probe"
        probe_dir.mkdir()
        probe = probe_dir / "libpresent-probe.so"
        build = subprocess.run([
            "gcc", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-fPIC",
            "-shared", "-Wl,-Bsymbolic-functions",
            "-DZEITOP_PACING_ONLY", "-DZEITOP_PRESENT_PROBE",
            "-I" + str(ROOT / "vendor/vulkan"),
            "-o", str(probe), str(ROOT / "vulkan_layer.c"),
            str(ROOT / "limiter.c"), "-pthread", "-ldl"
        ], capture_output=True, text=True, timeout=20)
        self.assertEqual(build.returncode, 0, build.stderr)
        (probe_dir / "VkLayer_Probe.json").write_text(json.dumps({
            "file_format_version": "1.2.1",
            "layer": {
                "name": "VK_LAYER_ZEITOP_present_probe", "type": "GLOBAL",
                "api_version": "1.4.0", "library_path": "./libpresent-probe.so",
                "library_arch": "64", "implementation_version": "1",
                "description": "Zeitop test-only downstream present counter"
            }
        }))
        output = self.root / "downstream.presents"
        env = dict(self.environment)
        env["LSFGVK_PROFILE"] = chosen["name"]
        env["VK_ADD_LAYER_PATH"] = str(probe_dir)
        env["VK_INSTANCE_LAYERS"] = "VK_LAYER_ZEITOP_present_probe"
        env["ZEITOP_PROBE_OUTPUT"] = str(output)

        def count():
            return output.stat().st_size if output.is_file() else 0

        with (self.root / "handshake.stdout").open("wb") as out, (
                self.root / "handshake.stderr").open("wb") as err:
            proc = subprocess.Popen(
                [str(self.root / "zeitop-run"), "vkcube",
                 "--wsi", "wayland", "--width", "320", "--height", "240",
                 "--suppress_popups"],
                env=env, stdout=out, stderr=err,
                cwd=self.root, start_new_session=True
            )
            try:
                time.sleep(2)
                first = count()
                self.assertIsNone(proc.poll())
                sessions = list((self.root / "runtime/fg-sessions").glob("*.json"))
                self.assertEqual(len(sessions), 1)
                session = json.loads(sessions[0].read_text())
                self.assertFalse(session["pending"])
                matching_index = next(
                    i for i,p in enumerate(profiles) if p["name"] == chosen["name"]
                )
                self.assertEqual(tomllib.loads(
                    sessions[0].with_suffix(".toml").read_text()
                )["profile"][matching_index]["multiplier"], 1)
                time.sleep(2)
                off_delta = count() - first
                switch_live(self.root, True)
                time.sleep(2)
                on_delta = count() - first - off_delta
                switch_live(self.root, False)
                time.sleep(2)
                final_delta = count() - first - off_delta - on_delta
                self.assertIsNone(proc.poll())
                # Pacing at ~30 base FPS. Probe sees 1x during bypass,
                # 2x after the live enable, and 1x after disable.
                self.assertGreater(off_delta, 40)
                self.assertLess(off_delta, 85)
                self.assertGreater(on_delta, 90,
                    "Hot-reload failed to produce 2x output frames")
                self.assertLess(on_delta, 150)
                self.assertGreater(final_delta, 40)
                self.assertLess(final_delta, 85)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=6)
        events = log.read_text(errors="replace") if log.exists() else ""
        self.assertIn("(Disabled)", events)
        self.assertGreaterEqual(
            events.count(f"Multiplier: {chosen['multiplier']}"), 2
        )
        self.assertNotIn("[ERROR]", events)
        self.assertEqual(self.config.read_bytes(), original)

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
