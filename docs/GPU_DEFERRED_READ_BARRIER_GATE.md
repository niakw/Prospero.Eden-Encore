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
