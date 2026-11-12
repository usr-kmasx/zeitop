#!/usr/bin/env python3
"""Compare MangoHud per-frame CSV against Zeitop's self-reported present cadence.

This runs only the installed vkcube. All output/configuration stays in this project.
No Steam, game, or user/system configuration is changed.
"""
import csv
import json
import os
import select
import socket
import statistics
import subprocess
import time
from pathlib import Path

from core import is_enabled, parse_packet, set_enabled

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runtime" / "validation_mangohud"
SOCKET = ROOT / "runtime" / "zeitop.sock"
COMMAND = ["vkcube", "--c", "240", "--wsi", "wayland",
           "--width", "320", "--height", "200", "--suppress_popups"]
CASES = (
    ("mangohud_only", False, False),
    ("zeitop_disabled", True, False),
    ("zeitop_enabled", True, True),
)


def metrics(seq):
    values = list(seq)
    if not values:
        return None
    vals = sorted(values)
    return {
        "count": len(vals),
        "mean_ms": round(statistics.mean(vals), 4),
        "median_ms": round(statistics.median(vals), 4),
        "stdev_ms": round(statistics.pstdev(vals), 4),
        "min_ms": round(vals[0], 4),
        "p95_ms": round(vals[int(.95 * (len(vals) - 1))], 4),
        "p99_ms": round(vals[int(.99 * (len(vals) - 1))], 4),
        "max_ms": round(vals[-1], 4),
        "over_33_333": sum(v > 33.333 for v in vals),
        "under_30": sum(v < 30 for v in vals),
    }


def run_one(label, with_zeitop, enabled):
    folder = BASE / label
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / "MangoHud.conf"
    config.write_text(
        "no_display=0\n"
        "fps\nframetime\nframe_timing\n"
        "autostart_log=1\nlog_duration=20\nlog_interval=0\n"
        f"output_folder={folder}\n", encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "MANGOHUD": "1",
        "MANGOHUD_CONFIGFILE": str(config),
        "XDG_CACHE_HOME": str(ROOT / "runtime/cache"),
        "XDG_CONFIG_HOME": str(ROOT / "runtime/config"),
        "XDG_DATA_HOME": str(ROOT / "runtime/data"),
        "MESA_SHADER_CACHE_DIR": str(ROOT / "runtime/cache/mesa"),
        "ZEITOP_DEBUG": "1" if with_zeitop else "0",
    })
    args = ([str(ROOT / "zeitop-run")] if with_zeitop else []) + COMMAND
    set_enabled(ROOT, enabled)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.bind(str(SOCKET))
        s.setblocking(False)
        proc = subprocess.Popen(args, cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        records = []
        start = time.monotonic()
        while proc.poll() is None or time.monotonic() - start < .3:
            ready, _, _ = select.select([s], [], [], .04)
            if ready:
                try:
                    packet = s.recv(128)
                except BlockingIOError:
                    continue
                result = parse_packet(packet)
                if result is not None:
                    pid, ms = result
                    records.append((time.monotonic() - start, pid, ms))
            if proc.poll() is not None:
                break
        stdout, stderr = proc.communicate(timeout=6)
        (folder / "vkcube.stdout").write_text(stdout, encoding="utf-8")
        (folder / "vkcube.stderr").write_text(stderr, encoding="utf-8")
        with (folder / "zeitop_telemetry.csv").open("w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(("arrival_s", "pid", "ft_ms"))
            writer.writerows(records)
    finally:
        s.close()
        SOCKET.unlink(missing_ok=True)

    logs = sorted(folder.glob("vkcube_*.csv"),
                  key=lambda f: f.stat().st_mtime_ns)
    mango_frames = []
    mango_logs = []
    if logs:
        latest = logs[-1]
        mango_logs = [str(latest.relative_to(ROOT))]
        with latest.open(newline="") as stream:
            if stream.readline().startswith("os,cpu,gpu,"):
                stream.readline()  # MangoHud system metadata values
            else:
                stream.seek(0)
            for row in csv.DictReader(stream):
                try:
                    value = float(row["frametime"])
                    if 0 < value < 5000:
                        mango_frames.append(value)
                except (KeyError, TypeError, ValueError):
                    continue

    result = {
        "label": label,
        "limit_enabled": enabled,
        "wrapped": with_zeitop,
        "exit_code": proc.returncode,
        "elapsed_s": round(time.monotonic() - start, 3),
        "mangohud": metrics(mango_frames),
        "zeitop": metrics(row[2] for row in records),
        "mangohud_csv": mango_logs,
        "zeitop_telemetry_csv": str((folder / "zeitop_telemetry.csv").relative_to(ROOT)),
        "layer_ready": "ZEITOP_VULKAN_DEVICE_READY" in stderr,
    }
    (folder / "summary.json").write_text(json.dumps(result, indent=2),
                                         encoding="utf-8")
    return result


def main():
    if not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("Wayland is not available")
    if SOCKET.exists():
        raise SystemExit("Zeitop socket exists. Close the Zeitop GUI before comparing.")
    old_state = is_enabled(ROOT)
    outcomes = []
    try:
        for label, wrapped, enabled in CASES:
            print("RUN", label, flush=True)
            result = run_one(label, wrapped, enabled)
            print(json.dumps(result, indent=2), flush=True)
            outcomes.append(result)
            if result["exit_code"] != 0 or result["mangohud"] is None:
                raise RuntimeError(f"Comparison case failed: {label}")
            if wrapped and result["zeitop"] is None:
                raise RuntimeError(f"Zeitop produced no samples in {label}")
    finally:
        set_enabled(ROOT, old_state)
    (BASE / "comparison.json").write_text(json.dumps(outcomes, indent=2),
                                          encoding="utf-8")


if __name__ == "__main__":
    main()
