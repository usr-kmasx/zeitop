"""Zeitop-owned per-launch presentation mode, isolated from canonical lsfg-vk."""
import json
import os
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from core import create_layout
from fg_live import (
    LiveConfigError, launch_session, presentation_mode,
    remember_presentation_mode, render_effective, switch_live, warmup_session,
)
from tests.test_fg_live import SAMPLE

ROOT = Path(__file__).resolve().parents[1]


class TestPresentationMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="zeitop_presentation_", dir=ROOT / "runtime")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        create_layout(self.root)
        self.config = self.root / "canonical.toml"
        self.config.write_text(SAMPLE)
        self.env = {"HOME": str(self.root), "LSFGVK_CONFIG": str(self.config)}

    def test_default_is_noninvasive_and_persists_option_separately(self):
        original = self.config.read_bytes()
        self.assertEqual(presentation_mode(self.root), "default")
        self.assertEqual(render_effective(original, enabled=True), original)
        remember_presentation_mode(self.root, "immediate")
        marker = self.root / "runtime/fg.presentation-mode"
        self.assertEqual(marker.read_text(), "immediate\n")
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
        self.assertEqual(presentation_mode(self.root), "immediate")
        remember_presentation_mode(self.root, "default")
        self.assertEqual(presentation_mode(self.root), "default")
        self.assertEqual(self.config.read_bytes(), original)
        for invalid in ("none", "vsync", "../immediate", "", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(LiveConfigError):
                    remember_presentation_mode(self.root, invalid)
        self.assertEqual(presentation_mode(self.root), "default")

    def test_immediate_rewrites_only_runtime_presentation_flags(self):
        original = self.config.read_bytes()
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                new = render_effective(original, enabled=enabled, presentation_mode="immediate")
                parsed = tomllib.loads(new.decode())
                self.assertEqual([p["multiplier"] for p in parsed["profile"]],
                                 [3, 2] if enabled else [1, 1])
                self.assertEqual([p["override_present_mode"] for p in parsed["profile"]],
                                 [False, False])
                self.assertEqual([p["pacing_mode"] for p in parsed["profile"]],
                                 ["vsync", "vsync"])
                self.assertIn("custom_field = 18", new.decode())
                self.assertIn('custom_global = "keep me"', new.decode())
        self.assertEqual(self.config.read_bytes(), original)

    @patch("fg_live.fg_config.external_fg_available", return_value=True)
    def test_sessions_keep_launch_time_mode_during_warmup_and_toggle(self, _available):
        original = self.config.read_bytes()
        remember_presentation_mode(self.root, "immediate")
        first, _, _ = launch_session(self.root, pid=os.getpid(), env=self.env)
        first_meta = json.loads(first.with_suffix(".json").read_text())
        self.assertEqual(first_meta["presentation_mode"], "immediate")
        self.assertFalse(tomllib.loads(first.read_text())["profile"][0]["override_present_mode"])
        remember_presentation_mode(self.root, "default")
        second, _, _ = launch_session(self.root, pid=os.getpid(), env=self.env)
        second_meta = json.loads(second.with_suffix(".json").read_text())
        self.assertEqual(second_meta["presentation_mode"], "default")
        self.assertNotIn("override_present_mode", tomllib.loads(second.read_text())["profile"][0])
        warmup_session(self.root, first.stem)
        warmup_session(self.root, second.stem)
        switch_live(self.root, True)
        immediate = tomllib.loads(first.read_text())["profile"]
        normal = tomllib.loads(second.read_text())["profile"]
        self.assertFalse(immediate[0]["override_present_mode"])
        self.assertNotIn("override_present_mode", normal[0])
        self.assertEqual(immediate[0]["multiplier"], 3)
        self.assertEqual(normal[0]["multiplier"], 3)
        switch_live(self.root, False)
        self.assertFalse(tomllib.loads(first.read_text())["profile"][0]["override_present_mode"])
        self.assertNotIn("override_present_mode", tomllib.loads(second.read_text())["profile"][0])
        self.assertEqual(self.config.read_bytes(), original)

    def test_invalid_presentation_mode_does_not_render_config(self):
        with self.assertRaises(LiveConfigError):
            render_effective(SAMPLE.encode(), enabled=True, presentation_mode="none")
        self.assertEqual(self.config.read_text(), SAMPLE)
