"""Authenticated FG handshake, independently of Steam or user configuration."""
import json
import os
import socket
import tempfile
import threading
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import fg_ipc
from core import create_layout
from fg_live import launch_session

ROOT = Path(__file__).resolve().parents[1]
CONFIG = '''version = 2
[global]
allow_fp16 = true
[[profile]]
name = "IPC vkcube"
active_in = ["vkcube"]
multiplier = 2
flow_scale = 1.0
performance_mode = false
pacing_mode = "vsync"
'''


class TestFgIpc(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'runtime',
                                                prefix='fg_ipc_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        create_layout(self.root)
        self.config = self.root / 'original.toml'
        self.config.write_text(CONFIG)
        with patch('fg_live.fg_config.external_fg_available', return_value=True):
            self.live, _, self.pending = launch_session(
                self.root, pid=os.getpid(),
                env={'LSFGVK_CONFIG': str(self.config)})
        self.assertTrue(self.pending)
        self.original = self.config.read_bytes()
        self.token = self.live.stem

    def _roundtrip(self, authorized):
        endpoint = self.root / 'runtime/zeitop.sock'
        errors = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            server.bind(str(endpoint))
            server.settimeout(2)

            def serve_once():
                try:
                    packet, anc, flags, address = server.recvmsg(
                        256, socket.CMSG_SPACE(fg_ipc.CREDS_SIZE))
                    fg_ipc.service_packet(server, packet, address, anc, self.root)
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=serve_once, daemon=True)
            worker.start()
            with patch('fg_ipc._presenting_parent',
                       return_value=os.getpid() if authorized else None,
                       side_effect=None if authorized else PermissionError('rejected')):
                if authorized:
                    self.assertTrue(fg_ipc.request_warmup(self.root, self.token))
                else:
                    with self.assertRaisesRegex(OSError, 'rejected FG warmup'):
                        fg_ipc.request_warmup(self.root, self.token)
                worker.join(2)
            self.assertFalse(worker.is_alive(), 'IPC server did not reply')
            self.assertFalse(errors, errors)

    def test_ro_guest_can_use_abstract_socket_without_file_writes(self):
        self._roundtrip(authorized=True)
        entry = json.loads(self.live.with_suffix('.json').read_text())
        self.assertFalse(entry['pending'])
        self.assertEqual(tomllib.loads(self.live.read_text())['profile'][0]['multiplier'], 1)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_unauthorized_request_does_not_modify_session(self):
        self._roundtrip(authorized=False)
        entry = json.loads(self.live.with_suffix('.json').read_text())
        self.assertTrue(entry['pending'])
        self.assertEqual(tomllib.loads(self.live.read_text())['profile'][0]['multiplier'], 2)

    def test_missing_gui_socket_keeps_native_fallback(self):
        self.assertFalse(fg_ipc.request_warmup(self.root, self.token))
        with self.assertRaises(ValueError):
            fg_ipc.request_warmup(self.root, 'bad')


if __name__ == '__main__':
    unittest.main()
