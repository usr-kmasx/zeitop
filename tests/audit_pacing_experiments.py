#!/usr/bin/env python3
"""Reproducible MangoHud vs Zeitop control-point audit. All writes project-local."""
import csv
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import parse_packet, set_enabled, is_enabled

BASE = ROOT / "runtime" / "audit_pacing" / "runs"
SOCKET = ROOT / "runtime" / "zeitop.sock"

def summarize(values):
    s = sorted(values)
    if not s:
        return None
    return {
        "n": len(s),
        "median": round(statistics.median(s), 5),
        "mean": round(statistics.mean(s), 5),
        "stdev": round(statistics.pstdev(s), 5),
        "p95": round(s[int(.95 * (len(s)-1))], 5),
        "min": round(s[0], 5),
        "max": round(s[-1], 5),
        "over_33.5": sum(x > 33.5 for x in s),
        "off_target_over_0.1ms": sum(abs(x - 1000/30) > .1 for x in s),
    }

def run(label, *, zeitop=False, native_limit="", display=True, vkcube_mode=2, audit_layer=None, frames=180, width=320, height=200):
    folder = BASE / label
    folder.mkdir(parents=True, exist_ok=True)
    assert not SOCKET.exists(), f"socket active: {SOCKET}"
    config = folder / "MangoHud.conf"
    config.write_text("\n".join([
        f"no_display={'0' if display else '1'}",
        "fps", "frametime", "frame_timing",
        "autostart_log=1", "log_interval=0", "log_duration=20",
        f"output_folder={folder}",
        f"fps_limit={30 if native_limit else 0}",
        f"fps_limit_method={native_limit or 'late'}",
        "",
    ]), encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "MANGOHUD": "1",
        "MANGOHUD_CONFIGFILE": str(config),
        "XDG_CACHE_HOME": str(ROOT/"runtime"/"cache"),
        "XDG_CONFIG_HOME": str(ROOT/"runtime"/"config"),
        "XDG_DATA_HOME": str(ROOT/"runtime"/"data"),
        "MESA_SHADER_CACHE_DIR": str(ROOT/"runtime"/"cache"/"mesa"),
        "ZEITOP_DEBUG": "1",
    })
    if audit_layer:
        env["ZEITOP_HOME"] = str(ROOT)
        env["VK_ADD_LAYER_PATH"] = str(audit_layer)
        env["VK_INSTANCE_LAYERS"] = "VK_LAYER_ZEITOP_pacing"
    args = ( [str(ROOT / "zeitop-run")] if zeitop else []) + [
        "vkcube", "--c", str(frames), "--wsi", "wayland", "--width", str(width),
        "--height", str(height), "--present_mode", str(vkcube_mode), "--suppress_popups"
    ]
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(SOCKET))
    receiver.settimeout(.25)
    try:
        proc = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                              text=True, timeout=22)
        (folder/"stdout.log").write_text(proc.stdout,encoding="utf-8")
        (folder/"stderr.log").write_text(proc.stderr,encoding="utf-8")
        z = []
        while True:
            try: data=receiver.recv(128)
            except socket.timeout:break
            item=parse_packet(data)
            if item is not None: z.append(item[1])
    finally:
        receiver.close()
        SOCKET.unlink(missing_ok=True)
    logs = sorted(folder.glob("vkcube_*.csv"), key=lambda p:p.stat().st_mtime)
    m=[]
    if logs:
        with logs[-1].open(newline="") as f:
            line=f.readline()
            if line.startswith("os,cpu,gpu"):
                f.readline()
            else:
                f.seek(0)
            for row in csv.DictReader(f):
                try:
                    v=float(row["frametime"])
                    if 0 < v < 5000: m.append(v)
                except (KeyError, TypeError, ValueError):continue
    result={
        "label":label, "exit":proc.returncode, "native_limit":native_limit,
        "zeitop":zeitop, "display":display,"present_mode":vkcube_mode,
        "mango_all":summarize(m), "mango_nominal":summarize(x for x in m if 30<=x<=40),
        "zeitop_telemetry":summarize(z),"mango_file":logs[-1].name if logs else None,
        "layer_loaded":"ZEITOP_VULKAN_DEVICE_READY" in proc.stderr
    }
    (folder/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2),flush=True)
    if proc.returncode or not m or (zeitop and not z):
        raise RuntimeError(f"bad experiment: {label}")
    return result

if __name__=="__main__":
    assert SOCKET.exists() is False, "GUI or stale socket must be handled separately"
    original = is_enabled(ROOT)
    outcomes=[]
    try:
        for kind in sys.argv[1:] or ["mango_early","mango_late","zeitop_pre","zeitop_hidden"]:
            set_enabled(ROOT,kind.startswith("zeitop") or kind.startswith("acquire") or kind.startswith("submit"))
            if kind=="mango_early": out=run(kind,native_limit="early")
            elif kind=="mango_late": out=run(kind,native_limit="late")
            elif kind=="zeitop_pre": out=run(kind,zeitop=True)
            elif kind=="zeitop_hidden": out=run(kind,zeitop=True,display=False)
            elif kind=="zeitop_immediate": out=run(kind,zeitop=True,vkcube_mode=0)
            elif kind=="zeitop_late": out=run(kind,audit_layer=ROOT/"runtime/audit_pacing/layer_late")
            elif kind=="acquire_before": out=run(kind,audit_layer=ROOT/"runtime/audit_pacing/layer_acquire_before")
            elif kind=="acquire_after": out=run(kind,audit_layer=ROOT/"runtime/audit_pacing/layer_acquire_after")
            elif kind=="submit_before": out=run(kind,audit_layer=ROOT/"runtime/audit_pacing/layer_submit_before")
            elif kind=="zeitop_late_immediate": out=run(kind,audit_layer=ROOT/"runtime/audit_pacing/layer_late",vkcube_mode=0)
            else: raise ValueError(kind)
            outcomes.append(out)
    finally:
        set_enabled(ROOT,original)
    print("RESULTS",len(outcomes), flush=True)
