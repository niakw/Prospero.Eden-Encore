# R350 — FC27 GPU stutter: a reproducible forensic split

Date: 2026-10-12. Branch: dev/ps5-sparse-jit. **No gameplay performance fix is claimed here.**

## Evidence from the existing PS5 FTP logs

Source: `heap.prev.log` and `heap.log` fetched from
`ftp://192.168.1.209:2121/data/prosperoeden/logs/`.
These are **earlier PS5 sessions** and do not represent a fresh R349 on-console test.

Reproduced with:

```sh
python3 -B tools/analyze-fc27-stutter.py --self-test
python3 -B tools/analyze-fc27-stutter.py heap.prev.log
python3 -B tools/analyze-fc27-stutter.py heap.log
```

The script pairs `EDEN_VULKAN_FRAME`, `EDEN_FRAME_PRESSURE` and `EDEN_DEV_GPU` by their exact frame key, computes deltas from the cumulative GPU snapshots, and reports 12 per-phase cache counters. In particular, it distinguishes *five-second correlations* from individual-frame causality.

| Metric | FC27 longer gameplay (`heap.prev.log`) | Later largely frozen-menu session (`heap.log`) |
| --- | ---: | ---: |
| Five-second reporting windows | 175 | 104 |
| Mean displayed FPS | 28.37 | 29.86 |
| Frame intervals above 50 ms | 1,035 | 23 |
| Windows with full GPU producer queue | 36 | **0** |
| Above-50-ms intervals in those full-queue windows | 950 (91.8%) | 0 |
| Accumulated producer queue wait | 2.179 seconds | **0** |
| Emulated GPU *worker thread* idle fraction | 75.0% | 92.0% |
| Longest recorded frame interval | 574 ms | 555 ms |

The 1,035 late frames cluster overwhelmingly into the 36 windows where the queue became full. The Pearson correlation (across five-second windows) between producer full-queue wait and late50 count is **0.821**. Correlation with incoming GPU dispatch *count* is **0.579**. The cache phase `pipeline_configure` correlation is only **0.230**, and `pair_held` only **0.184**; the CPU guest cache lock wait is **0.160**, and JIT time is **-0.018**. These measurements provide no basis for declaring JIT caching or individual pipeline compilation the primary cause of the observed sustained stutter.

**Crucial limit:** total queue wait was only ~2.18 s over ~875 s of samples. This is nowhere near enough to explain every 50-ms frame interval as a *direct time spent sleeping on the queue*. The queue becoming full is most credibly a **symptom or amplifier of bursty guest-to-GPU work delivery**. The GPU worker idles approximately three-quarters of wall clock even during the overloaded windows. That is a **CPU thread-idle measurement, NOT a hardware GPU utilization figure**; do not infer that AMD shader cores were idle 75% of the time.

The frozen menu is an **independent class of stall**: graphics presents continued at ~30 FPS with no producer queue pressure. The game image did not progress visually and Square/Triangle rebinding failed in the user's report. A functioning presentation heartbeat is not evidence of guest UI progression. This needs guest input/state and image-progress evidence, rather than the same GPU-queue fix.

## Exact native source sites audited

- `vendor/encore-active/eden-gpu/include/video_core/gpu_thread.h`: currently enforces a 32-command bounded SPSC queue for latency, unlike the original generic 4096-item default.
- `vendor/encore-active/eden-gpu/gpu_thread_quiet.cpp`: producer `PushCommand` waits via `EmplaceWaitWithStopToken` when full; the GPU worker handles complete `SubmitListCommand` through `scheduler.Push`.
- `vendor/sources/eden/src/video_core/control/scheduler.cpp`: `Scheduler::Push` binds a channel under a lock but processes commands outside it; this alone does not prove a deadlock.
- `vendor/encore-active/eden-backports/src/video_core/dma_pusher.cpp`: `DmaPusher::DispatchCalls` processes the complete queued command list, flushes the GPU command stream, and signals the command-list end. Breaking these operations apart without respecting draw/fence/order invariants would risk corrupted textures and new freezes.
- `headless/performance.cpp`: native `EDEN_FRAME_PRESSURE` and `EDEN_DEV_GPU` distinguish command producer wait, GPU worker dispatch, guest IPC/dequeue, and cache contention. These existing counters are sufficient for this post-mortem; do not add unbounded per-command logging.

## Engineering decisions

1. **Do not increase the queue to 4096** or disable back-pressure to conceal saturated periods: it risks stale input and larger guest-to-display latency.
2. **Do not force higher FPS/presentation Hz** without proving the game progresses; the later frozen-menu session demonstrates why.
3. **Do not globally eliminate required DMA flushes, guest GPU syncs or texture alias barriers** to gain throughput. FC27 already has texture/HUD corruption and requires accurate ordering.
4. Target the source and duration of **bursty command production** and command-list processing, then determine whether the host scheduler, guest frame presentation, or GPU owner batches work that should have been time-sliced without violating fences.
5. Keep the menu freeze separate: confirm physical input changes, virtual pad mapping and the guest UI's actual advancement. The R332 pad heartbeat instrumentation exists for precisely that purpose, but was not validated on a new console session.

## Acceptance criteria before asking for another console test

Native builds plus host invariant tests must pass, and a proposed source change must identify an exact previously observed stall with an ordering-safe correction. No runtime fix is inferred merely because dependency vendoring completed or a build is green. When testing is justified, judge **late38/50/100, maximum gap, command-queue waiting, input-to-visible-frame delay and image correctness**, not only average FPS. Existing logs are sufficient for the above classification but cannot prove a future patch's efficacy.


## R351 — Binder/HLE timing cross-check; do not equate back-pressure with deadlock

The offline analyzer now independently aggregates monotonic cumulative `EDEN_DEV_HLE` timers by the actual `(service, command)` tuple. It compares them with `EDEN_FRAME_PRESSURE` totals using the **existing** log files (no new console session or logging request). The command is `IHOSBinderDriver::TransactParcelAuto`, which multiplexes multiple inner graphical transactions; `cmd=3` is **not** the inner `DequeueBuffer` transaction identifier.

| Five-second observation set | Guest `dequeue` timer total | HLE `IHOSBinderDriver cmd=3` total | GPU producer queue full time |
|---|---:|---:|---:|
| Longer FC27 gameplay (175 windows) | 118.91 s | 116.51 s | 2.179 s |
| Later menu stall (104 windows) | 294.96 s | 292.64 s | 0 s |

The near matching binder/dequeue wall times suggest the HLE command's blocking time is **dominated by graphics buffer acquisition**, in both sets of logs. It does not distinguish intentional guest frame pacing/back-pressure from a stuck consumer. The menu's ~30 FPS renderer heartbeat and near-zero GPU queue pressure also show that merely increasing the command-queue length cannot address a static game menu.

**Next source investigation is BufferQueue producer wakeups, consumer release and `HardwareComposer::ComposeLocked` / GPU `WaitForComposite` order.** The existing `check-nvnflinger-dequeue-wakeup.py` regression test already checks that the epoch-based condition variable wakes two producers; do not regress that contract. The actual compositor currently waits for the previous composite before releasing acquired framebuffers, a valid ordering constraint that must not be bypassed with timeouts or unconditional releases. No completed demonstration of an orphaned buffer or missing notification exists yet; therefore this is a targeted investigation, **not** a claimed fix or a reason to skip required fences.

The 43 shipping Eden patches are integrated and qualified through R349, including the previous BufferQueue wakeup fix. These archived logs predate the R349 runtime, so they cannot prove the stall remains or has vanished in that build.
