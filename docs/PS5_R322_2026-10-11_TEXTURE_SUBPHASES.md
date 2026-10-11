# R322 — Identify the real FC27 1440p FillImageViews slow path

Branch `dev/ps5-sparse-jit`, upstream pinned `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Evidence and problem

R310 1440p gameplay logs show sampled individual `FillImageViews` invocations as long as ~11.361 ms; they do not reveal whether the time was spent checking TIC descriptors, uploading CPU-modified textures, searching alias candidates, or doing actual alias image copies/scale changes. R320/R321 remove redundant work in safe situations, but there is no proof they address the dominant 1440p stall source.

## Source change

Extend the existing **1-in-16 draw, Detailed Logging-only** `EDEN_GPU_CACHE_PHASE` phases with three exact-scope measurements:

- `texture_cpu_refresh`: measured only after `RefreshContents` finds a CPU-modified image; includes tracking, staging, unswizzle/conversion and upload enqueue.
- `texture_alias_scan`: measured from the alias search until no-newer-alias return or start of actual rescale/copy work. R321 latest-global-tick skip returns before starting this timer.
- `texture_alias_copy`: measure rescale selection, sort and actual image-copy work after at least one newer alias has been found.

The existing GPU cache pair locks, guest invalidation, copy/barrier semantics, memory ownership and image lifetime are **completely unchanged**. The runtime source adapter already injects `performance.h` into PS5 Vulkan's texture cache; three exact replacement pairs add the RAII timers. Non-PS5 code is guarded. With detailed logging OFF, no time is read, no per-draw print is emitted, and the timer only stores a null stats pointer.

These timers are **diagnostic**, not a claim of increased FPS or graphics quality. They allow an evidence-driven distinction between actual GPU/guest coherency work and lookups. R321 native #38153086997 SUCCESS and is a different binary; R322 must pass source/native CI before any on-console collection.

## Regression

`tools/check-ps5-texture-subphases.py` SHA verifies upstream texture cache source, parses the actual production Python adapter, ensures exactly one anchor per insertion and correct instrumentation scope, and compiles the emitted blocks under PS5 and upstream C++20. Wired into both preflight and native-build gates. Important: interpret cumulative phase timings per five-second window; timers sample only 1/16 draws, and overlapping workers/timing should not be treated as additive CPU wall time.
