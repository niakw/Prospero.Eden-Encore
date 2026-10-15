# Native GPU TickWork snapshot fairness — 16 October 2026

Branch: `dev/ps5-sparse-jit`. This is a source-level liveness correction, **not** a demonstrated fix for FC27 freezes, HUD disappearance, or frame pacing. No console build or test requested.

## Identified defect

Pinned `video_core/gpu.cpp` drains `sync_requests` via `while (!sync_requests.empty())`, temporarily releasing the mutex while executing each callback. CPU threads can append more requests while that callback executes. Therefore a continuously replenished queue can keep one `GPUTick` command executing indefinitely and delay other work on the same native GPU owner, even if each callback succeeds. This is a provable unbounded-batch risk, not evidence that it occurred in the observed FC27 sessions.

## Corrective contract

Native CMake derives a **single bounded entry snapshot count** under the same `sync_request_mutex`. The worker consumes exactly that many original FIFO requests and then returns to its GPU command queue. Requests appended during processing remain pending for their own `TickGPU` commands. Call sites in the pinned GPU implementation that enqueue `RequestSyncOperation` directly also schedule `TickGPU`; the public `RequestFlush` path is paired with `TickGPU` in native `ThreadManager::FlushAndInvalidateRegion`.

Each successful callback still increments `current_sync_fence` once and notifies waiting CPU threads. An exception continues propagating with **no invented fence acknowledgement**. The `unique_lock`-owned unlock/lock pair remains exception-safe. The non-native source and experimental guest-write deferral are unchanged.

## Host validation and limits

`tools/check-gpu-sync-failure-host.py` derives the **actual native CMake source fragment**, extracts `TickWork`, and compiles it under Clang ASan/UBSan. The added cases verify 16 successive reentrant appends terminate one per tick, original FIFO requests precede a callback-enqueued request, and completion fences advance only for executed callbacks; earlier normal, throwing and fatal-waiter tests remain.

No evidence yet establishes real shader, cache, draw, guest-thread or native device progress under FC27. The historical frozen-game traces include runs where presented frames and draw counts continued, so this fix must not be credited with ending those stalls. Do not publish a console candidate or request new tests based on this host regression alone.
