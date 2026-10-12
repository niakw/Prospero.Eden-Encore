# R395 — FC27 R394 half-match: buffer-cache contention during frame pacing collapse

## Provenance / scope

- Native PS5 FW 13.60, FC27 title `0100C49025D3E000`, Vulkan, 1440p output and 1x game resolution.
- Exact R394 build: `4c84f90cf31804ee8e1301798e7f9be8047d69ad`, confirmed independently in `boot-trace(8).txt` and `heap(20261012-212056).log`.
- Captured by user after about one half of live play. `heap(20261012-212056).log` contains 114 matching five-second windows = 572.3 seconds, 16,617 counted frames.
- Old reference `heap.prev(4).log` is `fa2ad53c79f1f8039c29e60917491d671539e3f0` with 302 windows = 1515.9 seconds. The duration and mix of gameplay/menu/loading differ; do NOT treat gross frame totals as a controlled A/B.
- *No crash/freeze is confirmed by this R394 partial capture.* Further crash data can be correlated separately.

## Key observed measurements from R394 capture

- Average FPS across five-second windows: 29.03; median 30; minimum window 18.94. 750 frames >38ms, 306 >50ms, 42 >100ms, 14 >200ms, 2 >500ms; largest 543.74ms.
- Correlation of five-second late50 counts with cache contention counts: r=0.819; with aggregate wait_ms: r=0.729.
- Breaking out domains is vital: buffer contention count r=0.827 and **buffer wait_ms r=0.845**; texture wait_ms r=-0.162. Correlation is association, not per-frame causality.
- Normal windows (>=29.9 FPS; n=80) mean **12.33ms buffer lock wait and 1,107 buffer contentions per five seconds**, versus low-FPS windows (<25 FPS; n=7) mean **124.59ms buffer wait and 7,699 contentions**. Texture wait falls from 27.88ms to 16.33ms in these two groups. Because both group membership and workload vary, do not claim this alone proves the origin of every hitch.
- Three consecutive late windows:
  - frame=16384, FPS=20.28, late50=44, buffer wait=273.42ms, texture wait=18.78ms, buffer contended=16,407, gpu_full=0ms, jit=40.95ms.
  - frame=16494, FPS=21.91, late50=40, buffer wait=240.58ms, texture wait=23.24ms, buffer contended=14,626, gpu_full=0ms, jit=7.67ms.
  - frame=16618, FPS=24.78, late50=29, buffer wait=99.78ms, texture wait=18.43ms, buffer contended=6,571, gpu_full=0ms, jit=7.39ms.
- GPU thread idle times on those 5-second windows = 3454 / 3497 / 3766 ms. This measures **GPU worker thread idle**, not PS5 GPU hardware utilization.
- Texture budget at frame 16500: usage=4,380,950,528 bytes, expected=4,724,464,026, critical=5,583,457,485, `keep_dirty=1 memory_short=0`. No evidence of forced dirty-texture eviction due to pressure in this snapshot. R391 scaled-image GC backport cannot be credited as a fix for these buffer-lock stalls.
- 5.85 million instrumented CPU write entries and 214,267 cache contentions were recorded; sampling of GPU cache phases at nominal 1/16 is NOT comparable to full wall time. The GPU owner holds the **paired buffer+texture mutexes across GraphicsPipeline::Configure** (verified in `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`). Guest OnCPUWrite acquires the buffer mutex before touching the texture mutex; this is the concrete contention site.

## IPC diagnostic evidence and mitigation

- R393 IPC tracking's old 128-slot table reported `overflow_calls=63799` by frame 16618: some guest thread IDs no longer receive per-thread attribution. This does NOT imply 63,799 guest threads or blocked IPC calls. Many could be calls from a small number of untracked thread IDs.
- R395 raises fixed diagnostic slots to 1024 and caps the open-addressing path at 64 probe attempts, with an ASan/UBSan host harness covering collision and saturation. Still *only* detailed-logging mode. It cannot by itself resolve buffer-cache contention or the freeze. Avoid claiming that it does.
- Under R394 `detailed=1`, GuestCacheLock uses try_lock plus counters and elapsed clocks; `detailed=0` follows original upstream mutex.lock without that diagnostic cost. Do not assume measured detailed logging contention exactly equals quiet-mode behavior.

## Technical recommendation before any further unsafe refactor

1. Prioritize the `buffer_cache.mutex` critical section: static dependencies under `GraphicsPipeline::Configure`, descriptor staging and buffer update. The potential fix is less time **under** the lock, but only hoist operations whose inputs are immutable and validated independently. Never unlock across mutable GPU cache accesses, and never blindly enable cache-spin, DMA shortcuts or skip invalidation.
2. Preserve fence, descriptor and buffer lifetime invariants and vendor/source-generator byte equivalence. Changes to `vendor/encore-active/eden-vulkan` must be synchronized with `tools/prepare-vulkan-port.py` and covered by host structural/behavioral tests.
3. On a future comparable native build, compare the same title, settings and warm cache, focusing on buffer contention per five-second window, late50 events and stability/HUD corruption rather than mean FPS alone.
4. If an actual FC27 freeze occurs, obtain live IPC progress and guest-PC/thread evidence; R393 cumulative completed IPC service durations alone do not prove deadlock.

Source artifacts: user-provided October 12 R394 and previous PS5 boot/heap/stderr diagnostic logs, analyzed offline, never committed verbatim.
