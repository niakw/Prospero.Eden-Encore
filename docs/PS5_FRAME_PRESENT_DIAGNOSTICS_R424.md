# R424 — Diagnose 30 FPS frame hitches by presentation phase

An FPS counter holding 30 FPS doesn't establish regular frame delivery. Previous PS5 detailed profiles accumulated `gpu_present_wait` across both `PresentManager::GetRenderFrame()` waits: (1) the producer waiting for a recycled frame in `free_queue` and (2) the GPU fence associated with that frame. A 30 FPS plateau with hitches cannot distinguish FIFO queue starvation from GPU completion latency with that one aggregate.

R424 adds two **detailed-mode only** counters, retaining the existing aggregate and respecting the original sequence:

- `gpu_present_free_wait`: `free_mutex` acquisition, `free_cv.wait` and ownership transfer from `free_queue`.
- `gpu_present_fence_wait`: blocking `frame->present_done.Wait()` after `free_mutex` has been released.
- `EDEN_PRESENT_WAIT_PHASE frame=... free_calls=... free_ns=... fence_calls=... fence_ns=...` every regular detailed GPU snapshot, reporting cumulative totals for delta analysis.

No new queue depth, fence semantics, swapchain structure, presentation policy, spin, busy-wait or sleep. The normal non-detailed path doesn't call a clock in either new `DiagnosticTimer`. The original `EDEN_DEV_GPU ... present_calls= ... present_ns=...` remains unchanged for existing parsers, as does the renderer's frame time.

For source provenance, the tracked complete `vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp` and `tools/prepare-vulkan-port.py` both contain equivalent transforms. Regression gates are `tools/check-ps5-present-phase-timing.py` and the full `tools/check-vendored-vulkan-fork.py`.

## Interpretation

Compare two consecutive five-second snapshots:

- Rising `free_ns` plus low `fence_ns`: free image scarcity / asynchronous presentation back-pressure, investigate presenter throughput and swapchain.
- Rising `fence_ns`: returned image is still used by GPU, investigate command completion/synchronization, not shader build count alone.
- Neither dominates while FC27 hitches: prioritize existing `EDEN_DEV_GPU` queue, `EDEN_GPU_DMA_SYNC`, guest cache wait, pipeline build, and game-vsync timestamps.

Diagnostic counters alone are **not a claim of performance improvement**. If R422 finishes first, keep it as the safe physical baseline; incorporate these counters only in the subsequent combined native candidate. No additional physical test required for a source-only R424 commit.
