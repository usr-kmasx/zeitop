"""Regression tests for the WebKitGTK 6 script-message protocol."""
import unittest
from core import decode_message

class TestBridge(unittest.TestCase):
    def test_accepts_javascriptcore_value_directly(self):
        import gi
        gi.require_version("JavaScriptCore", "6.0")
        from gi.repository import JavaScriptCore
        context = JavaScriptCore.Context()
        val = JavaScriptCore.Value.new_string(context, '{"action":"copy"}')
        self.assertEqual(decode_message(val), "copy")

    def test_close_action(self):
        import gi
        gi.require_version("JavaScriptCore", "6.0")
        from gi.repository import JavaScriptCore
        context = JavaScriptCore.Context()
        val = JavaScriptCore.Value.new_string(context, '{"action":"close"}')
        self.assertEqual(decode_message(val), "close")

    def test_invalid_payloads_do_not_trigger_actions(self):
        import gi
        gi.require_version("JavaScriptCore", "6.0")
        from gi.repository import JavaScriptCore
        context = JavaScriptCore.Context()
        for raw in ('not-json', '{}', '{"action":"delete"}', '[]'):
            with self.subTest(raw=raw):
                val = JavaScriptCore.Value.new_string(context, raw)
                self.assertIsNone(decode_message(val))
