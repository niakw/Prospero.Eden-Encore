# R319 — Drain Vulkan graphics descriptor overflow outside cache-pair locks

Branch `dev/ps5-sparse-jit`, pinned Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Concrete contention mechanism

Pinned `RasterizerVulkan::PrepareDraw` acquires `std::scoped_lock{buffer_cache.mutex, texture_cache.mutex}` and calls `GraphicsPipeline::ConfigureImpl`, which calls `guest_descriptor_queue.Acquire(scheduler, num_descriptor_entries, uses_descriptor_buffer)`. When per-frame descriptor payload usage plus this reservation reaches `frame_payload_size`, original `UpdateDescriptorQueue::Acquire` invokes `scheduler.WaitWorker()` **while both cache mutexes are held**. Guest `OnCPUWrite` or texture read/flush requests wait for those same locks. This is a provable path to thread contention, but the existing R310 FC27 logs do not prove a specific payload-overflow count. Do not claim it is the sole stutter source.

## Conservative PS5-only preflight

A new **inline, PS5-only** `UpdateDescriptorQueue::PreflightGuestDraw` tests the ordinary 0x400-entry reserve; when near capacity it invokes the **same** scheduler worker drain and resets only the payload cursor, before the rasterizer obtains the graphics cache pair locks. It does not touch descriptor contents, formats, existing barriers or Vulkan command ordering. After an actual drain, `gpu_memory->FlushCaching()` runs again to include guest memory invalidations that arrived while the GPU thread waited. The pipeline is selected **after** draining, not held across it. Original `Acquire` remains completely unchanged and still protects unusually large reservations (>0x400 entries).

This is a targeted reduction of possible critical-section wait, not a blanket replacement of GPU locks or scheduler synchronization. Normal draws add an O(1) space check. If overflow never occurs in a scene, this change will not eliminate its stutters. The code is guarded by `PS5_NATIVE` and does not affect non-PS5 targets.

## Tests

`tools/check-ps5-descriptor-queue-preflight.py` verifies exact git SHA blobs for pinned rasterizer and descriptor header, extracts the real production adapter, checks call ordering and the unmodified upstream overflow safety gate, compiles the actual PS5 preflight method, and exercises normal, nearly-full, oversized and boundary conditions. Wired to host core and native PS5 gates. Requires native build and hardware observation to qualify performance gains.

## Source qualification and native gate

Host source preflight [#38140834981](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38140834981) **SUCCESS**, including the exact C++ descriptor reserve overflow replay. Full PS5 native All-On compilation requested only after this result, on the same R319 code. Source CI success does not prove on-console FPS, absence of stutter, or texture detail correctness.
