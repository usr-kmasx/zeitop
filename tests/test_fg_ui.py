"""Frame Generation settings do not touch the V12.11.26 limiter."""
import fcntl
import re
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestFrameGenerationWindow(unittest.TestCase):
    def test_html_has_global_and_profile_fields(self):
        html = (ROOT / "ui/fg-settings.html").read_text()
        for term in (
            'lang="en"', 'FRAME GENERATION', 'LOSSLESS SCALING DLL',
            'LSFG-VK CONFIG FILE', 'PROFILES', 'PROFILE SETTINGS',
            'Profile Name', 'Active In', 'Multiplier', 'Flow Scale',
            'Performance Mode', 'Pacing Mode', 'Override Present Mode',
            'Preserve Swapchain Image Count', 'GLOBAL SETTINGS',
            'Allow FP16', 'Log Level', 'Log File', 'Save Changes',
        ):
            self.assertIn(term, html)

    def test_main_settings_button_opens_frame_generation_window(self):
        js = (ROOT / "ui/main.js").read_text()
        app = (ROOT / "app.py").read_text()
        self.assertIn("post('settings')", js)
        self.assertIn('elif action == "settings":', app)
        self.assertIn('self.open_fg_settings()', app)
        self.assertIn('zeitopSettings', app)

    def test_editor_exposes_profile_management_and_dll_browse(self):
        js = (ROOT / "ui/fg-settings.js").read_text()
        for token in ("add-profile", "duplicate-profile", "remove-profile",
                      "fg_choose_dll", "fg_choose_config", "fg_save", "fg_load",
                      "source_index", "window.zeitopFgResponse"):
            self.assertIn(token, js)
        self.assertNotIn("VK_INSTANCE_LAYERS", js)

    def test_no_unrequested_profile_copy_action_and_clear_live_update_text(self):
        html = (ROOT / "ui/fg-settings.html").read_text()
        js = (ROOT / "ui/fg-settings.js").read_text()
        app = (ROOT / "app.py").read_text()
        for text in ("copy-profile", "Copy for Steam", "profile-command-panel"):
            self.assertNotIn(text, html)
            self.assertNotIn(text, js)
        self.assertNotIn("fg_copy_profile", app)
        self.assertIn("hot-reload", html)
        self.assertIn("hot-reload", js)
        self.assertIn('id="save"', html)

    def test_new_settings_text_is_english_only(self):
        for relative in ("ui/fg-settings.html", "ui/fg-settings.js"):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertFalse(re.search(r"[À-ÖØ-öø-ÿ]", content))
            self.assertNotRegex(content, r"Configurações|Copiar|Desativar|Fechar|Alvo")

    def test_settings_close_and_reopen_in_same_process(self):
        """Regression for settings not opening again until restarting Zeitop."""
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland is unavailable")
        lock = ROOT / "runtime" / "zeitop.lock"
        if lock.is_file():
            with lock.open("rb") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self.skipTest("Main Zeitop window already running")
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        env = dict(os.environ, ZEITOP_FG_REOPEN_TEST="1",
                   PYTHONDONTWRITEBYTECODE="1")
        cp = subprocess.run([str(ROOT / "run.sh")], env=env, cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        self.assertIn("ZEITOP_FG_REOPEN_OK", cp.stdout, cp.stdout + cp.stderr)

    def test_gui_smoke_reads_configuration_without_editing_it(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland is unavailable")
        lock = ROOT / "runtime" / "zeitop.lock"
        if lock.is_file():
            with lock.open("rb") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self.skipTest("Main Zeitop window already running")
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        env = dict(os.environ, ZEITOP_FG_SMOKE_TEST="1", PYTHONDONTWRITEBYTECODE="1")
        cp = subprocess.run([str(ROOT / "run.sh")], env=env, cwd=ROOT,
                            capture_output=True, text=True, timeout=16)
        self.assertEqual(cp.returncode, 0, cp.stdout+cp.stderr)
        self.assertIn("ZEITOP_FG_SMOKE_CONFIG_READY", cp.stdout)
        self.assertIn("ZEITOP_FG_SMOKE_CLOSE_OK", cp.stdout)


if __name__ == "__main__":
    unittest.main()
