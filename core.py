"""Project-local controls and telemetry validation."""
import math
import json
import shlex
import time
from collections import deque
from pathlib import Path

TARGET_MS = 1000.0 / 30.0


def brand_drag_hit(x: float, y: float, button: int) -> bool:
    """Fixed-size 480x206 GUI: native move is reserved for the ZeiTop wordmark."""
    return button == 1 and 42 <= x <= 115 and 12 <= y <= 45


def decode_message(value):
    """WebKitGTK 6 passes a JavaScriptCore.Value, not JavascriptResult."""
    try:
        data = json.loads(value.to_string())
    except (ValueError, TypeError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None
    action = data.get("action")
    return action if action in {"toggle", "toggle_fg", "copy", "close", "settings"} else None

def create_layout(root: Path) -> None:
    folder = Path(root) / "runtime"
    folder.mkdir(parents=True, exist_ok=True)
    state = folder / "limit.state"
    if not state.exists():
        state.write_text("0\n", encoding="ascii")
    # External lsfg-vk is opt-in and independently controlled.
    fg_state = folder / "fg.state"
    if not fg_state.exists():
        fg_state.write_text("0\n", encoding="ascii")

def is_enabled(root: Path) -> bool:
    try:
        return (Path(root) / "runtime" / "limit.state").read_text(encoding="ascii").strip() == "1"
    except OSError:
        return False

def set_enabled(root: Path, enabled: bool) -> None:
    create_layout(root)
    state = Path(root) / "runtime" / "limit.state"
    temp = state.with_suffix(".state.tmp")
    temp.write_text("1\n" if enabled else "0\n", encoding="ascii")
    temp.replace(state)

def is_fg_enabled(root: Path) -> bool:
    """Requested hot-reload state for the generated lsfg-vk runtime config."""
    try:
        return (Path(root) / "runtime" / "fg.state").read_text(encoding="ascii").strip() == "1"
    except OSError:
        return False


def set_fg_enabled(root: Path, enabled: bool) -> None:
    """Atomic opt-in toggle; independent of the live frame limiter flag."""
    create_layout(root)
    state = Path(root) / "runtime" / "fg.state"
    temp = state.with_suffix(".state.tmp")
    temp.write_text("1\n" if enabled else "0\n", encoding="ascii")
    temp.replace(state)


def launch_option(root: Path) -> str:
    return f"{shlex.quote(str(Path(root).resolve() / 'zeitop-run'))} %command%"

def parse_packet(packet: bytes):
    try:
        fields = packet.decode("ascii").split()
        if len(fields) != 3 or fields[0] != "ZEITOP1":
            return None
        pid = int(fields[1])
        frame_ms = float(fields[2])
        if pid < 1 or not (0 < frame_ms <= 5000) or not math.isfinite(frame_ms):
            return None
        return (pid, frame_ms)
    except (UnicodeError, ValueError, OverflowError):
        return None

def severity(ms: float) -> str:
    return "good" if ms <= 34.5 else "warn" if ms <= 40.0 else "bad"


class TelemetryTracker:
    """Separate streams so launcher and game cannot erase one another.

    Prefer the most recently appearing sustained source (at least four frames).
    If it stops presenting, fall back to another active process.
    """

    def __init__(self, max_samples=100, idle_seconds=2.5):
        self.sources = {}
        self.max_samples = max_samples
        self.idle_seconds = idle_seconds

    def record(self, pid: int, frame_ms: float, now=None) -> None:
        now = time.monotonic() if now is None else now
        if pid < 1 or not math.isfinite(frame_ms) or not (0 < frame_ms <= 5000):
            return
        self._prune(now)
        source = self.sources.get(pid)
        if source is None:
            source = {
                "started": now,
                "last": now,
                "samples": deque(maxlen=self.max_samples),
            }
            self.sources[pid] = source
        source["last"] = now
        source["samples"].append(frame_ms)

    def _prune(self, now) -> None:
        for pid in list(self.sources):
            if now - self.sources[pid]["last"] > self.idle_seconds:
                del self.sources[pid]

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        self._prune(now)
        if not self.sources:
            return {"pid": None, "samples": [], "real": None, "average": None}
        stable = [(pid, source) for pid, source in self.sources.items()
                  if len(source["samples"]) >= 4]
        candidates = stable or list(self.sources.items())
        pid, selected = max(candidates, key=lambda item: item[1]["started"])
        samples = list(selected["samples"])
        return {
            "pid": pid,
            "samples": samples,
            "real": round(samples[-1], 2),
            "average": round(sum(samples) / len(samples), 2),
        }


class AverageDisplayCadence:
    """Hold the last-100-frames average stable for one-second intervals.

    First reading, PID changes and disconnects are applied immediately.
    Only the number shown for the selected ongoing process is throttled;
    real frame times and chart samples continue at their original cadence.
    """

    def __init__(self, interval_seconds=1.0):
        self.interval_seconds = interval_seconds
        self.pid = None
        self.last_update = None
        self.value = None

    def display(self, pid, average_ms, now=None):
        now = time.monotonic() if now is None else now
        if pid is None or average_ms is None:
            self.pid = None
            self.last_update = None
            self.value = None
            return None
        if (
            pid != self.pid or self.last_update is None or
            now - self.last_update >= self.interval_seconds
        ):
            self.pid = pid
            self.last_update = now
            self.value = average_ms
        return self.value
