"""First-present handshake over Zeitop's existing local telemetry socket.

The game/Proton only sends a datagram; the GTK host performs filesystem writes
outside Pressure Vessel's read-only bind mount. No system IPC path is created.
"""
from __future__ import annotations

import os
import secrets
import socket
import struct
from pathlib import Path

REQUEST = b"ZEITOP_FG_WARMUP1 "
REPLY = b"ZEITOP_FG_RESULT1 "
CREDS_SIZE = struct.calcsize("3i")


def _valid_token(token: str) -> bool:
    return (isinstance(token, str) and len(token) == 24 and
            all(c in "0123456789abcdef" for c in token))


def request_warmup(root: Path, token: str, *, timeout: float = 1.35) -> bool:
    """Return False only when the GUI socket does not exist or is stale.

    When the GUI is connected, it MUST acknowledge success before the game
    releases its first presentation. A connected but failing server is not
    bypassed by doing uncoordinated writes in the game namespace.
    """
    if not _valid_token(token):
        raise ValueError("Invalid Frame Generation session token")
    endpoint = Path(root) / "runtime" / "zeitop.sock"
    if not endpoint.is_socket():
        return False
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        # Linux abstract address: no bind/lock files inside read-only Proton.
        address = "\0zeitop-fg-" + str(os.getpid()) + "-" + secrets.token_hex(8)
        client.bind(address)
        client.settimeout(timeout)
        try:
            client.sendto(REQUEST + token.encode("ascii"), str(endpoint))
        except (FileNotFoundError, ConnectionRefusedError):
            return False
        try:
            reply = client.recv(256)
        except socket.timeout as error:
            raise TimeoutError("Zeitop GUI did not acknowledge FG warmup") from error
    prefix = REPLY + token.encode("ascii") + b" "
    if not reply.startswith(prefix):
        raise OSError("Invalid Frame Generation IPC response")
    status = reply[len(prefix):]
    if status == b"OK":
        return True
    raise OSError("Zeitop GUI rejected FG warmup: " + status.decode("ascii", "replace"))


def _presenting_parent(peer_pid: int, token: str) -> int:
    """Authenticate the host PID of the Vulkan process via kernel creds.

    The helper is directly spawned by Vulkan. Linux SCM_CREDENTIALS supplies
    the host-visible helper PID even when Proton has a different PID view.
    The parent is required to actually carry this launch's random token.
    """
    process = Path("/proc") / str(peer_pid)
    stat = (process / "stat").read_text(encoding="ascii")
    parent = int(stat.rsplit(") ", 1)[1].split()[1])
    if parent <= 1:
        raise PermissionError("Warmup requester no longer has a Vulkan parent")
    inherited = (Path("/proc") / str(parent) / "environ").read_bytes().split(b"\0")
    if b"ZEITOP_FG_WARMUP_TOKEN=" + token.encode("ascii") not in inherited:
        raise PermissionError("Warmup requester does not own this launch token")
    return parent


def service_packet(sock: socket.socket, packet: bytes, address, ancdata, root: Path) -> bool:
    """Handle an IPC datagram and return whether it belongs to this protocol."""
    if not packet.startswith(REQUEST):
        return False
    token_bytes = packet[len(REQUEST):]
    try:
        token = token_bytes.decode("ascii")
    except UnicodeDecodeError:
        return True
    if not _valid_token(token) or not address:
        return True
    try:
        credential = next((body for level, kind, body in ancdata
                           if level == socket.SOL_SOCKET and
                           kind == socket.SCM_CREDENTIALS and
                           len(body) >= CREDS_SIZE), None)
        if credential is None:
            raise PermissionError("Missing Unix peer credentials")
        peer_pid, uid, _gid = struct.unpack("3i", credential[:CREDS_SIZE])
        if uid != os.getuid() or peer_pid <= 1:
            raise PermissionError("Unauthorized warmup requester")
        parent_pid = _presenting_parent(peer_pid, token)
        # Imported here to avoid a cycle: fg_live CLI uses request_warmup.
        from fg_live import warmup_session
        warmup_session(root, token, pid=parent_pid)
        status = b"OK"
        if os.environ.get("ZEITOP_DEBUG"):
            print(f"ZEITOP_FG_IPC_OK parent={parent_pid}", flush=True)
    except Exception as error:
        # The GUI must never crash on a malformed or failed IPC request.
        print(f"Zeitop FG IPC: {error}", flush=True)
        status = b"ERR"
    try:
        sock.sendto(REPLY + token_bytes + b" " + status, address)
    except OSError as error:
        print(f"Zeitop FG IPC reply failed: {error}", flush=True)
    return True
