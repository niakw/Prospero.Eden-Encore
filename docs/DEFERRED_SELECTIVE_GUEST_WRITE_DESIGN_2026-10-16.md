# Selective tracked-page guest writes — design, not an activation approval

Source branch: `dev/ps5-sparse-jit`. Baseline: `3cf279f`; extended source inventory: `0f96500`.

**Decision:** Keep `kNativePostStorePublicationReady=false`. Nothing in this
document changes native execution, GPU scheduling, releases, or gameplay.
The #187 deferred bridge remains an unqualified candidate.

## What the current source actually provides

1. `common/page_table.h`: `MarkRasterizerCached()` atomically sets
   `marked` and the `RasterizerCachedMemory` type. `ExtractPointer()`
   returns zero for marked entries unless `ignore_marked=true`.
2. `core/memory.cpp::RasterizerMarkRegionCached()`: when a region becomes
   GPU-cached, `host_buffer->Protect(...)` grants **no write permission**
   to its fastmem mapping. The read permission depends on the reactive
   flushing setting. Ordinary pages retain a direct write path.
3. `core/memory.cpp::GetPointerImpl()`: marked regions take the
   `RasterizerCachedMemory` branch and invoke `on_rasterizer`. Scalar
   `Write<T>()` and conditional writes pass `HandleRasterizerWrite()`
   as that callback.
4. `core/arm/dynarmic/arm_dynarmic_{32,64}.cpp`: both JIT configurations
   expose a direct page table and optional fastmem, but also install
   `MemoryWrite*` callbacks. The exact `page_table_marked_bit=0`
   behavior in the *pinned Dynarmic backend* must be demonstrated with
   generated-code/runtime evidence, not inferred just from the
   `PageEntryData::ExtractPointer()` C++ helper.
5. `core/guest_memory.h`: a mutable `GuestMemory` may hold a direct
   `GetSpan()` alias. This goes through `GetPointerSilent()`, which can
   obtain the underlying pointer to a marked page. `GuestMemoryScoped`
   invalidates after in-place writes; this is not yet an ordered
   reserve/store/publish protocol, and alias lifetime must be accounted for.
6. `vendor/sources/eden/CMakeLists.txt` sets `HAS_NCE` only on
   ARM64 Linux/Android; `core/CMakeLists.txt` includes NCE only when that
   flag is set. NCE is therefore **not** an active x86-64 native producer
   under this build selection. This does not qualify NCE for ARM64 ports.

Source anchoring is checked by
`tools/check-deferred-native-access-coverage.py`. A green result is
**a correctly blocked activation**, not a behavioral proof.

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
| A32/A64 cached page through page-table JIT | Execute real JIT stores on a dynamically marked page and prove callback/slow path | Not demonstrated |
| A32/A64 cached page through fastmem | Verify write-protect trap/fallback for normal, vector, atomic and boundary-crossing stores | Not demonstrated |
| Dynamic page transition | Prove no untracked in-flight store survives a transition into GPU-tracked state; inspect ordering around protection and page marking | Not demonstrated |
| Writable `GuestMemory` aliases | Classify live users of mutable spans; guarantee lifetime + post-store notification or prohibit direct alias on tracked pages | Not demonstrated |
| Conditional/atomic write | Device-to-CPU read fence, FIFO predecessor wait, CAS success/failure, exactly-once outcome | Host protocol modeled, not joined to native code |
| GPU work and dirty collection | Confirm no GPU consumer overtakes unpublished writes and that cache invalidation/dirty collection are properly ordered | Not demonstrated |
| x86-64 build NCE applicability | Conditional compilation in CMake | Excluded under current settings |
| Performance | Actual host-run JIT measured in both untracked and tracked-page paths, with generated-code/fault counts and slowdown | Not measured |

### Proposed implementation boundary

Keep fastmem and page-table access active for **untracked pages**. Use
the existing page-marking / protection machinery to select only
GPU-tracked pages for a prospective callback-based store transaction.
No global JIT-wide mutex, no blanket `fastmem_pointer=nullopt`, and
no all-memory callback conversion. Pin the exact Dynarmic backend
semantics before code changes; if the backend does not reliably route
marked pages, this architecture is invalid as stated and must be revised.

Introduce no deferred native write until the producer-side post-store
publication and consumer-side fence are part of the **same proven path**.
Mutable writable spans need an explicit separate solution: a raw pointer
cannot retroactively acquire a store ticket after users have changed its
contents.

### Measurement without another console test

On a host that can build the pinned JIT, exercise a synthetic guest
program that writes untracked and dynamically GPU-tracked pages.
For each memory mode, count callback entries, protected-page faults,
successful conditional stores, failed conditionals and stores observed
by the consumer. Record store throughput and p50/p95/p99 latency,
both with and without GPU-cache contention, and compare against the
existing non-deferred implementation. Do not invent performance claims
from queue-only benchmarks.

If the proof shows an unobservable tracked-page store, a deadlock,
out-of-order consumer, or an unbounded slowdown, stop: the bridge
cannot be activated. FC27 freezes, HUD rendering defects and stutters
remain independent open problems until game-level evidence exists.

## Current follow-up

1. Identify the exact Dynarmic source/version used by this fork and
   prove marked page handling at generated-store level.
2. Inventory actual mutable `GuestMemory` call sites and ownership.
3. Only then prototype tracked-store post-publication, behind an
   opt-in host-only gate with the native gate still false.

No console build, release or new gameplay test follows from this design.
