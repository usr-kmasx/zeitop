#!/usr/bin/env python3
"""Isolated presentation schedule sweep. All outputs stay in Zeitop."""
import csv,json,os,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runtime"/"stage3"/"target_sweep"
OUT.mkdir(parents=True,exist_ok=True)
build=subprocess.run(["sh","pacing/build_stage3.sh"],cwd=ROOT,capture_output=True,text=True)
assert build.returncode==0,build.stdout+build.stderr
cases=[
    ("strict_33333",33333333,False),
    ("nearest_33333",33333333,True),
    ("strict_refresh2",33451000,False),
    ("nearest_33250",33250000,True),
]
results=[]
for name,period,nearest in cases:
    env=os.environ.copy()
    env["ZEITOP_TEST_TARGET_INTERVAL_NS"]=str(period)
    env["ZEITOP_TEST_NEAREST_REFRESH"]="1" if nearest else "0"
    for key,value in (
        ("XDG_CACHE_HOME","runtime/cache"),("XDG_CONFIG_HOME","runtime/config"),
        ("XDG_DATA_HOME","runtime/data"),("MESA_SHADER_CACHE_DIR","runtime/cache/mesa")
    ):env[key]=str(ROOT/value)
    p=subprocess.run([str(ROOT/"runtime/stage3/present_probe"),"--frames","72"],
        cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
    (OUT/f"{name}.stdout").write_text(p.stdout)
    (OUT/f"{name}.stderr").write_text(p.stderr)
    if p.returncode!=0:
        raise RuntimeError(f"{name}: exit={p.returncode}\n{p.stdout}\n{p.stderr}")
    source=ROOT/"runtime/stage3/present_feedback.csv"
    saved=OUT/f"{name}.csv"
    saved.write_bytes(source.read_bytes())
    with saved.open() as f:r=list(csv.DictReader(f))
    vals=[int(x["first_pixel_out_ns"]) for x in r]
    delta=[(b-a)/1e6 for a,b in zip(vals,vals[1:])]
    targeted=[int(x["target_time_ns"]) for x in r]
    mid=delta[3:] if len(delta)>3 else []
    stats={"case":name,"period_requested_ms":period/1e6,"nearest":nearest,
        "feedback":len(r),"intervals":len(delta),"median_ms":statistics.median(delta),
        "std_ms":statistics.pstdev(delta),"min_ms":min(delta),"max_ms":max(delta),
        "steady_median_ms":statistics.median(mid) if mid else None,
        "steady_std_ms":statistics.pstdev(mid) if mid else None,
        "over_33_5":sum(x>33.5 for x in delta),
        "under_30":sum(x<30 for x in delta),
        "target_is_present":all(v>0 for v in targeted)}
    print(json.dumps(stats),flush=True)
    results.append(stats)
(OUT/"results.json").write_text(json.dumps(results,indent=2))
print("SWEEP_COMPLETE",len(results),flush=True)
