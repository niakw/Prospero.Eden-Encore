#!/usr/bin/env python3
"""Correlate exact completed buffer-cache wait outliers with late-frame windows.

Old captures that predate EDEN_GUEST_CACHE_LOCK_TAIL are explicitly "unknown",
never zero. Correlation over five-second windows does not establish causality.
This utility operates on read-only logs, not game saves or network data.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re
import statistics

KV=re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=(-?[0-9]+(?:\.[0-9]+)?)")
DOMAIN=re.compile(r"\bdomain=(buffer|texture)\b")

def numbers(line):
    return {k:float(v) for k,v in KV.findall(line)}

def correlate(pairs):
    if len(pairs)<3:
        return None
    a,b=zip(*pairs)
    ma,mb=statistics.mean(a),statistics.mean(b)
    va=sum((x-ma)**2 for x in a)
    vb=sum((x-mb)**2 for x in b)
    if va<=0 or vb<=0:return None
    return round(sum((x-ma)*(y-mb) for x,y in pairs)/(va*vb)**0.5,3)

def analyze(text):
    frames={}
    pressure={}
    tails=defaultdict(dict)
    for line in text.splitlines():
        if line.startswith("EDEN_VULKAN_FRAME "):
            d=numbers(line)
            if "total" in d:frames[int(d["total"])]=d
        elif line.startswith("EDEN_FRAME_PRESSURE "):
            d=numbers(line)
            if "frame" in d:pressure[int(d["frame"])]=d
        elif line.startswith("EDEN_GUEST_CACHE_LOCK_TAIL "):
            d=numbers(line)
            m=DOMAIN.search(line)
            if m and {"frame","wait_ge1ms","wait_ge10ms","max_wait_ns"} <= d.keys():
                frame=int(d["frame"])
                # Do not combine duplicate lines: incomplete/reset session.
                if m.group(1) in tails[frame]:
                    raise ValueError("duplicate lock-tail sample")
                tails[frame][m.group(1)]=d
    common=sorted(frames.keys() & pressure.keys())
    rows=[]
    for frame in common:
        item=frames[frame]
        p=pressure[frame]
        wait=tails.get(frame,{})
        rows.append({"frame":frame,"fps":item.get("fps"),
                     "late50":int(item.get("late50",0)),
                     "worst_ms":item.get("worst_ms"),
                     "jit_ms":p.get("jit_ms"),
                     "buffer":wait.get("buffer"),"texture":wait.get("texture")})
    complete=[r for r in rows if r["buffer"] is not None and r["texture"] is not None]
    missing=len(rows)-len(complete)
    if not complete:
        return {"windows":len(rows),"tail_status":"NOT_MEASURED",
                "measured_windows":0,"missing_windows":missing,
                "reason":"No complete buffer+texture lock-tail counters were recorded"}
    by_domain={}
    for domain in ("buffer","texture"):
        samples=[r for r in complete if r[domain] is not None]
        by_domain[domain]={
            "completed_wait_ge1ms":int(sum(r[domain]["wait_ge1ms"] for r in samples)),
            "completed_wait_ge10ms":int(sum(r[domain]["wait_ge10ms"] for r in samples)),
            "largest_single_wait_ms":round(max(r[domain]["max_wait_ns"] for r in samples)/1e6,3),
            "late50_correlation":correlate([(r[domain]["wait_ge10ms"],r["late50"]) for r in samples])
        }
    highest=sorted(complete,key=lambda r:(-r["late50"],-r["worst_ms"]))[:12]
    return {
        "windows":len(rows),
        "tail_status":"COMPLETE" if not missing else "PARTIAL",
        "measured_windows":len(complete),"missing_windows":missing,
        "domains":by_domain,
        "worst_windows":[{
            "frame":r["frame"],"late50":r["late50"],"worst_ms":r["worst_ms"],
            "jit_ms":r["jit_ms"],
            "buffer_wait_ge10ms":int(r["buffer"]["wait_ge10ms"]),
            "buffer_max_wait_ms":round(r["buffer"]["max_wait_ns"]/1e6,3),
            "texture_max_wait_ms":round(r["texture"]["max_wait_ns"]/1e6,3)
        } for r in highest],
        "caution":"Aggregate wait counters can overlap across CPU cores. "
                  "A single >10ms completed wait is not proof of a matching late frame."
    }

def self_test():
    def window(n,late,bwait,twait):
        lines=[
            f"EDEN_VULKAN_FRAME frames=150 seconds=5 fps=30 worst_ms={40+late*70} total={n} late50={late}",
            f"EDEN_FRAME_PRESSURE frame={n} jit_ms={n/100}",
            f"EDEN_GUEST_CACHE_LOCK_TAIL frame={n} domain=buffer wait_ge1ms=2 wait_ge10ms={bwait} max_wait_ns={12_000_000 if bwait else 900_000}",
            f"EDEN_GUEST_CACHE_LOCK_TAIL frame={n} domain=texture wait_ge1ms=1 wait_ge10ms={twait} max_wait_ns={15_000_000 if twait else 600_000}"
        ]
        return "\n".join(lines)
    text="\n".join(window(n,late,b,t) for n,late,b,t in [(150,0,0,0),(300,3,1,0),(450,8,2,1),(600,2,0,0)])
    result=analyze(text)
    assert result["tail_status"]=="COMPLETE" and result["measured_windows"]==4
    assert result["domains"]["buffer"]["completed_wait_ge10ms"]==3
    assert result["domains"]["buffer"]["largest_single_wait_ms"]==12
    assert result["domains"]["texture"]["completed_wait_ge10ms"]==1
    assert result["worst_windows"][0]["frame"]==450
    old=analyze("\n".join(x for x in text.splitlines() if not x.startswith("EDEN_GUEST_CACHE_LOCK_TAIL")))
    assert old["tail_status"]=="NOT_MEASURED"
    partial=analyze(text.replace("frame=450 domain=texture","frame=450 domain=other"))
    assert partial["tail_status"]=="PARTIAL" and partial["missing_windows"]==1
    print("GUEST_LOCK_TAIL_REPLAY_PASS complete/partial/not-measured distinguished")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("heap_log",type=Path,nargs="?")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.self_test:self_test()
    elif args.heap_log:
        from json import dumps
        print(dumps(analyze(args.heap_log.read_text(errors="replace")),indent=2))
    else:p.error("Provide a heap log or --self-test")

if __name__=="__main__":
    main()
