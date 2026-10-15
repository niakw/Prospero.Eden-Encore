# October 15 GPU cache/JIT upstream review — source qualification only

Scope: `dev/ps5-sparse-jit`; no new native build and no physical console test.

## Evidence from supplied Oct 15 FC27 traces

Two independent session files were analyzed separately. Their maximum *cumulative*
buffer-cache lock waits per ~5-second window were 176.2 ms and 252.2 ms.
For texture-cache mutexes the maxima were 120.9 ms and 510.1 ms.
These are sums across completed waits, not one stalled render frame and
not a causal proof of pause-menu freeze. Latest per-session results had
323 and 466 displayed frames >50ms, respectively. Do not merge session
counter resets or equate presenter FPS with guest simulation progress.

## Current upstream disposition

- ProsperoEden [#187](https://github.com/blackbearreloaded/ProsperoEden/commit/f1b83c21d157):
  high-priority, **not completely integrated**. This change includes much
  more than buffer lock elision: deferred guest writes, GPU-side replay before
  dependent commands, GPU-modified/fence exceptions, and core-scoped queues.
  Importing only the early deferred-write version would risk stale HUD/terrain
  textures. The `buffer_write_ahead.h` subcomponent is separately staged:
  it marks registered buffer pages only under an existing cache lock, stops
  at unregistered or GPU-owned pages, and is **OFF by default** (`cpu_write_ahead=0`).
  Offline sanitizer tests do not prove any speedup. The complete deferral
  semantics are not enabled or claimed.
- ProsperoEden [#188](https://github.com/blackbearreloaded/ProsperoEden/commit/b94216347b9a):
  **not integrated**. Direct JIT page table + page reuse need matching sparse
  commit order, page invalidation, new Dynarmic IR opcodes and host memory
  differential tests. Existing sparse JIT is not an equivalent implementation.
- ProsperoEden [#185](https://github.com/blackbearreloaded/ProsperoEden/commit/99e381ed29f7):
  **not integrated**. Dirty block-row texture refresh needs per-image, per-cache
  lifetime accounting and same-snapshot unswizzle verification; an earlier
  upstream variant left stale page state across title switches.
- ProsperoEden [#179](https://github.com/blackbearreloaded/ProsperoEden/commit/9c898feb254a):
  already covered by `headless/jit-compile-batch.inc` line 21.
- ProsperoEden [#183](https://github.com/blackbearreloaded/ProsperoEden/commit/a13e040cd502):
  equivalent 1.5ms guest VI composition delay already present.
- ProsperoEden [#181](https://github.com/blackbearreloaded/ProsperoEden/commit/6b4d27ff3352):
  256-entry native GPU queue already present.
- ProsperoEden [#178](https://github.com/blackbearreloaded/ProsperoEden/commit/96d8f4a8e852):
  native `video_core` ThinLTO + Zen2 already present.

## Stop conditions

No more user console trials for these source checks. Do not enable the
new write-ahead optimization on a release from host contracts alone.
Prioritize full write/read/fence ordering proof for #187, then independent
JIT memory differential verification for #188, then per-texture lifecycle
checks for #185. CI success proves source contracts, not FC27 gameplay.

## Deferred write pipeline gate (follow-up)

A standalone `headless/gpu_deferred_write_queue.h` now models per-core deferred
ranges, same-page-only merging, release/acquire handoff, GPU owner replay
without holding queue mutexes, and explicit shutdown quiescence. The
`tools/check-gpu-deferred-queue-host.py` sanitizer fixture covers four
concurrent producers (1,280 distinct writes), invalid/overflow ranges,
cross-page boundaries and a simulated GPU-modified fence case.

**This is deliberately NOT wired to OnCPUWrite, FlushCaching, or the DMA
pusher.** The test validates queue ownership mechanics but cannot prove that
real GPU cache invalidation, guest dirty range collection, guest submits and
GPU fences remain ordered. Runtime behavior therefore stays unchanged; a
console test now would provide no useful signal. The next engineering gate is
a source-level native integration whose actual guest cache and HLE ordering
passes host validation before any activation.

## GPU-dirty replay correctness gate (follow-up)

The pinned `core/gpu_dirty_memory_manager.h` uses `DEVICE_PAGEBITS-1`
(2,048-byte) transform regions and 64-byte alignment. Passing an arbitrary
queued guest write directly to `Collect` can cross one or several transform
regions and violate its bit-mask preconditions. `headless/gpu_deferred_replay.h`
slices each GPU-owned replay at the exact 2-KiB boundary while preserving
the original CPU-core index; regular guest writes must still go through
texture/shader invalidation but do not create false GPUDirty entries.
`tools/check-gpu-deferred-replay-host.py` runs sanitizer-backed boundary,
large-span, core-attribution and reentrant-drain checks.

**Not yet connected to actual GPU dispatch or caches**. A native runtime
bridge still requires source and lifecycle validation across
`HandleRasterizerWrite`, `OnCPUWrite`, `FlushCaching`, DMA and fences.
No PS5 test is warranted until that integration is qualified.

## Queue coalescing narrowed to the GPU-dirty transform

A previously staged queue could merge disjoint guest writes inside a 4-KiB
page. The actual GPU dirty collector tracks 2-KiB regions, so an overly
wide merged range could cause false GPU-owned dirty marks. Coalescing now
requires both a single 2-KiB region AND overlapping/touching spans;
disjoint spans are kept separate. The host sanitizer fixture checks both
cross-region adjacency and unwritten gaps within a region.

This conservative policy is source-only; the full #187 runtime path
remains intentionally disconnected until ordered GPU/DMA/fence replay is
verified, including on title teardown.

## Cross-core FIFO requirement and correction

The first host queue drained all core 0 writes before core 1-3 writes.
That could reorder CPU invalidations across independent core producers
and make a GPU cache snapshot inconsistent. The new session-owned FIFO
assigns one mutex-protected enqueue order across all cores and stores
the original core on each range. Replaying never holds the queue mutex;
a callback may enqueue more work for a subsequent batch. Coalescing
only applies to adjacent/overlapping ranges from the **same core**
in the **same 2-KiB dirty region**, and only when consecutive in FIFO.
The sanitizer fixture asserts cross-core [2,0,3,1] ordering and prohibits
a coalescing shortcut across intervening core writes.

This guarantees enqueue order only. It does NOT prove the memory visibility
order between guest writes and GPU command execution; native enablement
remains blocked on DMA/fence and title-lifecycle contracts.

## Native Vulkan bridge (source integration; strictly OFF)

A guarded `headless/guest_write_deferred_bridge.cmake` is included by the
native CMake port, with `EDEN_GUEST_WRITE_BRIDGE_DEV=OFF` by default. Only a
native Vulkan development profile can select the CMake path. Its derived
source translations (immutable upstream + immutable maintained Vulkan files)
pair the title-owned `Tegra::MemoryManager` queue with Vulkan
`RasterizerVulkan::OnCPUWrite`, `MemoryManager::FlushCaching`, GPU-dirty
per-core collection and command boundaries at start/end of DMA dispatch,
Maxwell DMA and Kepler compute launches. Reentrant GPU replay suppresses
its own enqueue through a thread-local scope.

**Not yet production-ready.** `cpu_write_defer` remains false with no
activation through settings. Host CI tests CMake parsing in OFF mode and
pinned-source anchors, but no native SDK build has compiled the opt-in branch.
Even a successful native compilation would not yet prove callback ordering,
GPU cache synchronization, shutdown quiescence or stable game HUD. No
console test is justified.
