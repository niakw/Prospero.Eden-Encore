# R352 — Fence-safe NVNflinger screen and layer teardown

Branch `dev/ps5-sparse-jit`, 2026-10-12.

## Reproduced source-level lifecycle defect

The pinned Eden `SurfaceFlinger::DestroyLayer` only erased the layer from its master registry. If a display's stack still retained the corresponding `shared_ptr`, it remained present and owned by the display and its `HardwareComposer` could continue holding an acquired guest `BufferQueue` slot. `SurfaceFlinger::RemoveDisplay` similarly erased the display without explicitly releasing the compositor's outstanding framebuffers.

The ordinary `Container::CloseLayerLocked` does remove stacked layers, but `Container::OnTerminate` invokes `DestroyLayerLocked` directly during mass teardown. The old code therefore had real uncovered paths. These omissions risk retained graphics buffers, failure to release guest queue slots and new frame acquisition stalls. We have **not established** that this is the specific cause of FC27's frozen button remapping menu: the previous telemetry also includes legitimate presentation back-pressure, so attribution still needs a console run.

## Exact correction, no new runtime patcher

The full `surface_flinger.cpp` translation unit is checked in at:

`vendor/encore-active/eden-surface-lifecycle/src/core/hle/service/nvnflinger/surface_flinger.cpp`

The pinned original stays untouched at `vendor/sources/eden/src/core/hle/service/nvnflinger/surface_flinger.cpp`. The standalone `tools/install-vendored-surface-lifecycle.py` installs the entire checked-in compiled source into the disposable Eden worktree, after the 43 existing shipping backports and before CMake. It checks the original git-blob SHA, the pinned Eden commit and rejects unexpected source drift.

The correction modifies three `SurfaceFlinger` methods:

- **RemoveLayerFromDisplayStack:** checks that the layer is actually attached; waits for any prior GPU composite fence to complete before releasing the still-acquired framebuffer and removing the layer; a second removal is a no-op.
- **DestroyLayer:** first detaches the layer from *all* display stacks using the same fence-safe method, even when the caller bypassed `CloseLayerLocked`, then erases the master registration.
- **RemoveDisplay:** waits for the prior composite before releasing every attached layer's acquired buffer, clears the display's stack and erases the display. A duplicate display removal does nothing.

Crucially, the correction **does not ignore presentation fences, free buffers ahead of GPU completion, enlarge the GPU command queue or change the title's 30 FPS presentation policy**. Those shortcuts could cause further texture corruption or control lag.

## Host and native tests

`tools/check-surface-lifecycle.py` extracts the **actual four compiled method bodies** (`FindDisplay` and the three modified methods) from the full versioned C++ file, compiles them as C++20 with only surrounding system classes mocked, and checks:

1. Normal layer removal waits before release and is idempotent.
2. Direct destruction of a still-stacked layer detaches and frees it.
3. Closing a display with multiple attached layers waits once and releases each, with no remaining screen.
4. The same layer retained by multiple displays is detached from all of them.
5. The installer is idempotent, validates the original source pin and rejects unknown intervening modifications.

Both source and PS5 native workflow preflights execute this regression before building. Native PS5 compilation and on-console operation must be confirmed separately.

## Interpreting previous FC27 metrics

From pre-R349 PS5 logs, the longer match had 1,035 frame intervals above 50 ms and 950 of these occurred in five-second windows with a saturated producer GPU queue. The menu period instead recorded **zero producer queue pressure** and substantial accumulated guest BufferQueue dequeue time. The latter can represent intended 30 FPS pacing, not necessarily a deadlock. This patch addresses a demonstrated resource-lifetime defect in the buffer presentation lifecycle; it does **not** claim to eliminate the separate in-match burst-delivery issue.

Do not ask for another console trial until the R352 native build is green. A subsequent trial should first check whether control remapping can be completed without freezing, then check in-match intervals, buffer reuse and HUD/jersey fidelity at the user's usual **1440p, 1× game resolution**, without unnecessary shader-cache clearing.
