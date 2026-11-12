#!/usr/bin/env python3
"""Compact GTK4/WebKitGTK frontend for the Zeitop frame-pacing shim."""
import fcntl
import json
import os
import socket
import sys
import time
from pathlib import Path

import fg_config

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
            self.fg_smoke = os.environ.get("ZEITOP_FG_SMOKE_TEST") == "1"
            self.fg_reopen_smoke = os.environ.get("ZEITOP_FG_REOPEN_TEST") == "1"
            self.fg_ready_count = 0
            self.fg_destroy_count = 0
            self.fg_window = None
            self.fg_web = None
            self.fg_config_path = None
            self.fg_revision = None

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
            if self.fg_smoke:
                GLib.timeout_add(350, self._fg_smoke_open)
                GLib.timeout_add(3000, self._fg_smoke_finish)
            if self.fg_reopen_smoke:
                GLib.timeout_add(400, self._fg_reopen_first)
                GLib.timeout_add(1650, self._fg_reopen_close)
                GLib.timeout_add(2550, self._fg_reopen_second)
                GLib.timeout_add(4000, self._fg_reopen_finish)

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
            if self.fg_window:
                self.fg_window.close()
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
                elif action == "settings":
                    self.open_fg_settings()
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

        def _fg_reopen_first(self):
            self.send_js("document.getElementById('settings').click()")
            return False

        def _fg_reopen_close(self):
            if self.fg_web:
                self.fg_web.evaluate_javascript(
                    "document.getElementById('fg-close').click()",
                    -1, None, None, None, None, None
                )
            return False

        def _fg_reopen_second(self):
            self.send_js("document.getElementById('settings').click()")
            return False

        def _fg_reopen_finish(self):
            visible = bool(self.fg_window and self.fg_window.is_visible())
            print(
                "ZEITOP_FG_REOPEN_DIAGNOSTIC "
                f"config_ready={self.fg_ready_count} "
                f"destroyed={self.fg_destroy_count} "
                f"visible={visible}",
                flush=True,
            )
            if self.fg_ready_count >= 2 and self.fg_destroy_count >= 1 and visible:
                print("ZEITOP_FG_REOPEN_OK", flush=True)
            else:
                print("ZEITOP_FG_REOPEN_FAIL", flush=True)
            if self.fg_window:
                self.fg_window.close()
            if self.window:
                self.window.close()
            return False

        def _fg_smoke_open(self):
            self.open_fg_settings()
            return False

        def _fg_smoke_finish(self):
            if self.fg_window:
                self.fg_window.close()
            if self.window:
                self.window.close()
            print("ZEITOP_FG_SMOKE_CLOSE_OK", flush=True)
            return False

        def open_fg_settings(self):
            if self.fg_window:
                self.fg_window.present()
                return
            window = Gtk.Window()
            window.set_title(f"Zeitop {VERSION} - Frame Generation Settings")
            window.set_transient_for(self.window)
            window.set_modal(False)
            window.set_resizable(False)
            window.set_decorated(False)
            window.set_default_size(840, 618)
            window.set_size_request(840, 618)
            window.add_css_class("zeitop-fg-window")
            self.fg_drag = Gtk.GestureClick.new()
            self.fg_drag.set_button(1)
            self.fg_drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.fg_drag.connect("pressed", self.on_fg_drag_press)
            window.add_controller(self.fg_drag)
            provider = Gtk.CssProvider()
            provider.load_from_string("""
                window.zeitop-fg-window, window.zeitop-fg-window > * {
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
            manager = WebKit.UserContentManager()
            manager.register_script_message_handler("zeitopSettings")
            manager.connect("script-message-received::zeitopSettings",
                            self.on_fg_message)
            web = WebKit.WebView(user_content_manager=manager)
            bg = Gdk.RGBA()
            bg.parse("rgba(21, 24, 28, 0)")
            web.set_background_color(bg)
            web.connect("context-menu", lambda *_: True)
            web.get_settings().set_enable_developer_extras(False)
            self.fg_window = window
            self.fg_web = web
            window.set_child(web)
            # GTK4 can destroy the window without emitting a usable
            # destroy callback. Clear references on close-request before
            # GTK actually disposes the native window.
            window.connect("close-request", self._fg_close_requested)
            web.load_uri((ROOT / "ui" / "fg-settings.html").as_uri())
            window.present()

        def on_fg_drag_press(self, gesture, _n_press, x, y):
            # Preserve the undecorated window's native Wayland move gesture
            # only over the title area (not over form controls or Close).
            if not (0 <= y <= 47 and 0 <= x < 760):
                return
            if not self.fg_window:
                return
            surface = self.fg_window.get_surface()
            device = gesture.get_device()
            event = gesture.get_last_event(None)
            if not surface or not isinstance(surface, Gdk.Toplevel) or not device or not event:
                return
            surface.begin_move(device, 1, x, y, event.get_time())
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

        def _fg_close_requested(self, window):
            if self.fg_window is window:
                self.fg_destroy_count += 1
                self.fg_window = None
                self.fg_web = None
                self.fg_drag = None
                # Let GTK4 finish destroying the window. A subsequent click
                # creates a fresh window and user content manager.
            return False

        def _fg_send(self, message: dict):
            if self.fg_web:
                encoded = json.dumps(message, allow_nan=False)
                self.fg_web.evaluate_javascript(
                    "window.zeitopFgResponse(" + encoded + ")",
                    -1, None, None, None, None, None
                )

        def _fg_load(self):
            if self.fg_config_path is None:
                self.fg_config_path = fg_config.discover_config()
            state = fg_config.load_config(self.fg_config_path)
            self.fg_revision = state["revision"]
            self._fg_send({
                "type": "state", "state": state,
                "status": fg_config.runtime_status(self.fg_config_path)
            })
            self.fg_ready_count += 1
            if self.fg_smoke:
                print("ZEITOP_FG_SMOKE_CONFIG_READY", flush=True)

        def _fg_choose_file(self, kind):
            if not self.fg_window:
                return
            dialog = Gtk.FileDialog.new()
            dialog.set_title("Select lsfg-vk.dll" if kind == "dll"
                             else "Select lsfg-vk conf.toml")
            dialog.open(
                self.fg_window, None,
                lambda source, result: self._fg_file_selected(source, result, kind)
            )

        def _fg_file_selected(self, dialog, result, kind):
            try:
                selected = dialog.open_finish(result)
            except GLib.Error as error:
                # GTK cancellation is not a configuration error.
                if error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                    return
                self._fg_send({"type": "error", "message": str(error)})
                return
            path = selected.get_path() if selected else None
            if not path:
                return
            if kind == "dll":
                self._fg_send({"type": "picked_dll", "path": path})
            else:
                self.fg_config_path = Path(path)
                try:
                    self._fg_load()
                except (fg_config.ConfigError, OSError) as error:
                    self._fg_send({"type": "error", "message": str(error)})

        def on_fg_message(self, _manager, value):
            try:
                data = json.loads(value.to_string())
                if not isinstance(data, dict):
                    return
                action = data.get("action")
                if action == "fg_load":
                    self._fg_load()
                elif action == "fg_choose_dll":
                    self._fg_choose_file("dll")
                elif action == "fg_choose_config":
                    self._fg_choose_file("config")
                elif action == "fg_close":
                    if self.fg_window:
                        self.fg_window.close()
                elif action == "fg_save":
                    if self.fg_config_path is None:
                        raise fg_config.ConfigError("No configuration selected.")
                    if data.get("revision") != self.fg_revision:
                        raise fg_config.ConfigError("Configuration changed. Reload before saving.")
                    current = fg_config.runtime_status(self.fg_config_path)
                    result = fg_config.save_config(
                        self.fg_config_path, data.get("settings"),
                        self.fg_revision,
                        validator=current["cli_path"]
                    )
                    self.fg_revision = result["state"]["revision"]
                    self._fg_send({
                        "type": "saved", "state": result["state"],
                        "changed": result["changed"]
                    })
            except (ValueError, TypeError, fg_config.ConfigError, OSError) as error:
                self._fg_send({"type": "error", "message": str(error)})

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
