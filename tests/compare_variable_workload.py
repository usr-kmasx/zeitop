#!/usr/bin/env python3
"""Controlled CPU work + actual Wayland Vulkan present; MangoHud independent log.

Runs only the Zeitop-contained test renderer, does not launch Steam/games.
Everything written under ROOT/runtime/variable_workload; restores limit.state.
"""
import argparse
import csv
import json
import math
import os
import socket
import statistics
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import is_enabled,set_enabled

BASE=ROOT/"runtime"/"variable_workload"
PATTERNS=("5","20","33","40","random")

def summarize(values):
    vals=sorted(v for v in values if math.isfinite(v) and 0<v<5000)
    if not vals:return None
    def percentile(n):
        return vals[max(0,math.ceil(n*len(vals))-1)]
    return {
        "n":len(vals),"median_ms":round(statistics.median(vals),5),
        "mean_ms":round(statistics.mean(vals),5),
        "stdev_ms":round(statistics.pstdev(vals),5),
        "p95_ms":round(percentile(.95),5),"p99_ms":round(percentile(.99),5),
        "min_ms":round(vals[0],5),"max_ms":round(vals[-1],5),
        "over_33_5":sum(v>33.5 for v in vals),
        "under_33_333":sum(v<1000/30 for v in vals),
        "under_30":sum(v<30 for v in vals)
    }

def read_mango(path):
    with path.open(newline="",encoding="utf-8") as file:
        first=file.readline()
        if first.startswith("os,cpu,gpu"):
            file.readline()  # metadata, not frame data
        else:
            file.seek(0)
        rows=csv.DictReader(file)
        return [float(row["frametime"]) for row in rows
                if row.get("frametime") and math.isfinite(float(row["frametime"]))]

def run_case(base,pattern,kind,trial,frames):
    label=f"{pattern}_{kind}_{trial:02d}"
    folder=base/label
    if folder.exists():raise RuntimeError(f"output already exists, will not reuse {folder}")
    folder.mkdir(parents=True)
    conf=folder/"MangoHud.conf"
    conf.write_text("\n".join((
        "no_display=0","fps","frametime","frame_timing",
        "autostart_log=1","log_interval=0","log_duration=30",
        f"output_folder={folder}","fps_limit=0","",
    )),encoding="utf-8")
    env=os.environ.copy()
    env.update({
        "MANGOHUD":"1","MANGOHUD_CONFIGFILE":str(conf),
        "ZEITOP_DEBUG":"1",
        "ZEITOP_TEST_WORK_PATTERN":pattern,
        "ZEITOP_TEST_WORK_SEED":str(1729+trial),
        "XDG_CACHE_HOME":str(ROOT/"runtime/cache"),
        "XDG_CONFIG_HOME":str(ROOT/"runtime/config"),
        "XDG_DATA_HOME":str(ROOT/"runtime/data"),
        "MESA_SHADER_CACHE_DIR":str(ROOT/"runtime/cache/mesa"),
    })
    if kind=="new":
        env["ZEITOP_VULKAN_STAGE2"]="1"
    else:
        env.pop("ZEITOP_VULKAN_STAGE2",None)
    args=[str(ROOT/"zeitop-run"),str(ROOT/"runtime/stage3/present_probe"),
          "--untimed-frames",str(frames)]
    proc=subprocess.run(args,env=env,cwd=ROOT,capture_output=True,
                        text=True,timeout=max(45,frames*.09+10))
    (folder/"stdout.log").write_text(proc.stdout,encoding="utf-8")
    (folder/"stderr.log").write_text(proc.stderr,encoding="utf-8")
    files=sorted(folder.glob("present_probe_*.csv"),
                 key=lambda f:f.stat().st_mtime_ns)
    if proc.returncode or not files:
        raise RuntimeError(f"{label}: exit {proc.returncode}; MangoHud CSV missing? "
                           f"See {folder}/stderr.log")
    if "ZEITOP_VULKAN_DEVICE_READY" not in proc.stderr:
        raise RuntimeError(f"{label}: Vulkan interception not verified")
    if kind=="new" and "ZEITOP_FRAME_CONTROLLER_READY" not in proc.stderr:
        raise RuntimeError(f"{label}: candidate layer not loaded")
    if f"ZEITOP_TEST_WORK_PATTERN={pattern}" not in proc.stdout:
        raise RuntimeError(f"{label}: synthetic CPU work not verified")
    if f"ZEITOP_PRESENTS_SUBMITTED={frames}" not in proc.stdout:
        raise RuntimeError(f"{label}: incomplete presentation count")
    raw=read_mango(files[-1])
    if len(raw)<12:
        raise RuntimeError(f"{label}: insufficient MangoHud samples: {len(raw)}")
    result={
        "label":label,"pattern":pattern,"controller":kind,"trial":trial,
        "target_ms":round(1000/30,6),"seed":1729+trial,
        "frames_requested":frames,
        "mangohud_raw":summarize(raw),
        "mangohud_nominal_30_to_40":summarize(v for v in raw if 30<=v<=40),
        "mango_file":str(files[-1].relative_to(ROOT)),
        "stdout_file":str((folder/"stdout.log").relative_to(ROOT)),
        "stderr_file":str((folder/"stderr.log").relative_to(ROOT)),
    }
    (folder/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--runs",type=int,default=10)
    parser.add_argument("--frames",type=int,default=72)
    parser.add_argument("--patterns",default=",".join(PATTERNS))
    parser.add_argument("--tag",default="repeated")
    args=parser.parse_args(argv)
    patterns=tuple(args.patterns.split(","))
    if (not patterns or any(x not in PATTERNS for x in patterns)
        or args.runs<1 or args.runs>30 or args.frames<32 or args.frames>240):
        parser.error("invalid workload, run count or frames")
    if not os.environ.get("WAYLAND_DISPLAY"):
        raise RuntimeError("No Wayland session")
    if (ROOT/"runtime/zeitop.sock").exists():
        raise RuntimeError("Zeitop UI socket active; refusing to interfere")
    work=BASE/args.tag
    if work.exists():raise RuntimeError(f"Results exist; choose a new --tag: {work}")
    work.mkdir(parents=True)
    for command in (["sh",str(ROOT/"pacing/build_stage3.sh")],
                    ["sh",str(ROOT/"pacing/build_candidate.sh")]):
        build=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        if build.returncode:raise RuntimeError(build.stdout+build.stderr)
    original=is_enabled(ROOT)
    results=[]
    try:
        for pattern in patterns:
            for trial in range(1,args.runs+1):
                # Alternate ordering to reduce drift from temperature/scheduler.
                order=("old","new") if trial%2 else ("new","old")
                for kind in order:
                    set_enabled(ROOT,True)
                    print(f"RUN {pattern} {kind} trial={trial}/{args.runs}",flush=True)
                    result=run_case(work,pattern,kind,trial,args.frames)
                    results.append(result)
                    m=result["mangohud_raw"]
                    print(f"RESULT {result['label']} n={m['n']} "
                          f"median={m['median_ms']} p99={m['p99_ms']} "
                          f"over33.5={m['over_33_5']} under33.333={m['under_33_333']}",
                          flush=True)
    finally:
        set_enabled(ROOT,original)
        (work/"raw_results.json").write_text(json.dumps(results,indent=2),
                                             encoding="utf-8")
        print(f"STATE_RESTORED={int(is_enabled(ROOT)==original)}",flush=True)
    if len(results)!=len(patterns)*args.runs*2:
        raise RuntimeError("Insufficient completed benchmark runs")
    rows=[]
    for pattern in patterns:
        for kind in ("old","new"):
            filtered=[r for r in results if r["pattern"]==pattern
                      and r["controller"]==kind]
            row={
                "work_pattern":pattern,"controller":kind,
                "runs":len(filtered),
                "median_of_trial_medians_ms":round(statistics.median(
                    r["mangohud_raw"]["median_ms"] for r in filtered),5),
                "median_of_trial_p99_ms":round(statistics.median(
                    r["mangohud_raw"]["p99_ms"] for r in filtered),5),
                "total_over_33_5":sum(r["mangohud_raw"]["over_33_5"] for r in filtered),
                "total_under_33_333":sum(r["mangohud_raw"]["under_33_333"]
                                          for r in filtered),
                "total_samples":sum(r["mangohud_raw"]["n"] for r in filtered)
            }
            rows.append(row)
    (work/"summary.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
    print("SUMMARY",json.dumps(rows),flush=True)
    print("COMPLETE",len(results),"raw MangoHud runs retained under",work,flush=True)

if __name__=="__main__":
    main()
