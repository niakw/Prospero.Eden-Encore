# Selective tracked-page guest writes — design, not an activation approval

Source branch: `dev/ps5-sparse-jit`. Baseline: `3cf279f`; selective-source checks added in `0f96500` and `0e732a3`.

**Decision:** Keep `kNativePostStorePublicationReady=false`. Nothing in this
document changes native execution, GPU scheduling, releases, or gameplay.
The #187 deferred bridge remains an unqualified candidate.

## What the current source actually provides

1. `common/page_table.h`: `MarkRasterizerCached()` atomically sets
   `marked` and the `RasterizerCachedMemory` type. `ExtractPointer()`
   returns zero for marked entries unless `ignore_marked=true`.
2. `core/memory.cpp::RasterizerMarkRegionCached()`: when a region becomes
   GPU-cached, `host_buffer->Protect(...)` removes direct fastmem **write access**.
   In this x86-64 native port, `EDEN_A32_FASTMEM=ON` changes
   `HostMemory::Protect()` into updates to a **per-guest-page checked access
   byte map**, not an OS `mprotect()` call. The JIT checks the blocked-write bit
   before accessing the A32 fastmem window. The read permission depends on
   reactive flushing. Ordinary pages retain their direct path. A64 native
   application processes are excluded from the A32 fastmem arena in the
   CMake-derived `memory.cpp` (`!process.Is64Bit()` condition).
3. `core/memory.cpp::GetPointerImpl()`: marked regions take the
   `RasterizerCachedMemory` branch and invoke `on_rasterizer`. Scalar
   `Write<T>()` and conditional writes pass `HandleRasterizerWrite()`
   as that callback.
4. `core/arm/dynarmic/arm_dynarmic_{32,64}.cpp` installs
   `page_table_marked_bit=0` and `MemoryWrite*` callbacks. The actual
   `dynarmic/backend/x64/emit_x64_memory.h` lookup checks the marked
   bit and branches to `abort`, where `emit_x64_memory.cpp.inc` calls the
   memory-write fallback. `headless/CMakeLists.txt` keeps this behavior
   when generating its optimized bit-zero `test/jnz` check for A32/A64.
   `headless/checked-fastmem.cmake` routes blocked A32 fastmem stores
   (including scalar SIMD paths) to a checked page-table lookup and then
   callbacks when the page is marked. Native A32 exclusive fastmem uses
   a separately routed page-table path; `EDEN_INLINE_EXCLUSIVES` defaults
   OFF because forced inline exclusives previously exhibited a hardware
   soft-hang. This is real generated-store **source** evidence, but not a
   native deferred-publication implementation.
5. `core/guest_memory.h`: a mutable `GuestMemory` may hold a direct
   `GetSpan()` alias. This goes through `GetPointerSilent()`, which can
   obtain the underlying pointer to a marked page. `GuestMemoryScoped`
   invalidates after in-place writes; this is not yet an ordered
   reserve/store/publish protocol, and alias lifetime must be accounted for.
6. `vendor/sources/eden/CMakeLists.txt` sets `HAS_NCE` only on
   ARM64 Linux/Android; `core/CMakeLists.txt` includes NCE only when that
   flag is set. NCE is therefore **not** an active x86-64 native producer
   under this build selection. This does not qualify NCE for ARM64 ports.

7. `headless/memory_check.cpp` already runs actual synthetic A32 and
   A64 JIT instructions. Its `Check<false>()` / `Check<true>()` paths
   assert callbacks on marked pages; `CheckFastmemA32()` covers tracked,
   unaliased, cross-page, scalar SIMD and fallback cases; and
   `StressFastmemA32()` concurrently changes page permissions and marking
   while JIT guest workers execute and checks the final backing RAM.
   `BenchFastmemA32()` already offers table-versus-checked-fastmem host
   benchmarks, but no new timing measurements were made in this audit.
   These are pre-existing test **implementations**; their presence does
   not assert that this exact commit has executed/passed them.

Source anchors (including the actual JIT emitter, A32 access-byte guard,
and pre-existing host JIT harness) are checked by
`tools/check-deferred-native-access-coverage.py`. A green **source preflight**
means its assumptions still match and the bridge is correctly blocked; it
does not prove GPU/CPU synchronization or runtime JIT correctness.

## Concrete scoped producers and first-tracking hazard

The `GuestMemoryFlags` type also does **not** enforce read-only
access at compile time: `GuestMemory<..., SafeRead>` still offers
`T* data()`, mutable `operator[]` and a mutable `std::span<T>` from
`Read()`. Therefore a search restricted to `FLAGS & Write` cannot
prove the absence of in-place modifications through nominally read-only
buffers. This is a possible API-level escape, **not** a demonstrated
write at every read-only call site. Qualify actual mutating uses before
counting CPU-producer coverage as complete.

The scoped template in `core/guest_memory.h` is not tied to one
producer domain. Actual writable GPU-side instantiations are present:

| Consumer | Scoped write flag | Ownership / cache path |
| --- | --- | --- |
| `video_core/engines/engine_upload.cpp` | `SafeReadCachedWrite` | GPU upload swizzle; contiguous mapped span may be modified in place |
| `video_core/engines/maxwell_dma.cpp` | `SafeReadCachedWrite`, `UnsafeReadCachedWrite` | GPU DMA linear/tiled copies; explicit `SetAddressAndSize()` changes the eventual destination in some paths |
| `video_core/engines/sw_blitter/blitter.cpp` | `SafeReadWrite` | GPU software blit into a writable destination |
| `video_core/host1x/vic.cpp` | `SafeWrite` | GPU video processing output |

All these aliases use `Tegra::MemoryManager` through
`GpuGuestMemoryScoped` and are **GPU engine producers**, not proof of
an uncaptured CPU/JIT store. `Tegra::MemoryManager::GetSpan()`
returns its mapped backing pointer via `memory.GetSpan()`.
With a mapped span, `GuestMemoryScoped` performs a **post-write
`InvalidateRegion()`**, not an ordered CPU reserve/store/publish.
Fallback copies may instead use `WriteBlockCached()`, which writes
through to RAM and records the invalidate in `accumulator`; its
`FlushCaching()` drains the accumulator. The native bridge must
preserve GPU command order and cache visibility; it must **not**
automatically classify these GPU-engine writes as CPU transaction
producers. The inventory is not exhaustive for CPU-side writable
`GuestMemory` users; further call-site qualification is required.

The more serious native page-transition gap is independent of the
above GPU engine aliases: `RasterizerMarkRegionCached()` calls
`host_buffer->Protect()` **before** it marks the PTE. The A32
`HostMemory::Protect()` function updates the checked access map
under its own mutex, but a JIT instruction tests that map without
taking the mutex. A previously passed guard can therefore proceed
with a direct store while protection/marking is happening. This
source sequence does not contain an **in-flight JIT writer quiescence
barrier** before the page becomes GPU-visible. The pre-existing
`StressFastmemA32()` verifies eventual RAM values under flips; it
does not assert a per-write callback/notification happened before
the GPU first used a newly cached page.

Before #187 can be activated, prove a transition protocol satisfying
both invariants: (a) no untracked direct CPU write still races when a
page becomes GPU-tracked, and (b) every later tracked write is ordered
against the GPU consumer. Avoid broad per-instruction locking. A
candidate epoch/safepoint scheme must have measured cost and a
concrete memory-model proof before being implemented in native code.

## Conditional stores: an existing read fence is not a CAS fence

`core/memory.cpp::WriteExclusive<T>()` and `WriteExclusive128()`
call `HandleRasterizerWrite()` **before**
`Common::AtomicCompareAndSwap()`, whether or not the comparison
succeeds. Neither function invokes `HandleRasterizerDownload()` in
its atomic path. Separately, `video_core/gpu.cpp::OnCPURead()`
already has an actual GPU read/download synchronization sequence
(`RequestSyncOperation`, `TickGPU`, `WaitForSyncOperation`).

This does **not** demonstrate that native CAS operations currently
corrupt game data. It does establish why moving the existing eager
notification into the deferred queue would be wrong: an unsuccessful
CAS is not a modified RAM store, and a future deferred CAS must
synchronize its expected-value read against any GPU-resident data
before the atomic attempt. `CommitConditionalAfterRead()` models
this host-side but is not attached to the native CPU/JIT path.
For the eventual bridge, reserve before the read fence, wait for
predecessors only, complete the GPU device transfer, attempt CAS
exactly once, then `PublishAndWake()` on success or
`CancelAndWake()` on failure. Keep the native gate closed.

## Required transaction for an intercepted GPU-tracked store

```text
CPU/JIT hits tracked page
  -> confirm actual callback/fault routing (including exclusives)
  -> finish GPU-to-CPU device read/download fence, if required
  -> reserve ordered producer ticket before modifying backing RAM
  -> execute the host RAM store exactly once (or report CAS failure)
  -> publish after successful modification, otherwise cancel
  -> GPU consumer drains only published tickets before dependent work
  -> GPU cache invalidation and dirty collection run in original order
```

There must be no GPU-cache mutex held while reserving, waiting for a
device fence, or publishing. A reserved-but-unpublished ticket must
prevent its consumer from passing the corresponding read hazard without
deadlocking the CPU producer. A failed publication is terminal for that
title/session, not permission to replay the store or fall back to an
unordered write. Cross-page stores and A64 128-bit stores need a
transaction covering the complete affected range.

The **linearization point** for a modified RAM store is its successful
post-store publication. A false CAS/failed conditional store cancels
the ticket. Do not enqueue a cache-maintenance operation as though it
had modified RAM; classify it separately.

The current `HandleRasterizerWrite()` calls the rasterizer *before*
the underlying `memcpy`/CAS. The developer bridge currently enqueues
at that earlier point; therefore a consumer could observe a notification
before the CPU has stored the bytes. Merely switching the queue's
notification ordering does not repair missing producers.

## Qualification gates: all required, none currently met as a set

| Boundary | Minimum evidence | Current status |
| --- | --- | --- |
| A32/A64 cached page through page-table JIT | Generated lookup routes marked stores to callbacks; verify current host execution results and temporal ordering | Source and pre-existing synthetic JIT test coverage; not rerun here |
| A32 checked fastmem (A64 native has no arena) | Access-byte map selects direct/fallback; test marked, vector, crossing and exclusive cases | Source and pre-existing A32 host JIT test coverage; no new execution claim |
| Dynamic page transition | Prove no untracked in-flight store can overlap first GPU-cache use; inspect ordering of access-byte protection and PTE marking | Existing A32 concurrent stress test checks backing values; no GPU coherency proof |
| Writable `GuestMemory` aliases | Distinguish GPU engine aliases from CPU-side producers; preserve post-write invalidation and FIFO visibility | GPU DMA/upload/blitter/VIC owners identified, CPU-side call sites not exhausted |
| Conditional/atomic write | GPU-device read fence, predecessor wait, CAS success/failure and exactly-once publication | Native CAS pre-notifies and has no download call in its atomic path; host protocol only |
| GPU work and dirty collection | Confirm no GPU consumer overtakes unpublished writes and that cache invalidation/dirty collection are properly ordered | Not demonstrated |
| x86-64 build NCE applicability | Conditional compilation in CMake | Excluded under current settings |
| Performance | Compare host-run JIT on tracked/untracked pages and under contention | Existing `--fastmem-bench` for table vs checked A32; no new measurements or GPU contention profile |

### Proposed implementation boundary

Keep fastmem and page-table access active for **untracked pages**. Use
the existing page-marking / protection machinery to select only
GPU-tracked pages for a prospective callback-based store transaction.
No global JIT-wide mutex, no blanket `fastmem_pointer=nullopt`, and
no all-memory callback conversion. The pinned x64 Dynarmic backend and
native-derived port do have marked-page fallback mechanisms; the open
task is verifying their interaction with a post-store GPU transaction,
not rediscovering whether marked pages can reach callbacks.

Introduce no deferred native write until the producer-side post-store
publication and consumer-side fence are part of the **same proven path**.
Mutable writable spans need an explicit separate solution: a raw pointer
cannot retroactively acquire a store ticket after users have changed its
contents.

### Measurement without another console test

Reuse `headless/memory_check.cpp` instead of creating another synthetic
JIT harness: the default test already exercises real A32/A64 marked
page-table stores plus A32 checked-fastmem and concurrent page flips.
Its `--fastmem-bench` mode reports `FASTMEM_BENCH kind=... mode=table/checked
ns_per_iteration=...`; preserve that baseline. If a future developer-only
host transaction prototype is built, add the missing *post-store*
publication/consumer visibility/fence assertions on tracked pages and
compare with existing non-deferred numbers, with p50/p95/p99 under GPU
contention. Never infer actual runtime wins from source coverage or
queue-only tests.

If the proof shows an unobservable tracked-page store, a deadlock,
out-of-order consumer, or an unbounded slowdown, stop: the bridge
cannot be activated. FC27 freezes, HUD rendering defects and stutters
remain independent open problems until game-level evidence exists.

## Current follow-up

1. Reuse the pinned x64 JIT emitter and `memory_check.cpp` as the
   actual interception baseline; do **not** disable direct memory broadly.
2. Inventory actual mutable `GuestMemory` call sites and their lifetime,
   and determine whether marked-page aliases bypass the write transaction.
3. Prove the first-tracking transition excludes in-flight direct stores;
   a successful A32 backing-value stress test alone does not establish
   GPU-visible ordering.
4. Only then prototype tracked-store post-publication plus the actual
   GPU-to-CPU device read fence, behind a host-only gate, keeping the
   native gate false.

No console build, release or new gameplay test follows from this design.
