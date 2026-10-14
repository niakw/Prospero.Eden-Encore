#!/usr/bin/env python3
"""Reproduce two independent FC27 failures from anonymized telemetry.

This is a *regression classifier and model sanity check*, not an emulator, nor
proof that changing GPU queue depth, mutex choice, JIT cache, or clocks fixes
the game. All guest buffer-mutex measurements are per-window sums across
threads, not a per-frame causal trace. No source, saves or console are read.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"tools/fixtures/fc27-2efd8b3c-stutter-windows.json"
STAGES=(("startup",0,6000),("gameplay",6000,32000),("still_presentation",32000,10**18))
FIELDS=("total","frames","seconds","fps","worst_ms","late50","late100",
        "late200","late500","cache_wait_ms","cache_contended","jit_ms",
        "guest_ipc_ms","guest_dequeue_ms","gpu_idle_ms","gpu_dispatch_ms",
        "gpu_fence_ms","gpu_full_ms","cache_buffer_wait_ms","cache_texture_wait_ms")

def load(path:Path)->list[dict[str,float]]:
    data=json.loads(path.read_text())
    assert data["source_sha"]=="2efd8b3c96608667a2b22f1751eed1a475091cce"
    assert data["fields"]==list(FIELDS)
    rows=[dict(zip(FIELDS,row,strict=True)) for row in data["rows"]]
    assert len(rows)==415 and rows[0]["total"]==130 and rows[-1]["total"]==60955
    assert all(b["total"]>a["total"] for a,b in zip(rows,rows[1:]))
    assert all(row["frames"]>0 and row["seconds"]>0 and
               row["worst_ms"]>=0 and row["late50"]>=row["late100"]>=
               row["late200"]>=row["late500"]>=0 for row in rows)
    return rows

def status(rows:list[dict])->dict:
    long50=sum(row["late50"] for row in rows)
    long500=sum(row["late500"] for row in rows)
    worst=max(row["worst_ms"] for row in rows)
    return {
        "late50_frames":round(long50),
        "late500_frames":round(long500),
        "worst_ms":round(worst,1),
        "stutter_sla":"FAIL" if long50>0 or worst>50 else "PASS",
        "gpu_queue_pressure_windows":sum(row["gpu_full_ms"]>0.01 for row in rows),
    }

def grouped(rows:list[dict])->dict:
    d={}
    for name,low,high in STAGES:
        subset=[v for v in rows if low<v["total"]<=high]
        assert subset
        def med(k):
            return round(median(x[k] for x in subset),3)
        d[name]={
            "windows":len(subset),
            "late50":round(sum(r["late50"] for r in subset)),
            "late500":round(sum(r["late500"] for r in subset)),
            "median_jit_ms_per_window":med("jit_ms"),
            "median_cache_wait_ms_per_window":med("cache_wait_ms"),
            "median_buffer_wait_ms_per_window":med("cache_buffer_wait_ms"),
            "median_gpu_idle_ms_per_window":med("gpu_idle_ms"),
        }
    return d

def synthetic_progress_pause(ms:int,compositor_fps:int=30)->dict:
    """A deterministic counterexample: GPU can present stale images smoothly.

    The guest produces unique images at 30Hz. Its producer is paused 750ms
    around 1 second, whereas the compositor continues at 30Hz with the last
    buffer. No real frame arrival times or firmware behavior are asserted.
    """
    duration_ms=3000.0
    step=1000.0/compositor_fps
    produced_ms=0.0
    last_unique=-1
    repeated=0
    max_content_age=0.0
    frame_count=0
    t=0.0
    while t<duration_ms-0.001:
        # During the guest-side pause no new content is produced.
        if not (1000<=t<1000+ms):
            produced_ms=t
            last_unique=frame_count
        else:
            repeated+=1
        max_content_age=max(max_content_age,t-produced_ms)
        frame_count+=1
        t=frame_count*step
    return {"compositor_fps":compositor_fps,
            "compositor_late50":0,
            "guest_paused_ms":ms,
            "content_repeat_frames":repeated,
            "max_content_age_ms":round(max_content_age,1),
            "gpu_queue_pressure":0}

def self_test(rows):
    t=status(rows)
    stage=grouped(rows)
    assert t["stutter_sla"]=="FAIL"
    assert (t["late50_frames"],t["late500_frames"])==(858,10)
    assert t["worst_ms"]==1288.1
    assert t["gpu_queue_pressure_windows"]==0
    assert [stage[k]["windows"] for k,_,_ in STAGES]==[42,180,193]
    assert [stage[k]["late50"] for k,_,_ in STAGES]==[109,679,70]
    assert [stage[k]["late500"] for k,_,_ in STAGES]==[7,3,0]
    # A GPU-only queue-size check incorrectly calls this real baseline clean.
    assert stage["gameplay"]["median_jit_ms_per_window"] < 50
    assert stage["gameplay"]["median_cache_wait_ms_per_window"] > 10
    # A true clean fixture must not get a false alarm.
    good=[{**r,"late50":0,"late100":0,"late200":0,"late500":0,
           "worst_ms":33.334} for r in rows]
    assert status(good)["stutter_sla"]=="PASS"
    # Both an explicit producer pause and a smooth compositor can coexist.
    model=synthetic_progress_pause(750)
    assert model["compositor_late50"]==0
    assert model["gpu_queue_pressure"]==0
    assert model["content_repeat_frames"]>=20
    assert model["max_content_age_ms"]>=700
    # Catch false positives where high compiler work is mistaken for lateness.
    high_jit=[{**r,"jit_ms":3000} for r in good]
    assert status(high_jit)["stutter_sla"]=="PASS"
    print("STUTTER_REGRESSION_PASS: real 415-window baseline correctly FAILS smoothness SLA")
    print("GUEST_PROGRESS_MODEL_PASS: 30fps presentation can repeat unchanged content")
    return t,stage,model

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    rows=load(FIXTURE)
    if args.self_test:
        t,st,model=self_test(rows)
    else:
        t,st,model=status(rows),grouped(rows),synthetic_progress_pause(750)
    result={"source_sha":"2efd8b3c96608667a2b22f1751eed1a475091cce",
            "known_bad_telemetry":t,"stage_summary":st,
            "independent_guest_pause_simulation":model,
            "limitations":"Five-second sums cannot assign cause to individual frames. "
            "No recent build was measured on console. GPU queue and content "
            "freshness are independent axes."}
    if args.json:print(json.dumps(result,indent=2))
    else:
        print("REAL_CAPTURE",t)
        for k,v in st.items():print("STAGE",k,v)
        print("SYNTHETIC_CONTENT_LIVENESS",model)
        print("NO_GAMEPLAY_FIX_CLAIMED")

if __name__=="__main__":
    main()
