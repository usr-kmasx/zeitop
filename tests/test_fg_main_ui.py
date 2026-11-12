"""Independent Frame Generation icon and backend state wiring."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestFgMainUi(unittest.TestCase):
    def test_fg_icon_is_immediately_right_of_limiter(self):
        html = (ROOT / "ui/index.html").read_text(encoding="utf-8")
        self.assertIn('id="fg-toggle"', html)
        self.assertTrue(html.index('id="toggle"') <
                        html.index('id="fg-toggle"') <
                        html.index('id="copy"'))
        self.assertIn('aria-label="Enable lsfg-vk"', html)
        self.assertIn('aria-pressed="false"', html)

    def test_independent_dom_toggles_and_response_state(self):
        js = (ROOT / "ui/main.js").read_text(encoding="utf-8")
        self.assertIn("power.addEventListener('click', () => post('toggle'))", js)
        self.assertIn("fgPower.addEventListener('click', () => post('toggle_fg'))", js)
        self.assertIn("fgPower.classList.toggle('active', !!state.fgEnabled)", js)
        self.assertIn("fgPower.setAttribute('aria-pressed'", js)
        self.assertIn("state.fgAvailable", js)

    def test_backend_keeps_limiter_toggle_independent(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        core = (ROOT / "core.py").read_text(encoding="utf-8")
        self.assertIn('elif action == "toggle_fg":', app)
        self.assertIn("set_fg_enabled(ROOT, requested)", app)
        self.assertIn("if requested and not fg_config.external_fg_available()", app)
        self.assertIn('"fgEnabled": is_fg_enabled(ROOT)', app)
        self.assertIn('"fgAvailable": fg_config.external_fg_available()', app)
        self.assertIn('{"toggle", "toggle_fg", "copy", "close", "settings"}', core)
        # The production limiter cannot be modified as part of this feature.
        self.assertIn('if action == "toggle":', app)
        self.assertIn('set_enabled(ROOT, not is_enabled(ROOT))', app)


if __name__ == "__main__":
    unittest.main()
