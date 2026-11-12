#!/usr/bin/env python3
"""Prepare/inspect manual Steam Proton comparisons; never starts or changes games."""
import argparse
import csv
import json
import math
import re
import shlex
import statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"runtime"

def output_parent(raw):
    parent=Path(raw).resolve() if raw else (BASE/"proton_validation")
    if not parent.is_relative_to(BASE.resolve()):
        raise ValueError("all Proton test output must remain inside Zeitop/runtime")
    return parent

def name_folder(args):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}",args.name):
        raise ValueError("session name must contain only letters, digits, - and _")
    return output_parent(args.output_root)/args.name

def prepare(args):
    folder=name_folder(args)
    if folder.exists():
        raise FileExistsError(f"session already exists: {folder}")
    folder.mkdir(parents=True)
    config=folder/"MangoHud.conf"
    config.write_text("\n".join([
        "no_display=0","fps","frametime","frame_timing",
        "autostart_log=1","log_interval=0","log_duration=240",
        f"output_folder={folder}","fps_limit=0","",
    ]),encoding="utf-8")
    env=[
        "MANGOHUD=1",
        f"MANGOHUD_CONFIGFILE={shlex.quote(str(config))}",
        "ZEITOP_DEBUG=1",
    ]
    if args.controller=="new":env.append("ZEITOP_VULKAN_STAGE2=1")
    launch=" ".join(env+[shlex.quote(str(ROOT/"zeitop-run")),"%command%"])
    (folder/"SteamLaunchOptions.txt").write_text(launch+"\n",encoding="utf-8")
    (folder/"session.json").write_text(json.dumps({
        "controller":args.controller,
        "expected_zeitop_enabled":args.controller!="disabled",
        "runtime_files_only":True,"game_started":False,
        "duration_recommendation_seconds":"120-180",
        "launcher_flags":launch,
    },indent=2),encoding="utf-8")
    print(f"SESSION={folder}")
    print(f"ZEITOP_POWER={'OFF' if args.controller=='disabled' else 'ON'}")
    print("PASTE_MANUALLY_IN_STEAM_LAUNCH_OPTIONS:")
    print(launch)
    print("Launch and play the SAME scene for 2-3 minutes; never compare different scenes.")
    print("No Steam/game option has been changed by this script.")

def metrics(values):
    values=sorted(float(v) for v in values if math.isfinite(float(v)) and float(v)>0)
    if not values:return None
    def percentile(p):
        return values[max(0,math.ceil(p*len(values))-1)]
    return {
        "frames":len(values),"median_ms":round(statistics.median(values),5),
        "p95_ms":round(percentile(.95),5),"p99_ms":round(percentile(.99),5),
        "stdev_ms":round(statistics.pstdev(values),5),
        "min_ms":round(values[0],5),"max_ms":round(values[-1],5),
        "over_33_5":sum(x>33.5 for x in values),
        "under_33_333":sum(x<1000/30 for x in values)
    }

def read_csv(path):
    with path.open(newline="",encoding="utf-8") as f:
        head=f.readline()
        if head.startswith("os,cpu,gpu"):
            f.readline()  # MangoHud hardware metadata, not a frame.
        else:
            f.seek(0)
        reader=csv.DictReader(f)
        if not reader.fieldnames or "frametime" not in reader.fieldnames:
            raise ValueError(f"not a MangoHud frametime CSV: {path}")
        values=[]
        for row in reader:
            try:values.append(float(row["frametime"]))
            except (ValueError,TypeError,KeyError):pass
        return values

def report(args):
    folder=name_folder(args)
    if not (folder/"session.json").exists():
        raise FileNotFoundError(f"no prepared session: {folder}")
    files=sorted(folder.glob("*.csv"))
    if not files:raise FileNotFoundError(f"no MangoHud CSV yet in {folder}")
    reports=[]
    for file in files:
        data=metrics(read_csv(file))
        if data:
            reports.append({"file":file.name,**data})
    if not reports:raise RuntimeError("no frametimes in the CSVs")
    result={"session":args.name,"configuration":json.loads((folder/"session.json").read_text()),
            "files":reports,"note":"Select matching game-process CSVs, not launcher CSVs."}
    (folder/"report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    for action in ("prepare","report"):
        p=sub.add_parser(action)
        p.add_argument("--name",required=True)
        p.add_argument("--output-root")
        if action=="prepare":
            p.add_argument("--controller",choices=("old","new","disabled"),required=True)
    args=parser.parse_args()
    try:
        (prepare if args.action=="prepare" else report)(args)
    except (OSError,ValueError,RuntimeError) as exc:
        parser.exit(1,f"ERROR: {exc}\n")

if __name__=="__main__":
    main()
