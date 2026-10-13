#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Virtual-time workload replay from real native 5-second frame windows.

This is a deliberately optimistic SINGLE-worker queueing model: arrivals
spaced by recorded presentation intervals, GPU service cost distributed
uniformly from measured GPU owner dispatch time. Worst-frame pauses can be
injected *on the GPU worker* as a hypothetical cause. It cannot prove driver,
guest producer, IPC, scheduler or Vulkan fence timing, since exact timestamps
of those operations were not recorded.
"""
from collections import deque
import json
from pathlib import Path
from statistics import median

root = Path(__file__).resolve().parents[1]
sample = json.loads((root/"tools/fixtures/native-load-20261013.json").read_text())
fields=sample["window_fields"]
rows=[dict(zip(fields,x)) for x in sample["windows"]]
assert len(rows)==68
assert sum(x["frames"] for x in rows)==9479
assert sum(x["late500"] for x in rows)==2

def replay(rate: int, inject_frame_max_on_worker: bool):
    # Pending frame-completion times for an optimistic serial GPU worker.
    # Ignore buffers freed by the guest, guest timeout/retry and kernel fences.
    pending=deque()
    backpressure=0
    longest=0
    startup=0.0
    latest_worker_finish=0.0
    for w in rows:
        ms=w["seconds"]*1000
        n=int(w["frames"])*rate
        assert n>0
        frame_spacing=ms/n
        # Assume each observed frame requires one modeled command; GPU
        # dispatch_ms is a sum, so distribute it uniformly across frames.
        service_ms=w["gpu_dispatch_ms"]/w["frames"]
        for idx in range(n):
            arrival=startup+idx*frame_spacing
            while pending and pending[0]<=arrival:
                pending.popleft()
            if len(pending)>=32:
                backpressure+=1
                arrival=max(arrival,pending[0])
                while pending and pending[0]<=arrival:
                    pending.popleft()
            # The recorded worst_ms is a frame interval, NOT an observed GPU
            # worker stall. Inject it only as a counterfactual upper-bound.
            pause=(w["worst_ms"] if idx==n//2 and inject_frame_max_on_worker else 0.0)
            complete=max(latest_worker_finish,arrival)+service_ms+pause
            pending.append(complete)
            latest_worker_finish=complete
            longest=max(longest,len(pending))
        startup+=ms
    return {"load_factor":rate,"hypothetical_worker_pauses":inject_frame_max_on_worker,
            "max_pending":longest,"queue_backpressure_events":backpressure,
            "virtual_tail_ms":round(max(0,latest_worker_finish-startup),2)}

base=replay(1,False)
spikes=replay(1,True)
quad=replay(4,False)
octo=replay(8,False)
print("MEASURED_OBSERVATIONS windows=68 total_frames=9479 worst_interval_ms=",
      max(w["worst_ms"] for w in rows),
      "median_gpu_dispatch_ms_5s=",round(median(w["gpu_dispatch_ms"] for w in rows),1),
      "median_gpu_idle_ms_5s=",round(median(w["gpu_idle_ms"] for w in rows),1))
for case in (base,spikes,quad,octo):
    print("VIRTUAL_QUEUE",json.dumps(case,sort_keys=True))
assert base["max_pending"]<=32
assert spikes["max_pending"]<=32, "one recorded maximum pause unexpectedly overfills 32 units"
assert octo["queue_backpressure_events"]>=quad["queue_backpressure_events"]>0
# With zero GPU consumption and continued production at a nominal 30 FPS,
# a 32-element queue fills after ~1.07 seconds, not after 28 minutes.
capacity=32
fps=30.0
fill_sec=capacity/fps
stall_sec=sample["stalls"][-1][0]/1000.0
assert stall_sec>1600 and 1<fill_sec<1.1
print(f"VIRTUAL_TOTAL_STALL age={stall_sec:.3f}s no_gpu_completions=1 "
      f"32_slot_fill_at_30fps={fill_sec:.3f}s if_producer_keeps_submitting=1")
print("MODEL LIMIT: no real Vulkan/guest driver or precise command arrival timestamps")
