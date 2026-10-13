# R421 — PS5 cold-pipeline scheduling / frame-hitch reduction

Context: FC27 can remain near 30 FPS while suffering long individual frame stalls. The emulator's real-time frame path, texture cache ownership and presentation are not the same as average FPS; higher GPU throughput alone cannot resolve a pipeline compilation wait. No PS5 frame-time improvement is claimed without new console data.

## Identified concurrency

Under the native **EDEN_DEV_PROFILE / All-On** configuration, `fast_first_pipelines=true` builds a quickly usable, nonoptimized Vulkan graphics pipeline on the first-use `VkPipelineBuilder` worker, then schedules a full optimized rebuild on the separate `VkPipelineOptimize` worker. Before R421 these two workers could enter the same RADV driver concurrently, even when more first-use shaders were queued. `GetTotalPipelineWorkers` itself is conservatively constrained by the real kernel CPU affinity; changing its limit without verified firmware SMT topology would risk starving presentation and I/O.

R421 gives first-use graphics builds priority **without altering GPU submissions, descriptor cache locking, Vulkan object ownership, guest CPU mapping, or graphics output**:

- An atomic pending count tracks queued and running first-use graphics builds, but **only while `fast_first_pipelines` is enabled**.
- Each queued build decrements this count via `SCOPE_EXIT` on success, exception or early return; an unsuccessful queue insertion is also compensated.
- The separate `VkPipelineOptimize` callback yields in 2 ms sleeps, at most 48 ms per optimized pipeline, whenever newer graphics builds need CPU/driver time.
- This wait is **solely on the speculative background optimization thread** and **never delays frame presentation or the first-use graphics build**. After the bound expires the optimizer proceeds, avoiding indefinite starvation.
- The original `optimized_ready` publication and pipeline destructor's cancellation/finish guard remain intact. PS5 release builds default `fast_first_pipelines=false`, so there is no pending-counter work there.
- `tools/prepare-vulkan-port.py` is updated along with the active `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp`; verify byte-for-byte equivalence via `tools/check-vendored-vulkan-fork.py`.

This is a **hypothesis-driven frame-time contention reduction**. It cannot by itself repair guest texture coherence, HUD drops, shader correctness or display refresh pacing. Confirm with first-use/present/cache profiling before attributing stutter improvements to this change. Prefer one combined hardware validation after the next All-On build, retaining the current game/shader cache for a warm-frame comparison.

## CodeQL

GitHub created `.github/workflows/codeql.yml` during the manual transition from Default Setup to Advanced. That generated file had no `config-file`, scanning the vendor test fixtures twice and making results inconsistent. R421 removes this duplicate, retaining the existing `.github/workflows/codeql-advanced.yml` with `.github/codeql/codeql-config.yml` and all three languages. `tools/check-codeql-security-scope.py` now prevents accidentally reintroducing it. The 14 vendor-source alerts are scope exclusions, not claims of patched upstream code.

## R422 native qualification

After R421 source regression checks passed, run one PS5 **All-On native** build with the verified R421 shader-fairness code and R417 scheduler thread probes. Package a single candidate for a combined FC27 console test; no change to release graphics presets, per-game FPS policy or cached media.
