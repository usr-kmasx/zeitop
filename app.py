#!/usr/bin/env python3
"""Compact GTK4/WebKitGTK frontend for the Zeitop frame-pacing shim."""
import fcntl
import json
import os
import socket
import sys
import time
from pathlib import Path

from core import TARGET_MS, AverageDisplayCadence, TelemetryTracker, brand_drag_hit, create_layout, decode_message, is_enabled, launch_option, parse_packet, set_enabled

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def main():
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    create_layout(ROOT)
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Gtk, WebKit, GLib, Gdk, Gio, GObject

    class Zeitop(Gtk.Application):
        def __init__(self):
            super().__init__(application_id=None)
            self.tracker = TelemetryTracker()
            self.average_display = AverageDisplayCadence(interval_seconds=1.0)
            self.selected_pid = None
            self.sock = None
            self.lock_handle = None
            self.web = None
            self.smoke = os.environ.get("ZEITOP_SMOKE_TEST") == "1"

        def do_activate(self):
            if self.props.active_window:
                self.props.active_window.present()
                return
            lock = ROOT / "runtime" / "zeitop.lock"
            self.lock_handle = open(lock, "a+b")
            try:
                fcntl.flock(self.lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Zeitop is already running.", file=sys.stderr)
                self.quit()
                return
            path = ROOT / "runtime" / "zeitop.sock"
            if path.exists():
                path.unlink()
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            self.sock.bind(str(path))
            os.chmod(path, 0o600)

            provider = Gtk.CssProvider()
            provider.load_from_string("""
                window.zeitop-window, window.zeitop-window > * {
                    background-color: transparent;
                    background-image: none;
                    box-shadow: none;
                    border: none;
                }
            """)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            self.css_provider = provider
            self.window = Gtk.ApplicationWindow(application=self)
            self.window.add_css_class("zeitop-window")
            self.window.set_title(f"Zeitop {VERSION}")
            self.window.set_default_size(480, 206)
            self.window.set_size_request(480, 206)
            self.window.set_resizable(False)
            self.window.set_decorated(False)
            self.window.connect("destroy", self.on_destroy)

            # Capture the actual hardware press on GTK, while its Wayland
            # input serial is still valid. JS messages arrive too late for
            # compositor-initiated toplevel moves.
            self.drag_gesture = Gtk.GestureClick.new()
            self.drag_gesture.set_button(1)
            self.drag_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.drag_gesture.connect("pressed", self.on_drag_press)
            self.window.add_controller(self.drag_gesture)

            manager = WebKit.UserContentManager()
            manager.register_script_message_handler("zeitop")
            manager.connect("script-message-received::zeitop", self.on_message)
            self.web = WebKit.WebView(user_content_manager=manager)
            background = Gdk.RGBA()
            background.parse("rgba(21, 24, 28, 0)")
            self.web.set_background_color(background)
            self.web.connect("load-changed", self.on_loaded)
            self.web.connect("context-menu", lambda *_: True)
            settings = self.web.get_settings()
            settings.set_enable_developer_extras(False)
            self.window.set_child(self.web)
            self.web.load_uri((ROOT / "ui" / "index.html").as_uri())
            GLib.timeout_add(120, self.poll)
            self.window.present()
            if self.smoke:
                GLib.idle_add(self.smoke_check_drag_ready)

        def smoke_check_drag_ready(self):
            surface = self.window.get_surface()
            ready = (
                isinstance(surface, Gdk.Toplevel)
                and self.drag_gesture.get_button() == 1
                and self.drag_gesture.get_propagation_phase() == Gtk.PropagationPhase.CAPTURE
            )
            print("ZEITOP_SMOKE_DRAG_READY" if ready else "ZEITOP_SMOKE_DRAG_FAIL", flush=True)
            return False

        def on_drag_press(self, gesture, n_press, x, y):
            if not brand_drag_hit(x, y, button=1):
                return
            surface = self.window.get_surface()
            device = gesture.get_device()
            event = gesture.get_last_event(None)
            if not surface or not isinstance(surface, Gdk.Toplevel) or not device or not event:
                return
            surface.begin_move(device, 1, x, y, event.get_time())
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

        def on_destroy(self, *_):
            if self.sock:
                self.sock.close()
                self.sock = None
                path = ROOT / "runtime" / "zeitop.sock"
                if path.exists():
                    path.unlink()
            if self.lock_handle:
                self.lock_handle.close()
                self.lock_handle = None

        def on_loaded(self, web, state):
            if state == WebKit.LoadEvent.FINISHED:
                self.push_state()
                if self.smoke:
                    GLib.timeout_add(300, self.smoke_click_copy)

        def smoke_click_copy(self):
            self.send_js("document.getElementById('copy').click()")
            GLib.timeout_add(450, self.smoke_verify_copy)
            return False

        def smoke_verify_copy(self):
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.read_text_async(None, self.smoke_got_clipboard)
            return False

        def smoke_got_clipboard(self, clipboard, result):
            try:
                text = clipboard.read_text_finish(result)
            except GLib.Error as err:
                if err.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_SUPPORTED):
                    # The compositor may reject a clipboard offer made from
                    # a synthetic JS click lacking a trusted Wayland input serial.
                    print("ZEITOP_SMOKE_COPY_UNVERIFIED_WAYLAND", flush=True)
                    self.send_js("document.getElementById(\'close\').click()")
                else:
                    print("ZEITOP_SMOKE_COPY_FAIL", err, flush=True)
                    self.quit()
                return
            if text != launch_option(ROOT):
                print("ZEITOP_SMOKE_COPY_FAIL", repr(text), flush=True)
                self.quit()
                return
            print("ZEITOP_SMOKE_COPY_OK", flush=True)
            self.send_js("document.getElementById('close').click()")

        def on_message(self, manager, result):
            try:
                action = decode_message(result)
                if action == "toggle":
                    set_enabled(ROOT, not is_enabled(ROOT))
                    self.push_state()
                elif action == "copy":
                    cmd = launch_option(ROOT)
                    clipboard = Gdk.Display.get_default().get_clipboard()
                    value = GObject.Value(GObject.TYPE_STRING)
                    value.set_string(cmd)
                    provider = Gdk.ContentProvider.new_union([
                        Gdk.ContentProvider.new_for_value(value),
                        Gdk.ContentProvider.new_for_bytes(
                            "text/plain;charset=utf-8", GLib.Bytes.new(cmd.encode("utf-8"))
                        ),
                    ])
                    if clipboard.set_content(provider):
                        self.clipboard_provider = provider
                        if self.smoke:
                            print("ZEITOP_SMOKE_COPY_HANDLER_OK", flush=True)
                        self.send_js("window.zeitopNotice('Command copied')")
                    else:
                        self.send_js("window.zeitopNotice('Failed to copy command')")
                elif action == "close":
                    if self.smoke:
                        print("ZEITOP_SMOKE_CLOSE_OK", flush=True)
                    self.window.close()
            except (ValueError, TypeError, AttributeError) as err:
                print(f"Zeitop bridge: {err}", file=sys.stderr)

        def send_js(self, script):
            if self.web:
                self.web.evaluate_javascript(script, -1, None, None, None, None, None)

        def push_state(self):
            selected = self.tracker.snapshot()
            self.selected_pid = selected["pid"]
            payload = {
                "enabled": is_enabled(ROOT),
                "connected": selected["pid"] is not None,
                "real": selected["real"],
                "average": self.average_display.display(selected["pid"], selected["average"]),
                "samples": selected["samples"],
                "target": TARGET_MS,
            }
            self.send_js("window.zeitopUpdate(" + json.dumps(payload, allow_nan=False) + ")")

        def poll(self):
            if not self.sock:
                return False
            changed = False
            for _ in range(256):
                try:
                    packet = self.sock.recv(128)
                except BlockingIOError:
                    break
                sample = parse_packet(packet)
                if not sample:
                    continue
                pid, elapsed = sample
                self.tracker.record(pid, elapsed)
                changed = True
            if changed or self.tracker.snapshot()["pid"] != self.selected_pid:
                self.push_state()
            return True

    app = Zeitop()
    return app.run(sys.argv)

if __name__ == "__main__":
    raise SystemExit(main())
