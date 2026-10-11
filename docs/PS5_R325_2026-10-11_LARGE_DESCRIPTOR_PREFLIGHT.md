# R325 — Large guest descriptor reservations: move overflow wait outside paired GPU cache locks

Target branch: `dev/ps5-sparse-jit`, pinned Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Verified remaining blocking path

`RasterizerVulkan::PrepareDraw` takes `buffer_cache.mutex + texture_cache.mutex` before calling `GraphicsPipeline::Configure`. The latter calls `UpdateDescriptorQueue::Acquire(scheduler, num_descriptor_entries, uses_descriptor_buffer)`. Pinned `Acquire` calls `scheduler.WaitWorker()` whenever `used + reserve >= frame_payload_size`, where `reserve` is `num_descriptor_entries` if nonzero and `0x400` otherwise.

R319's preflight, before these locks, correctly handles ordinary `0x400`-entry reservations, but pipelines reserving **more than `0x400`** can still overflow between R319's safe threshold and the actual size. Then the pinned fallback blocks both guest buffer/texture cache locks during `WaitWorker()`.

## Narrow PS5-only correction

- `GraphicsPipeline::DescriptorEntryReservation()` exposes the immutable reservation count already computed from shader stage metadata; zero means the existing `0x400` fallback.
- Before the paired cache locks, the GPU owner runs `PreflightLargeGuestDraw` only for a reservation **larger than `0x400`**, smaller than the frame capacity, and actually crossing the current payload boundary.
- Only on a real overflow does it perform the original `scheduler.WaitWorker()`, reset the payload cursor, reflush CPU-mapped guest memory, and reselect the current graphics pipeline to respect changed shader pages. A second bounded check covers a changed pipeline size; `Acquire` remains the final safety fallback.
- No extra sleeps or waits on normal draws; no larger descriptor buffer, stolen RAM, bypassed cache lock, shader skip, unsafe guest invalidation or `vkQueueSubmit` change.

## Host qualification, not console proof

- `tools/check-ps5-large-descriptor-preflight.py` compiles and runs the **exact C++ preflight methods emitted by the generator**. Proves 1,000-entry ordinary usage does not drain; 1,500-entry reservation drains exactly at the 4,096-entry boundary, not before; oversize/invalid reservation remains under original `Acquire` fallback; preserves expected used cursor and wait count.
- R319 real C++ preflight, R323 descriptor-buffer ring and pinned Vulkan generator replay also run. This establishes source and synthetic reservation semantics, not that FC27 exhibits this path or that it improves FPS.
- Host/core and PS5 native CI must pass before releasing. Keep the known-good R324 All-On package unmodified until R325 has completed native compilation and staging. **No further on-console testing is requested on source evidence alone.**

## Forensic motivation

The previous 1440p FC27 FTP recording shows five 5-second windows with substantial GPU queue back-pressure: ~22.6 average FPS and 122 frames exceeding 50 ms, versus ~29.5 FPS / 63 late frames across the other 63 windows. GPU queue fullness is an association, not proof of descriptor overflow. This change targets a *known* wait-under-double-lock code path without claiming that the log establishes its frequency.
