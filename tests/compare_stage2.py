#!/usr/bin/env python3
"""Paired MangoHud benchmark, independently observing Zeitop Stage 2.

Never writes outside ~/Projects/zeitop. Does not modify the production layer.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"))
from audit_pacing_experiments import run, SOCKET
from core import is_enabled, set_enabled

OUT=ROOT/"runtime"/"stage2"
LAYER=OUT
CONFIGS=(
    ("fifo_small",2,320,200),
    ("fifo_full",2,1366,768),
    ("mailbox_small",1,320,200),
)

def main():
    if SOCKET.exists():
        raise RuntimeError("Zeitop socket exists; close the GUI before benchmarking")
    built=subprocess.run(["sh",str(ROOT/"pacing"/"build_candidate.sh")],
                         cwd=ROOT,capture_output=True,text=True,timeout=30)
    if built.returncode:
        raise RuntimeError(built.stdout+built.stderr)
    previous=is_enabled(ROOT)
    paired=[]
    try:
        for name,mode,width,height in CONFIGS:
            for kind in ("old","new"):
                for trial in range(1,3):
                    label=f"stage2_ab_{name}_{kind}_{trial}"
                    set_enabled(ROOT,True)
                    print("BENCHMARK",label,flush=True)
                    options={"zeitop":True} if kind=="old" else {"audit_layer":LAYER}
                    result=run(label,frames=180,width=width,height=height,
                               vkcube_mode=mode,**options)
                    if result["exit"] or not result["layer_loaded"] or not result["mango_nominal"]:
                        raise AssertionError(f"Invalid comparison trial: {label}")
                    paired.append(result)
                    vals=result["mango_nominal"]
                    print(f"SUMMARY {label}: median={vals['median']:.4f}ms std={vals['stdev']:.4f}ms "
                          f"p95={vals['p95']:.4f}ms over33.5={vals['over_33.5']}",flush=True)
    finally:
        set_enabled(ROOT,previous)
    jsonpath=OUT/"paired_comparison.json"
    jsonpath.write_text(json.dumps(paired,indent=2),encoding="utf-8")
    lines=[
        "# Zeitop Stage 2 — Paired independent MangoHud comparison",
        "",
        "Production limiter remains unchanged; both use the same MangoHud layer",
        "order and same application/display configuration.",
        "",
        "| Test | Controller | Trial | Median (ms) | Std dev (ms) | P95 (ms) | Over 33.5 ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for x in paired:
        v=x["mango_nominal"]
        label=x["label"]
        parts=label.split("_")
        trial=parts[-1]
        kind=parts[-2]
        config="_".join(parts[2:-2])
        lines.append(f"| {config} | {kind} | {trial} | {v['median']:.4f} | "
                     f"{v['stdev']:.4f} | {v['p95']:.4f} | {v['over_33.5']} |")
    lines += ["","These are CPU-side MangoHud present-hook measurements, not display scan-out.",
              "The raw vkcube CSV files and stderr are retained under runtime/audit_pacing/runs.",
              "No rounding, clamping or ordering changes were applied to either tool.",
              ""]
    (OUT/"PAIRED_RESULTS.md").write_text("\n".join(lines),encoding="utf-8")
    print("EVIDENCE",str(jsonpath),flush=True)
    print("RESULTS_READY",len(paired), "project-local limit state restored",flush=True)

if __name__=="__main__":
    main()
