# Deferred guest writes: CPU-read and drain-barrier gate

Status: **BLOCKED / not eligible for activation**. Scope: `dev/ps5-sparse-jit`.
Source audit only: no console test, no native SDK compilation, no FPS claim.
The production switch `cpu_write_defer` stays OFF.

## Verified source paths

1. `Core::Memory::Impl::HandleRasterizerWrite` invokes `system.GPU().OnCPUWrite(address, size)`.
   The opt-in bridge preserves `ScopedGuestWriteOrigin` while the Vulkan implementation may enqueue
   the whole invalidation **before** modifying either cache (on buffer mutex contention).
   Guest code may then write the backing RAM immediately.
2. `Core::Memory::Impl::HandleRasterizerDownload` first consults the per-core
   `rasterizer_read_areas` cache. A covered read returns without calling `GPU::OnCPURead`.
3. `GPU::Impl::OnCPURead` consults `RasterizerVulkan::GetFlushArea`. For a
   preemptive area it returns before queuing any GPU request. Otherwise it
   requests `RasterizerVulkan::FlushRegion`, waits on a GPU sync fence, and returns.
   That request does **not** call the deferred queue's `FlushCaching`.
4. The opt-in `Tegra::MemoryManager::FlushCaching` drains queued writes at
   selected GPU commands/engines, but neither CPU-read bypass above has an
   explicit outstanding-write barrier. A read may therefore pass without
   acknowledging an earlier deferred cache invalidation.

Sources:
- `vendor/sources/eden/src/core/memory.cpp`: `HandleRasterizerDownload`, `HandleRasterizerWrite`
- `vendor/sources/eden/src/video_core/gpu.cpp`: `GPU::Impl::OnCPURead`, `RequestSyncOperation`
- `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`: `GetFlushArea`, `FlushRegion`, `OnCPUWrite`
- `headless/guest_write_deferred_bridge.cmake`: opt-in queue, rasterizer and engine wiring
- `headless/gpu_deferred_write_queue.h`: FIFO, unbounded outstanding entries

## Correctness failure mode (not a reproduced game bug)

Deferred invalidation A is accepted while a cache mutex is held. The CPU
subsequently accesses a GPU-tracked range before the GPU owner replays A.
A cached read-area hit can bypass `OnCPURead` entirely; even a non-cached
read can return via `GetFlushArea`'s preemptive shortcut or flush without
draining A first. GPU cache state can therefore lag CPU backing RAM and
read/download ordering is not established. This is a **source-level
counterexample**, not proof that it causes a particular freeze or HUD issue.

## Host-only progress: numbered replay watermark (15 October 2026)

The disabled candidate `headless/gpu_deferred_write_queue.h` now exposes:

- `EnqueueTracked`: monotonically numbered accepted writes, including contiguous
  same-core coalescing, with a per-session total enqueue order.
- `DrainThrough` / `Drain`: GPU-owner callbacks run without the queue mutex;
  the drain is bounded to a captured sequence, even if other producers
  continuously enqueue. A later enqueue from inside a callback remains pending
  for a subsequent drain.
- `CompletedSequence` and `WaitUntil`: a CPU-side waiter can wait for a
  previously accepted ticket. Completion is published only after the
  corresponding replay callback returns. `Close` wakes outstanding readers,
  and rejected writes must never be silently acknowledged.
- `Pending` includes in-flight callbacks, avoiding a false empty indication
  while an older write is being replayed.
- A separate mutex serializes GPU consumers: a second drain waits for the
  earlier replay to finish, then processes its own requested watermark;
  it cannot skip dependent invalidations. Recursive drain of the same queue
  on the owning thread fails fast rather than silently bypassing replay.
  Native lock-order and reentrancy must still be audited before enablement.

Targeted host-only Clang/ASan/UBSan compilation and execution passed (four
producers, 1,280 writes, coalescing, completion wait, shutdown cancellation,
and serialized concurrent replay owners (25 local stress iterations)).
This is **not** a native SDK build and **does not** establish renderer correctness.

**Still missing and blocking:** no real `HandleRasterizerDownload`,
`GPU::OnCPURead` or cache read-area hook uses these tickets, nor does the GPU
command processor schedule a drain on behalf of a waiting reader. `Close`
is not wired into the real title lifecycle. `WaitUntil` without first
scheduling the GPU owner can deadlock, so it must NOT be inserted into the
CPU-read path by itself. There is no safe queue-cap backpressure yet.

A callback completion watermark is NOT a Vulkan device/submit fence. Moreover,
`HandleRasterizerWrite` may enqueue before the actual backing-memory
`memcpy` on the producer returns: native integration must prove the required
CPU payload publication/order relative to GPU reads, not merely mark the
invalidation callback complete. GPU dirty/fence handling and texture
validity remain separate proof obligations.

## Finite replay snapshot: race corrected (source-only)

The earlier `DrainThrough` took a sequence target but repeatedly swapped and
processed the *entire* incoming queue. In the interval between observing the
sequence and acquiring the queue mutex, another producer could append work;
the loop also risked continuing indefinitely under reentrant or constant
concurrent producer pressure.

The corrected code captures **one FIFO snapshot under the queue mutex**,
releases that mutex, then runs all callbacks before publishing the completion
of the last snapshotted entry. New writes after this snapshot remain for a
later GPU-owner boundary. Multiple GPU-owner drainers remain serialized by
`consumer_mutex_`. A ticket passed to `DrainThrough` is therefore a
**minimum completion target**, not an exact maximum: newer entries accepted
*before* the snapshot may be included. That is intentional and host-tested.

A targeted C++20 host reproducer with Clang 17, ASan and UBSan completed 30
iterations covering continual callback enqueues (400 later writes), reader
completion, cancellation at session close and two serialized drain owners.
The repository's `check-gpu-deferred-queue-host.py` now includes an explicit
regression for this bounded snapshot behavior. These checks do not validate
native GPU timing or cache coherency.

## Pre-store publication race: still BLOCKED

The pinned `core/memory.cpp` executes `HandleRasterizerWrite` **before**
writing guest backing memory in `WriteBlockImpl` (tracked `memcpy`),
`ZeroBlock` (`memset`) and the scalar `Write<T>` path. In the disabled
bridge, `HandleRasterizerWrite` may enqueue and return immediately. A GPU
consumer could then replay the cache invalidation, acknowledge the sequence,
and consume RAM **before** the producer completes its actual store. Sequence
tracking cannot repair this fundamental ordering hole.

The bridge therefore also needs a post-store publication protocol that
covers every relevant scalar, exclusive, bulk, zeroing and fastmem write
path, with correct shutdown handling and memory ordering. No consumer may
consider an accepted write replayable until its source payload is published.
The current source-contract test pins the known pre-store ordering as a
**negative gate**, rather than pretending it is safe. Do NOT enable the
bridge or add a GPU read wait solely from the current watermark APIs.

## Two-phase write-publication prototype (host only)

A source-only `Queue::Reserve(core, address, size)` now assigns a FIFO position
**before** the producer changes guest RAM. The returned ticket contains both
a monotonically increasing write sequence and a session generation. Only
`Queue::Publish(ticket)`, called **after the actual guest store**, marks that
entry eligible for GPU-owner replay.

`DrainThrough` snapshots at most the contiguous **published FIFO prefix**;
an earlier unpublished reservation blocks later ready entries even when they
come from a different guest core. Published entries ahead of the first gap
may drain; entries after the gap cannot overtake it. `Publish` releases the
same mutex that a later GPU consumer acquires to snapshot ready work, giving
a C++ happens-before edge from the completed CPU store to the callback.
It **does not** establish a Vulkan completion fence, guest JIT fastmem
publication, or device visibility beyond the host-level callback.

Stale session-generation tickets cannot publish or wait successfully after
`ResetAfterQuiescence`; `Close` prevents new reservations and releases
waiters. A missed `Publish` intentionally leaves an unresolved FIFO entry
until shutdown instead of silently replaying uncommitted RAM.

**Native opt-in bridge is still NOT wired to this protocol.** Its generated
`MemoryManager::EnqueueDeferredCPUWrite` still calls the eager
`deferred_cpu_write_queue.Enqueue` before the guest's actual store.
A fail-closed host source test pins this mismatch; it must be replaced with
a real post-store integration across scalar, exclusive, zero, block and JIT
fastmem write paths before `cpu_write_defer` could ever be enabled.
No console build or on-device test is justified by this host prototype.

**Remaining liveness problem:** native `GPU::OnCPURead` and
`HandleRasterizerDownload` can bypass queue drainage. A read waiting
for a reserved ticket also requires scheduling the GPU owner after publish;
there is no such native orchestration yet. Native shutdown/wakeup and
queue pressure constraints remain unqualified.

## Native runtime interlock and write-site inventory (15 October 2026)

The experimental source generation previously retained a dangerous escape
hatch: even with the default switch OFF, a future runtime toggle could have
entered the legacy eager `Enqueue` before the guest's actual `memcpy` or
`memset` completed. The native bridge now checks the compile-time
`kNativePostStorePublicationReady = false` guard at BOTH the candidate
rasterizer path and the enqueue helper. With the guard false, a cache-mutex
contention uses the original blocking path rather than deferring it.
This protects the currently unqualified opt-in developer configuration even
if someone accidentally changes `cpu_write_defer` at runtime. Flipping the
guard is prohibited until the checklist below is met.

The pinned `core/memory.cpp` has **eight** `HandleRasterizerWrite`
references (seven call sites plus the definition):

| Write source | Current action | Publication risk |
| --- | --- | --- |
| `WriteBlockImpl` | Callback before tracked `memcpy` | Pre-store |
| `ZeroBlock` | Callback before tracked `memset` | Pre-store |
| Scalar `Write<T>` | Callback during pointer lookup, then `memcpy` | Pre-store |
| `WriteExclusive<T>` | Callback before atomic compare/exchange | May not store |
| `WriteExclusive128` | Callback before 128-bit compare/exchange | May not store |
| `StoreDataCache` | Cache operation; no direct store in the callback | Already-written data; ordering must be proven |
| `FlushDataCache` | Cache operation; no direct store in the callback | Already-written data; ordering must be proven |

`CopyBlock` routes its writes through `WriteBlockImpl` and can perform
a preceding `HandleRasterizerDownload`. Other device-pointer, JIT/fastmem
and write-watch paths need separate verification; the list is an audit of
**this file's dispatch sites**, not proof that all writers are covered.

Before enabling native deferral: wrap each actual data-producing operation
with a reservation whose ticket is published only after its store has
completed; accommodate conditional atomic success, CPU cache operations,
and multiple nested or split writes. Prove that no untracked GPU/cache
writer can enter the deferred path, and do not change the CPU-read barrier
until GPU-thread scheduling and session lifetime are proven separately.

## Session identity is mandatory for read waits and drains

Host tests exposed an ambiguity in the first two-phase queue API: plain
`Sequence` values restart from 1 after title teardown. A consumer holding
sequence 1 from the old title could accidentally wait on, or drain, sequence
1 in the new title. The queue now returns a `Ticket {sequence, generation}`
from both `Reserve` and `EnqueueTracked`, accepts only a ticket for
`WaitUntil` and `DrainThrough`, and rejects a ticket whose generation
does not match the current session. Bare-number waits and drains are
rejected at C++ compile time by the host fixture. `Drain()` internally
captures the queue's current generation and accepted watermark.

This prevents one specific class of stale-session API misuse. The
`ResetAfterQuiescence` lifecycle precondition remains mandatory, and
neither a completed ticket nor a flush request proves GPU device-fence
completion. No native CPU reader has been wired to these APIs; the
`kNativePostStorePublicationReady = false` interlock remains in force.

## Cross-address-space ticket isolation

A further host audit found that the first generation-tagged API initialized
each Queue's `generation_` to 1. Distinct guest address spaces could thus
both issue `Ticket{1, 1}`, allowing one queue's ticket to be accepted by
another. Each Queue instance and each quiescent reset now acquires a fresh,
process-unique epoch from a checked atomic counter. Ticket identity therefore
covers the owning address space and the title session, in addition to FIFO
order. The host fixture tests rejection of foreign tickets on Publish,
WaitUntil and DrainThrough; bare sequence waits/drains remain unsupported.

This is a narrow host-level correctness proof, not an authorization to
activate the deferred path. GPU work scheduling, post-store native producer
integration, page-mapping lifetime and cache/texture fence ordering still
need separate verification.

## Shutdown replay lifetime barrier

A source audit found that merely setting `closed_` and waking the waiting
CPU threads allowed an already-entered `DrainThrough` callback to continue
after `Close()` returned. A title could then tear down rasterizer/texture
resources while a GPU-owner callback was still using them.

The inactive queue's `Close()` now performs three ordered steps:

1. Under the queue mutex, set `closed_` so new reservations, publications
   and new GPU drain snapshots are rejected.
2. Wake outstanding CPU waiters without holding the GPU-consumer lock.
3. Acquire the GPU-consumer mutex **after releasing the queue mutex** and wait
   for any already-active GPU replay batch to finish before returning.

The host fixture coordinates an active blocked GPU callback, a CPU waiter
and a closing thread. It asserts that the reader is cancelled promptly but
`Close()` cannot finish until that callback completes. A separate test
asserts that queued writes are not replayed after closure.

**Strict native integration preconditions:** `Close()` must not run from
inside a replay callback and must never be called while the caller holds a
GPU cache lock needed by that callback. All producers and waiters must be
joined before deleting the owning queue and address-space structures. A
callback that itself blocks indefinitely may delay closure indefinitely;
the host test verifies ordering, not shutdown progress for every engine
deadlock scenario. This is **not** a lifecycle integration into the native
title manager and does not make the bridge eligible for activation.

## Partial replay exception: poison instead of false completion

The inactive queue formerly removed a published batch from its FIFO before
invoking the rasterizer. A C++ exception from an individual replay callback
would then destroy that batch without advancing its completion watermark.
Subsequent drain attempts could process newer writes despite older, partially
applied cache operations being missing.

The queue now catches callback exceptions only to **poison the owning title
session**, wake pending CPU readers, and rethrow the original exception.
While poisoned:

- no later GPU drain can run, even after the throwing callback exits;
- no new writes may be enqueued or published;
- outstanding `WaitUntil(ticket)` calls fail rather than hang;
- the failed batch is **not** acknowledged as replayed;
- `Pending()` remains true until quiescent teardown, and `Failed()` exposes
  the terminal state for diagnostics.

A callback may already have changed buffer/texture state before throwing,
so blindly retrying that item would not be safe or necessarily idempotent.
The generated developer-only `MemoryManager::FlushCaching` now also checks
`Queue::Failed()` and terminates rather than allowing a later GPU command to
continue with the poisoned cache state, even if an intermediate layer catches
the original exception. This is a fail-closed safety gate, **not crash
recovery**, and the developer bridge remains disabled.
Only `Close()`, joining the producers/readers/GPU consumer and
`ResetAfterQuiescence()` can clear the poison for a *new* title session.
This is **not a runtime recovery mechanism**. Callers must treat a poison
as a fatal per-session coherency failure and avoid submitting more GPU work.

The C++ host sanitizer fixture now throws during the second callback in a
batch, verifies the exception reaches its caller, the reader is released
with failure and no fresh write/replay is accepted, then resets after joining
all threads. It does not model Vulkan's partially applied cache operations.

## Quiescent reset is now a checked lifecycle transition

The queue previously allowed `ResetAfterQuiescence()` while the session
was still open, simply trusting the caller's promise that all producers and
GPU callbacks had stopped. That could clear in-flight ticket state and
recycle the queue for a new title while old work was still active.

`ResetAfterQuiescence()` now returns `false` unless `Close()` has
**fully completed**, not merely set the close flag. It first acquires the
GPU-consumer mutex (except from inside its own callback, where it refuses
to proceed), then the queue mutex, preserving the established lock order.
A successful reset clears the completed-close gate, discards old-session
state and issues a fresh process-unique epoch for new tickets.

This protects against accidental live-session resets. The caller must
**still join all producers, CPU read waiters and GPU consumers before reset**;
that external ownership/lifetime rule is not automatically provable from
queue-local locks. Reset is not designed to race a second `Close()` call.

The host regression rejects reset on an open session or inside a replay
callback, and requires close-before-reset on all previous fixture paths.
The native bridge is still disabled and does not yet manage this lifecycle.

## Host backlog: publication lookup no longer quadratic

The queue's `Publish(ticket)` previously linearly scanned every pending
write, while another CPU core could publish a later reservation before an
earlier one. A backlog of `n` separate reservations published in reverse
order therefore required up to O(n²) comparisons just to mark them ready,
before any rasterizer work.

The queue already assigns strictly increasing `last_sequence` values to
FIFO entries. Same-core coalescing only changes the final entry's upper
sequence; GPU draining removes a prefix without reordering survivors.
`Publish` now performs a `std::lower_bound` lookup on this monotone key
under the existing queue mutex, giving O(log n) search with identical
exact-ticket and unpublished-entry validation.

The host fixture adds 4,096 reserved writes published in reverse order,
then verifies zero premature replay and exact FIFO output. It also tests
publication after a previously published prefix has been drained, including
rejecting the removed ticket. The source contract pins binary lookup.

This reduces one potential CPU contention hotspot in the **inactive
prototype**, not the native GPU rendering cost. The unbounded queue's
memory pressure, repeated prefix vector moves, guest-write publication,
GPU-read barriers and session integration remain blockers to activation.

## Lost GPU wake after publication: source-only scheduling contract

In the source-proven GPU path, `Core::Memory::HandleRasterizerDownload`
may return early from its per-core read-area cache, and
`GPU::Impl::OnCPURead` may return on a preemptive `GetFlushArea`.
Neither schedules a deferred queue drain. A pending `Reserve` can thus
make a GPU owner's `Drain()` return zero; simply publishing that entry
later does not, by itself, cause any GPU thread to revisit the queue.

The host-only queue now provides `PublishAndWake(ticket, request_gpu)`:

1. Validate the generation-tagged ticket and publish the completed RAM store
   under the queue mutex, using binary search over sequence-ordered writes.
2. Recognize an **edge from an unready FIFO head to a published head**.
   Publishing a tail behind an unpublished head does not spuriously wake the
   GPU. A newly published former head does, including after a preceding
   prefix was already drained.
3. Release the queue mutex **before** invoking the caller-supplied
   `request_gpu()` callback. A synchronous host test demonstrates the
   callback can reenter the queue without a lock inversion; in the native
   engine the callback must normally **enqueue GPU-thread work**, not
   recursively perform rasterizer replay on the GPU-owner thread.
4. If the scheduling callback throws, poison the title's queue and release
   blocked readers with an error. Do not claim the write has been replayed
   or rely on an unrelated later draw to repair the broken ordering.

The host fixture covers an initially blocked GPU drain, reverse publication
of 256 writes with **one** GPU wake, a published prefix followed by a
previously unpublished hole and a second wake, and scheduling failure.
It also holds a producer inside its GPU scheduling callback while title
`Close()` runs: the CPU read waiter is released, but the close operation
cannot return until the callback exits. Wake-callback lifetime is counted
under the queue mutex **before** invoking the notifier, and `Close()`
waits on a separate condition variable for all counted wake callbacks.
This protects the caller from reclaiming GPU scheduler resources while an
earlier producer is still issuing a GPU wake. A scheduling callback that
blocks forever will delay closure, so the eventual native implementation
must supply a nonblocking, bounded-lifetime wake request.
The fixture now also runs a separate asynchronous host GPU worker: its
first callback deliberately remains in progress while two later reservations
publish out of order. The wake request generated by the previously blocked
head must survive that in-flight callback and cause a second GPU-owner drain,
with exactly ordered replay and no duplicate ranges. The host-only queue
rejects recursive `Close()` from its own wake callback to avoid waiting for
itself to finish. These are host protocol checks, not native renderer results.

**This is not yet wired to any native post-store write path.** The current
developer-only bridge still uses eager `Enqueue` and the
`kNativePostStorePublicationReady = false` interlock. Future production
integration must schedule work safely on the existing
`GPU::Impl::RequestSyncOperation` / `gpu_thread.TickGPU` path, ensure
asynchronous/synchronous GPU modes and shutdown are handled, avoid holding
buffer/texture locks, and run all read barriers against *published* writes
before their CPU reader proceeds. Producer lifecycle must keep the queue
and GPU scheduler alive through the wake callback. A wake is not a
Vulkan fence and must not be mistaken for completion.

## Fail-closed CPU read tickets during shutdown

The original `WaitUntil(ticket)` woke readers when a session was closed or
poisoned, but returned success whenever the sequence watermark had been
completed. A GPU replay callback finishing concurrently with `Close()`,
or a previous successful callback followed by a replay exception, could
therefore make an unusable title's CPU reader believe its cache state was
still valid.

The host-only queue now requires **both** successful replay completion
**and** a live, unpoisoned session at the return point of `WaitUntil`.
A closed or failed session cannot authorize further CPU reads, even for
tickets acknowledged earlier. Host regressions cover an in-flight callback
completed during teardown, a completed write followed by `Close()`,
and a previously successful write followed by a later poisoned callback.

This does not prove guest-side visibility or Vulkan barriers, and the
developer-only bridge remains disabled. A native reader must treat `false`
as a fatal/session-cancelled barrier outcome rather than continuing with
potentially stale RAM.

## Bounded pending write budget

An uncommitted FIFO reservation blocks replay of every later reservation.
Previously, producers could continue accepting guest writes without any
limit while that head was unready, risking unbounded per-title memory
growth. The inactive queue now admits at most **8,192 accepted but not yet
acknowledged writes**, calculated as `accepted_ - completed_` under the
queue mutex. This includes:

- published or unpublished writes sitting in the FIFO;
- an entire GPU snapshot currently inside a replay callback (removed from
  the vector but not yet acknowledged);
- separately accepted sequence IDs merged into a single eager tail entry.

At the limit, both `Reserve` and legacy `EnqueueTracked` reject new
writes without advancing a sequence. Existing reserved writes can still
`Publish` and drain normally; once replay completes, the budget opens
again. The host test fills all 8,192 slots behind an unpublished head,
publishes them in reverse order, checks replay order and attempts a new
reservation from inside the still-in-flight GPU callback. It also verifies
that eager same-range coalescing cannot bypass the budget.

**Critical integration contract:** a rejected `Reserve` is not an
acknowledgment and must cause the actual CPU write site to take an original
synchronous/cache-correct path *before storing guest RAM*, or fail the
session. A caller must never drop the invalidation and continue. This
host-only bound does not prove any FPS gain, and the native developer bridge
remains disabled while its pre-store enqueue is unqualified.

## Native GPU worker failure versus CPU sync-fence liveness

A separate audit of the **active native GPU worker** found a concrete
failure mode independent of the disabled deferred guest-write queue. The
native worker already catches exceptions, records an `exception_ptr` via
`Eden::RecordGpuFailure`, and requests its stop token. However,
`GPU::Impl::WaitForSyncOperation(fence)` traditionally waits on
`sync_request_cv` until the GPU-owned `TickWork()` increments the
completion fence. Once the worker has exited unexpectedly, no subsequent
`TickWork()` can acknowledge outstanding requests. The deliberate
`NotifyShutdown()` path cancels waits **after joining the GPU worker**,
but a CPU thread blocked on a missing fence might prevent the shutdown
sequence from starting.

The native build now derives `gpu.cpp` with a source-pinned
`headless/gpu_sync_failure_wait.inc` method. It preserves the original
condition-variable completion notification and shutdown cancellation, but
checks a non-consuming copy of the already recorded fatal GPU error at
most every 100 ms while a fence is pending. On failure it rethrows that
original exception, rather than letting the CPU reader hang or inventing
fence completion. Multiple readers can observe the same fatal event;
`TakeGpuFailure` still clears the error only when a new GPU worker starts.

`tools/check-gpu-sync-failure-host.py` compiles this exact native-derived
wait method with host ASan/UBSan. It tests immediate normal completion,
two separate CPU waiters observing one unconsumed fatal worker error, and
unchanged voluntary shutdown cancellation without falsely advancing a
fence. The host workflow runs this test without building a console app.

This is a **fatal-error liveness correction in the native runtime**, not
a verified FC27 performance or gameplay fix. A GPU worker that remains
alive but blocks inside a rasterizer command will not record an exception;
the guard therefore does not address GPU work deadlocks, missing guest
fences, or all observed freezes. It also does not enable the deferred
guest-write queue, whose post-store native contract remains incomplete.

## Required engineering contract

- Give accepted entries an ordered, per-session completion watermark.
  A read of a tracked range must observe the completion of every
  causally earlier conflicting write before relying on cached read areas
  or calculating/flushing the GPU download area. Cross-core ordering is
  assigned by the queue's mutex, not by host thread identity.
- Put the read dependency check **before the per-core cached-area shortcut**
  and the `GetFlushArea` shortcut; patching only `GPU::OnCPURead` is insufficient.
- Request GPU-owner drainage and wait for its acknowledged watermark.
  No CPU caller may replay GPU cache operations directly. Do not wait
  while holding a GPU buffer/texture cache mutex or the queue mutex.
- Cover each live graphics address space, including non-default channels;
  the queue lives in a `Tegra::MemoryManager`, not a process-global singleton.
- Replace any future queue cap with watermark-aware drainage and
  shutdown-aware backpressure. Never fall back to synchronous handling
  of a newer write while older writes remain pending.
- At title shutdown/switch, either complete all required work before
  destroying caches/queues or explicitly cancel after producer quiescence;
  no blocked CPU producer or dangling GPU callback may survive teardown.

## Required host/native qualification before any console test

1. **Deterministic order test:** enqueue A, trigger a read before draw/DMA,
   assert replay completion precedes read-area lookup and GPU download.
2. **Read shortcut test:** already-cached read area and preemptive
   `GetFlushArea` both still honor pending write dependencies.
3. **Concurrency test:** four guest producers, overlapping ranges, GPU
   owner drainage, reads racing with writes; no lost or reordered
   pre-watermark invalidations.
4. **Liveness test:** a full queue blocks producers only outside locks;
   GPU drain unblocks them; cancellation during shutdown releases waiters;
   continuous producers cannot indefinitely starve the GPU owner.
5. **Native test:** compile the ON development bridge with the actual native
   toolchain and linked source units, then inspect real call ordering.
   Host source fixtures and sanitizers alone do not satisfy this gate.

The previous host run `38794257575` validates its listed host checks only.
Neither that run nor upstream experimental patches establish this read barrier.
Keep `EDEN_GUEST_WRITE_BRIDGE_DEV` and `cpu_write_defer` OFF for shipping.
