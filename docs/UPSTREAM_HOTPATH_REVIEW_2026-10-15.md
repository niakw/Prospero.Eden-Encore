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

## Inline guest memory upload barrier

The development bridge now also derives `engine_upload_deferred.cpp`.
Its `State::ProcessData(std::span<...>)` drains the title-owned pending
guest writes before either direct linear `AccelerateInlineToMemory` or
tiled `GpuGuestMemoryScoped` upload, rather than waiting until a later
draw or dispatch. This closes one ordering hole between DMA and renderer
command boundaries. The mock native-ON CMake generator now expects **six**
derived units, while the runtime defer gate and normal build remain OFF.

## Prevent partially replayed cache invalidations

Review of pinned `HandleRasterizerWrite` and active Vulkan `OnCPUWrite`
identified a critical asymmetry: buffer cache invalidation runs before
texture cache invalidation. If the buffer phase succeeds, it is unsafe to
queue the entire write only because the subsequent texture mutex is held.
The disabled native bridge therefore **only defers before acquiring the
buffer cache mutex**, before either cache has been modified. Once that
mutex is acquired, the existing full buffer, texture and pipeline sequence
runs synchronously, including the texture mutex wait. The host generation
contract requires exactly one enqueue call in the active derived method
and forbids texture mutex `try_lock` in that path.

## Serialize GPU-dirty writes across guest and GPU producers

The pinned `Core::GPUDirtyMemoryManager::Collect` performs its
`current.exchange(new_transform)` under `guard` but the initial
`current.load` and same-region CAS occur outside the mutex.
With a GPU replay producer collecting into the same guest core concurrently,
one producer may replace a newer current transform with a stale snapshot,
silently dropping dirty blocks before `Gather`. Atomic exchange alone
does **not** solve a compare-and-swap race.

The **developer-only**, default-OFF bridge now derives
`deferred-core/core/gpu_dirty_memory_manager.h` from the pinned original,
acquiring the existing `guard` for the entire `Collect` method, while
removing the obsolete nested lock. `Gather` already takes `guard`.
No changes to `TransformAddress`, dirty bit granularity, fences, or the
normal vendor header. Both `core` and `video_core` opt-in builds must see
the same shadow header; the memory-manager replay translation unit now
includes its complete type explicitly. The host contract checks the
derived source and is extended with concurrent collection stress.

## Guest-core attribution and GPU-thread exclusion

The development bridge now derives `memory-ps5-deferred.cpp` from the
native-specific, already patched core memory translation unit. It scopes
`ScopedGuestWriteOrigin` around the **actual** `HandleRasterizerWrite ->
GPU::OnCPUWrite` call, restoring the previous TLS origin on return.
`Tegra::MemoryManager::EnqueueDeferredCPUWrite` takes that explicit guest
core instead of guessing from `GetCurrentHostThreadID`. The opt-in Vulkan
branch may only defer when the guest origin is valid, the queue gate is
enabled and the call is not itself a replay. Ordinary GPU-worker writes
have no guest origin and remain on the original synchronous path.
The developer CMake fixture checks the resulting seventh translation
unit and the exact origin guard. The shipping mode stays OFF.

## GPU write queue-pressure gate (unsafe shortcut withdrawn)

The candidate's 8,192-entry cap was withdrawn before runtime activation.
Returning false at capacity would make a *later* CPU write run the blocking
cache path ahead of older writes still queued for GPU replay. That breaks
the intended cache/fence ordering guarantee. The queue instead requires a
true GPU-drain barrier with shutdown-aware backpressure before any cap
can be introduced safely. Until then it remains OFF in all native builds.

Nested guest-core origin scope and worker TLS isolation are independently
covered by the sanitizer test of the replay header.

## Post-store FIFO cancellation model (2026-10-16)

The inactive host queue now has `Cancel(Ticket)` and `CancelAndWake(Ticket, RequestGpu)`
for a reserved write that completed without changing guest backing RAM (for
example a failed conditional store). Cancellation marks the ordered reservation
as published/no-op, rather than erasing its sequence and overtaking preceding
writes. The GPU drain advances the completed watermark past canceled entries
but never calls the cache invalidation callback for them. Canceling an
unpublished FIFO head triggers the same shutdown-joined GPU wake contract as
publishing a completed ordinary store; failed wake callbacks poison the queue.

The sanitizer host test exercises a canceled middle write, FIFO replay around
that write, a canceled head releasing a published tail, and stale/duplicate
resolution rejection. The native bridge remains OFF and
`kNativePostStorePublicationReady = false`: a failed atomic compare first
READS guest memory, so its read/download ordering must be solved as well as
post-store cancellation. All store classes, GPU cache ownership, direct
JIT/fastmem accesses, title shutdown and DMA must be qualified before
activation. This commit does not address game frame stalls or FC27 HUD.

## Cancelled-tail coalescing correctness (2026-10-16)

A cancelled pending conditional write remains in FIFO as a published no-op.
Before this follow-up, the queue\'s eager same-core coalescing could merge a
later real write into that cancelled tail. Because replay skips cancelled
entries, the merged genuine cache invalidation was silently lost. Eager
coalescing now requires `!tail.cancelled` in addition to its old same-core,
same-region and overlap checks. A sanitizer regression reproduces a failed
conditional write followed by a genuine overlapping write and verifies that
exactly the latter reaches the invalidation callback. No native/runtime bridge
is enabled, and this is not a gameplay/HUD/performance fix.

## Bounded backpressure for future post-store producers (2026-10-16)

The source-only queue now exposes `ReserveOrdered` for a new write arriving
while 8,192 older writes remain unacknowledged. A plain `Reserve` rejection
must never allow the native producer to fall through to synchronous cache
invalidation ahead of older FIFO work. `ReserveOrdered` instead captures
the accepted watermark, asks the GPU owner to drain OUTSIDE queue locks,
waits through the older watermark, and retries its reservation. Scheduling
callbacks are joined during `Close`; callback failures poison the session
and release waiting readers/producers. An unpublished FIFO head still blocks
later replay until `PublishAndWake` or `CancelAndWake` resolves it.

The host sanitizer test covers synchronous drain after saturation, a blocked
unpublished head released by publication, and a failing scheduler callback.
This interface is NOT used by the inactive CMake bridge, and the native
runtime gate stays `false`. In particular, there is still no proven GPU
command scheduler wake, read-after-write fence, atomic publication or native
teardown integration. A caller must not invoke this helper while holding a
cache mutex or on the GPU consumer thread. No claim of FC27 improvement.

## Explicit failed GPU scheduling callbacks (2026-10-16)

The host-only request/wakeup contract now accepts callbacks returning either
`void` (an exception signals failure) or `bool` (a `false` result signals
rejection). Previously a boolean rejection was ignored. That could leave a
published head with no GPU wake or cause `ReserveOrdered` to wait forever after
backpressure without any GPU job being scheduled. Both code paths now treat
`false` as a thrown scheduling error and enter their existing session-poisoning
and waiter notification paths; successful `true` and existing `void` callbacks
retain their behavior. Source guards and sanitizer host tests cover both APIs,
including cancelled writes. The native bridge and its runtime gate remain OFF.

## Post-store transaction adapter, host-only (2026-10-16)

`headless/gpu_deferred_store_publication.h` now composes the existing
`ReserveOrdered`, `PublishAndWake` and `CancelAndWake` operations around
an explicit noexcept RAM store callback. It reserves a FIFO position before
executing the operation exactly once, publishes only after a real modification,
and cancels a failed conditional write. The compiler rejects potentially
throwing store callbacks to avoid a partially modified but unpublished
reservation. If the title is closed/poisoned before reservation, no RAM operation
is attempted. A failed publication after RAM mutation is a fatal caller error;
there is no safe synchronous fallback.

The source-backed sanitizer test checks pinned ordinary/scalar/zero/CAS/cache
maintenance call-site ordering and exercises the actual host queue with a
normal RAM store, failed CAS, cross-core publication gap, saturated queue,
invalid reservation and explicit rejected scheduler wake. It proves the
standalone protocol's mechanics, **not** native GPU coherence.

`headless/guest_write_deferred_bridge.cmake` does not call this adapter.
The current native derived `HandleRasterizerWrite` bridge still eagerly
enqueues before backing RAM store and the fail-closed
`kNativePostStorePublicationReady` remains `false`. A real integration must
separately classify cache maintenance (no subsequent store), synchronize
reads/atomic RMW before the attempted write, and cover direct fastmem/JIT
stores and renderer/fence shutdown ordering. No native build, release, console
test, or claim of FC27 improvement.

## Developer source write-intent classification (2026-10-16)

The CMake-derived developer-only guest memory source now marks five
pre-store callbacks: block copy, zero block, scalar write, regular exclusive,
and 128-bit exclusive. The two cache-maintenance callbacks (StoreDataCache
and FlushDataCache) have no following RAM store and remain unmarked.
The GPU memory manager and Vulkan candidate both require the scoped
StoreFollows intent and the existing guest-core origin. The native bridge
still uses unsafe eager publication, which remains blocked by the unchanged
kNativePostStorePublicationReady=false gate. Normal builds are unchanged.
CMake source derivation tests assert all five marked and two unmarked sites;
the host sanitizer verifies nested and cross-thread TLS restoration.

## Nested cache-maintenance context isolation (2026-10-16)

Unmarked cache-maintenance callbacks could inherit `StoreFollows` from an
enclosing guest write on the same thread. The developer-only derived guest
memory source now puts an explicit `ScopedGuestCacheMaintenanceIntent` around
both `StoreDataCache` and `FlushDataCache` rasterizer callbacks. The scope
forces `NoStore` even under nested guest writes and restores the previous
intent on exit. The CMake derivation refuses changed or missing two-site
anchors; the generated-source contract verifies two tagged maintenance
callbacks without converting either into a RAM store. The host sanitizer
tests Store -> Maintenance -> Store nesting and restoration. The native
runtime bridge remains gated off and normal native sources are unchanged.

## Full store lifetime scoping in derived guest memory (2026-10-16)

A source review revealed that the previous `StoreFollows` markers for scalar
`Write`, `WriteExclusive` and `WriteExclusive128` lived only inside the
`GetPointerImpl` rasterizer callback; they ended before the subsequent
`memcpy` or atomic compare-and-swap. The tracked `WriteBlockImpl` marker
also ended before `memcpy`. This prevented any later post-store publication
hook from sharing the scoped operation identity.

The derived developer-only guest memory source now keeps markers in scope
for the complete tracked `WriteBlockImpl` callback and at function scope
for scalar/exclusive writes. The unsafe WriteBlockImpl branch performs its
original memcpy without a marker. `ZeroBlock` already covered its memset,
and cache-maintenance callbacks still force `NoStore`.
The host-generated-source contract checks the marker lifetime relative to
actual memcpy/CAS lines and confirms the five paths are still distinct.

This is **not** post-store publication: no native ticket, wake callback,
GPU-to-CPU read fence, or conditional-store outcome has been wired. The
developer-only enqueue path remains blocked by
`kNativePostStorePublicationReady=false`; shipping Vulkan sources are
unchanged. No console build, release, gameplay test or performance claim.

## Host conditional guest-write read fence (2026-10-16)

The standalone `CommitConditionalAfterRead` helper now models the missing
precondition for CAS and 128-bit exclusive stores: an explicit, **blocking**
guest CPU-read synchronization callback must report `ReadBarrierResult::Complete`
before any reservation or atomic RAM access. A rejected/incomplete read leaves
the queue unchanged and does not execute the attempt. Once synchronized,
`CommitPostStore` reserves, executes exactly one noexcept CAS attempt, then
publishes the modified range or cancels an unsuccessful comparison.

The host sanitizer now covers earlier GPU invalidations drained before a
successful CAS, failure without invalidation, and an uncompleted download
that cannot run the CAS. The test proves operation ordering in the standalone
queue and callback model, not cache-coherent native CPU reads. Native callers
would still need a real GPU-to-CPU download fence **and** arbitration against
concurrent write producers between the read and reservation, all fastmem/JIT
write paths, correct GPU scheduling, and title-lifetime joins. The developer
CMake source still does not invoke this helper and
`kNativePostStorePublicationReady=false`. No FC27 gameplay effect.

## Reserve-before-read and producer serialization model (2026-10-16)

The earlier `CommitConditionalAfterRead` synchronized CPU RAM before reserving
its FIFO ticket. Under saturation, the later reservation could drain queued GPU
invalidations after the read fence, leaving the CAS with stale data. Now an
unpublished CAS ticket is reserved first, and the blocking read callback receives
only its predecessor watermark (sequence minus one). It must never wait for the
CAS's own unpublished ticket. A failed read cancels that ticket without running
the atomic operation; a successful read proceeds to CAS and publish/cancel.

`GuestStoreOrderGate` provides one address-space-local mutex for participating
guest CPU writers, held through reservation, read synchronization, backing RAM
store, resolution and GPU wake. A threaded ASan/UBSan fixture proves a competing
producer cannot interleave with a conditional read; a full-queue fixture proves
pressure drain precedes the read, and the unpublished ticket stays excluded.
The GPU replay worker must never acquire the gate or recursively call it.
Complete native correctness additionally requires all guest/JIT/fastmem
producers and readers to participate, a true GPU-to-CPU device fence, and
safe session-lifetime joins. The developer CMake bridge does NOT use this
gate and remains disabled via `kNativePostStorePublicationReady=false`.

## Fatal GPU-to-CPU read-barrier errors (2026-10-16)

Prior to this host-only correction, an incomplete or throwing CPU read fence
was treated as a benign failed CAS comparison: the reserved ticket could be
cancelled and acknowledged while the title queue continued accepting writes.
But an uncompleted GPU download makes guest RAM coherence unknown. The
new `Queue::FailClosed()` immediately marks the session failed, notifies
blocked waiters and disallows subsequent reservations. It does not falsely
acknowledge a reserved write, replay invalidations, or schedule GPU work.
`CommitConditionalAfterRead` now uses it when the blocking read returns
`ReadBarrierResult::Failed` or throws (preserving the original exception).
A correctly completed read followed by a CAS mismatch STILL cancels normally
and does not poison the title. Host sanitizer regressions cover both fatal
read outcomes, lack of subsequent writes, failed waiter results, and a
quiescent close/reset. This changes only the inactive model, not FC27.

## Zero predecessor for the first conditional store (2026-10-16)

A first CAS reservation produces a generation-tagged predecessor watermark
of sequence zero. Ordinary `Queue::WaitUntil` correctly rejects such a ticket,
but using it as the conditional-read barrier would incorrectly reject a valid
first CAS. The host-only `Queue::WaitForPredecessors` now accepts a zero
predecessor ONLY when it belongs to the current generation with a live
reservation and a healthy, open session. It uses ordinary `WaitUntil` for
nonzero predecessors and preserves close/failure wakeup behavior. Host
sanitizer tests cover the first CAS, prior replay, stale/foreign generation,
fatal session, and reset. The caller remains responsible for scheduling GPU
replay and completing the actual GPU-to-CPU device transfer. The native
bridge stays off; no gameplay behavior changes.
