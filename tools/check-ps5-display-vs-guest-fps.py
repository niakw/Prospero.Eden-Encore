#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Separate compositor callback FPS from delivered content and guest simulation age.

The real renderer reports OnFrameDisplayed() after Present(frame), while the
Vulkan presenter may be asynchronous. A nominal 30 callbacks/s does NOT prove
30 new visual states/s, scanout cadence, or timely response to guest input.
Source contracts below anchor the deterministic, host-only model in the real
PS5 native path; there is no GPU, console video-out or host streaming here.
"""
from collections import deque
from pathlib import Path
import json
import statistics

root=Path(__file__).resolve().parents[1]
renderer=(root/"vendor/encore-active/eden-vulkan/vulkan_renderer.cpp").read_text()
manager=(root/"vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
graphics=(root/"headless/graphics.cpp").read_text()
native_main=(root/"headless/main.cpp").read_text()
settings=(root/"vendor/sources/eden/src/common/settings.h").read_text()
swapchain=(root/"vendor/encore-active/eden-vulkan/vulkan_swapchain.cpp").read_text()
data=json.loads((root/"tools/fixtures/native-load-20261013.json").read_text())
rows=[dict(zip(data["window_fields"],values)) for values in data["windows"]]
stable=[w for w in rows if 29.95<=w["fps"]<=30.05 and w["worst_ms"]<38]
assert len(stable)==36, "real captured smooth-callback windows changed"
assert all(abs(w["fps"]-30)<0.05 for w in rows[-10:])

start=renderer.index("void RendererVulkan::Composite(")
end=renderer.index("\nvoid RendererVulkan::",start+1)
composite=renderer[start:end]
assert "SCOPE_EXIT {\n        render_window.OnFrameDisplayed();\n    };" in composite
assert composite.index("SCOPE_EXIT {") < composite.index("if (!render_window.IsShown())")
assert composite.index("render_window.OnFrameDisplayed()") < composite.index("present_manager.Present(frame);")
assert "if (::Eden::Display::SkipFrame())" in composite  # even this path counts the callback
present_start=manager.index("void PresentManager::Present(Frame* frame) {")
present_end=manager.index("\nsize_t PresentManager::MaxExtraFrames",present_start)
present=manager[present_start:present_end]
assert "if (use_present_thread)" in present
assert "scheduler.Record([this, frame]" in present
assert "present_queue.push_back(frame);" in present
assert "CopyToSwapchain(frame);" not in present.split("} else {")[0]
worker=manager[manager.index("void PresentManager::PresentThread("):
               manager.index("\nvoid PresentManager::RecreateSwapchain(",manager.index("void PresentManager::PresentThread("))]
assert worker.index("present_queue.pop_front();")<worker.index("CopyToSwapchain(frame);")
assert "Settings::values.async_presentation = backend == Eden::GraphicsBackend::Vulkan;" in native_main
assert "++frame_total;" in graphics and "frame_sample_count / (now - frame_sample_start)" in graphics
assert "VK_PRESENT_MODE_FIFO_KHR" in swapchain
assert "FramePacingMode::Target_Auto" in settings # no assumption about user's runtime setting

CALLBACK_MS=1000.0/30
SCANOUT_MS=1000.0/60
N=150  # 5 seconds; 30.000 composite callbacks/s
callback=[i*CALLBACK_MS for i in range(N)]
assert abs((N-1)/(callback[-1]-callback[0])*1000-30)<0.000001

def run_model(present_delay, guest_content):
    # Serial presentation worker, FIFO scanout, at most 1 new completed item
    # per 60-Hz refresh. Content identity is a MODEL, never a pixel hash.
    # "Present" completion is treated optimistically as ready-for-next-scanout.
    ready=[]
    worker_time=0.0
    for i,t in enumerate(callback):
        worker_time=max(worker_time,t)+present_delay(i)
        ready.append((worker_time,i,guest_content(i)))
    ready.sort()
    pending=deque()
    available=0
    current_sequence=-1
    current_content=-1
    deliveries=[]
    unique_changes=[]
    displayed_age=[]
    for k in range(301):
        scan=k*SCANOUT_MS
        while available<len(ready) and ready[available][0]<=scan+1e-7:
            pending.append(ready[available])
            available+=1
        if pending:
            _,seq,content=pending.popleft()
            current_sequence=seq
            if content!=current_content:
                unique_changes.append(scan)
                current_content=content
        deliveries.append(current_content)
        if current_sequence>=0:
            displayed_age.append(scan-callback[current_sequence])
    dwell=[b-a for a,b in zip(unique_changes,unique_changes[1:])]
    return {
        "callback_fps":round((N-1)/(callback[-1]-callback[0])*1000,3),
        "actual_distinct_content":len(unique_changes),
        "longest_distinct_content_hold_ms":round(max(dwell),2),
        "p95_display_age_ms":round(sorted(displayed_age)[int(0.95*(len(displayed_age)-1))],2),
        "max_display_age_ms":round(max(displayed_age),2),
        "frames_delivered_to_model":max(0,current_sequence+1),
        "present_queue_left":len(pending)
    }

normal=run_model(lambda _:3.0,lambda i:i)
late_present=run_model(lambda i:120.0 if i%30==11 else 3.0,lambda i:i)
stale_guest=run_model(lambda _:3.0,lambda i:i-((i%20)-9 if 9<=i%20<=12 else 0))
print("CAPTURE nominal_30_windows=",len(stable),"of",len(rows))
print("SCREEN_MODEL baseline=",json.dumps(normal,sort_keys=True))
print("SCREEN_MODEL delayed_async_present=",json.dumps(late_present,sort_keys=True))
print("SCREEN_MODEL repeated_guest_content=",json.dumps(stale_guest,sort_keys=True))
assert normal["callback_fps"]==late_present["callback_fps"]==stale_guest["callback_fps"]==30.0
assert normal["actual_distinct_content"]>=148
assert normal["longest_distinct_content_hold_ms"]<=50.1
assert late_present["longest_distinct_content_hold_ms"]>=100
assert late_present["p95_display_age_ms"]>normal["p95_display_age_ms"]
assert stale_guest["actual_distinct_content"]<normal["actual_distinct_content"]
assert stale_guest["longest_distinct_content_hold_ms"]>=100
print("PASS: two independent visible-stutter paths at exactly 30.000 compositor callbacks/s")
print("BOUNDARY: model deliberately cannot infer actual FC27 game-frame IDs or TV scanout from FTP counters")
