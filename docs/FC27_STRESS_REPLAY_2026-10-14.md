# Offline FC27 stress/replay — 14 October 2026

**Scope:** Read-only post-hoc comparison of the two already-retrieved native diagnostic sessions. No console execution, save change, title profile edit, network-policy change or guest code patch was performed. The current latest native build is **not** among these sessions. These observations are not an A/B performance result attributable to subsequent commits.

## Captures compared

| Field | Earlier test | Later test |
| --- | --- | --- |
| source_sha | `c3774d3e8efbaa81c53ac3d2146848cc9b358cda` | `2efd8b3c96608667a2b22f1751eed1a475091cce` |
| diagnostic files | `heap.prev.log` / `stderr.prev.log` | `heap.log` / `stderr.log` |
| sampled windows | 68 | 415 |
| cumulative logged seconds | 341.505 | 2083.795 |
| total reported frames | 9,480 | 60,955 |
| mean FPS over sampled windows | 27.758 | 29.252 |
| windows below 25 FPS | 14 (20.6%) | 28 (6.7%) |
| largest measured frame interval | 575.264 ms | 1288.129 ms |
| frames beyond 500 ms | 2 | 10 |
| `EDEN_GPU_REPORT_STALLED` in matching stderr | 55 | 0 |

**Interpretation:** The later session has a higher average presented FPS and a smaller share of very slow sampled windows, but longer worst-case individual frames. Different durations and game scenes prevent a controlled improvement claim; compositor FPS does **not** prove continued game progression.

### Cache contention, same metric family

Among windows with FPS >= 29.9, the median cumulative *cache wait time within the window* falls from **4.686 ms** (39 sampled windows) to **0.397 ms** (341 sampled windows). Among windows below 25 FPS, it falls from **279.393 ms** (14 windows) to **41.3155 ms** (28 windows). These samples are not matching game scenes, and aggregate wait time is not a per-frame mutex latency. Both sessions still contain heavy outliers.

## Freeze signature: a different failure mode

The earlier capture had explicit GPU-stall warnings. The later capture has none in its corresponding stderr. However, the later capture's repeating-workload detector finds:

- approximately **945 seconds** of stable workload ratios toward the end of the capture, beginning near total frame **32,641**;
- **953.8 seconds** with no new completed audio decode service calls from near frame **32,491**;
- **963.9 seconds** with no new completed storage service calls from near frame **32,190**;
- compositor and GPU drawing, memory writes, IPC, and controller polls continuing.

The later progress-stall classifier returns `candidate_still_media_while_compositor_active=True`; it returns `False` for the older capture. The stable workload is **not** a proof of identical screen pixels, a frozen game process, or a particular thread deadlock. Stopping audio/storage accesses may be legitimate in some paused scenes; the user's observed end-of-match freeze remains the required visual symptom.

## Virtual replay of measured GPU owner work

Replay input consists of each session's real five-second `EDEN_VULKAN_FRAME` windows and cumulative `EDEN_DEV_GPU.dispatch_ns` / `idle_ns` counters, matched by exact frame totals. The model assumes one worker with evenly distributed owner dispatch service and a 32-item bounded queue. The "worst frame on worker" case is **counterfactual**: a long presented-frame gap is not an observed Vulkan worker pause.

| Model | Earlier 68 windows | Later 415 windows |
| --- | ---: | ---: |
| 1x nominal max pending | 1 / 32 | 1 / 32 |
| 1x nominal queue-pressure events | 0 | 0 |
| 1x with hypothetical worst frame on worker: max pending | 13 / 32 | 28 / 32 |
| 1x hypothetical queue-pressure events | 0 | 0 |
| 4x synthetic demand: queue-pressure events | 19,058 | 140,454 |
| 8x synthetic demand: queue-pressure events | 74,720 | 486,510 |

Do **not** compare raw 4x/8x pressure-event totals between unequal-length sessions. At 1x, the model has no queue backpressure, despite the observed freeze; the simplest model of a perpetually undersized GPU command queue is therefore not supported by these averages. A real driver fence, guest wait, head-of-line stall, or unchanged presented image is outside this model.

## Host regressions and stress tests re-executed

Twenty analysis/replay commands were launched against the locally available checkout and archived logs. **15 passed initially.** Five C++-based tests could not link against the Mac's default SDK (SDK 27 `tbd` architecture errors). Rerunning with explicit SDK 15.4 restored both JIT virtual-lifetime/startup tests. The remaining three failed **compilation** with the Mac's C++ library missing `std::stop_token` or `std::jthread`; they did **not** reach the assertions.

Independently, the current Linux source preflight [38540652474](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38540652474) passed the same three source-backed stress scripts:

- `tools/check-ps5-native-load-replay.py`: 1x/4x/8x stop-aware native producer queue stress, FIFO and cancellation; uses the **earlier 68-window archived fixture**.
- `tools/check-ps5-async-present-source-stress.py`: host-present-manager callback/present separation under synthetic stress.
- `tools/check-ps5-gpu-producer-wake.py`: queue-full wait, ordered delivery, teardown/cancellation.

Other successful host checks include guest progress classification, IPC analysis, JIT host allocator/source contracts, Vulkan present source replay, and the paired guest scheduler mutex test. These are host/synthetic validations, **not** FC27-on-firmware measurements or proof of a performance increase in the newest build.

## Corrective priorities

1. **P0 — stalled game progression:** observe the guest thread's actual blocked wait / PC and its synchronization partner across the frame ~32k transition, correlated to media/service progress. IPC completed-call totals alone cannot identify a blocked call.
2. **P0 — actual long frames:** isolate the ten >500 ms frame intervals from guest JIT compilation, memory paging, cache contention, shader work and presentation. Do not infer causality from average FPS.
3. **P1 — action profile:** confirm which game-owned custom control profile is selected at the pre-match screen and in match. Host physical-to-guest mapping counters are not guest action-profile evidence.
4. **P1 — HUD freshness:** compositor liveness and GPU draws do not show when the game generated new HUD content; independent image/state freshness evidence is required.
5. **Native qualification:** the later source migrations, flexible memory declaration and audio changes only become a candidate after their own green native package run; neither archived log tested these changes.

**Privacy:** This report retains counts and build SHAs only. It does not copy raw FTP logs, save content, personal file paths, or sensitive network requests to GitHub.


## Separate stutter regimes: the former GPU-only replay was too optimistic

The complete 415-window capture has a **measured 858 presentation intervals over
50 ms, including 10 over 500 ms**, with the worst gap at 1,288 ms. A GPU
dispatch-only queue replay that reports 0 full-queue windows cannot classify
this session as smooth. The source-backed regression fixture contains
**only 20 numeric timing/counter fields** per window (no raw console, network,
account or save content), and the checked-in
`tools/check-fc27-stutter-regimes.py --self-test` deliberately requires that
the actual capture be flagged `stutter_sla=FAIL`.

| Range (frame total) | Windows | >50ms intervals | >500ms intervals | Median JIT (ms/5s window) | Median cache lock wait (ms/5s window) |
|---|---:|---:|---:|---:|---:|
| <= 6,000, early compile-heavy gameplay | 42 | 109 | 7 | 592.853 | 8.552 |
| 6,001–32,000, sustained gameplay | 180 | 679 | 3 | 25.952 | 16.529 |
| >32,000, later repeating presentation | 193 | 70 | 0 | 0 | 0.257 |

These are **not controlled stage annotations or per-frame blame**. They
are ranges of frame totals, and the CPU/JIT/cache numbers are aggregates across
multiple host cores. There are two distinct stutter targets:
initial burst compilation and persistent gameplay CPU memory/cache contention.
The very quiet end stage must *not* be counted as evidence that title
progression resumed.

The source-backed `RasterizerVulkan::OnCPUWrite` currently acquires the buffer
cache lock for pages that have ever belonged to a GPU buffer. The monotonic
page-witness safely elides the lock only when no registration has ever
occurred; removing the mutex more aggressively could violate CPU/GPU memory
coherence. Do not silently remove it for a performance experiment.

Additional optional native diagnostic counters now report
`EDEN_GUEST_CACHE_LOCK_TAIL`: the **actual number of completed >1ms and
>10ms waits and the maximum individual buffer/texture wait per reporting
window**. They are disabled in quiet mode and do not alter cache lock
ownership, spin budget, or ordering. The next native trace can distinguish
hundreds of small waits from a handful of long holds. There is **no new
console trace for these counters yet**.

### Counterexample stress: compositor FPS is not content freshness

The replay now includes a deterministic 750ms guest-producer pause while
an independent 30Hz compositor continues presenting the last buffer. It
produces 0 over-50ms compositor intervals, 0 GPU queue-pressure events,
and 23 repeated-content frames. This is a *synthetic model*, not proof of
this specific game's mechanism. It prevents treating smooth 30 FPS counters
as proof that the application advanced.

**Do not claim an FPS improvement from the source-only fixes or tests**.
The 415 windows were captured on build `2efd8b3c`, not the newer binary.
