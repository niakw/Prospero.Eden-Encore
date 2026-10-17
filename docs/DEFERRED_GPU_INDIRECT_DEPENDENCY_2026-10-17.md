# GPU submission cannot seal indirect-memory dependencies (host evidence)

Source branch: dev/ps5-sparse-jit. Parent candidate: 9c7f0db.
This note supplements DEFERRED_JIT_QUIESCENCE_ARCHITECTURE_2026-10-17.md.
**NO-GO: native post-store publication remains disabled.**

## Verified native call path

1. GPU::PushGPUEntries forwards a CommandList to GPUThread::SubmitList.
2. GPUThread::StartThread pops SubmitListCommand and invokes Scheduler::Push.
3. Scheduler::Push calls dma_pusher.Push and then DispatchCalls.
4. DmaPusher::Step takes the next CommandListHeader (addr, size, sync)
   and only there instantiates GpuGuestMemory<CommandHeader, SafeRead or
   UnsafeRead> to read guest-backed command words. ProcessCommands then
   decodes method values and dispatches them to engine code.

At the SubmitList boundary the envelope does NOT enumerate all guest-memory
ranges subsequently referenced by decoded methods. Two submissions with
identical headers can result in different decoded method arguments when
the backing command RAM differs at Step execution.

tools/check-native-dma-indirect-dependencies-host.py compiles the
**unchanged pinned DmaPusher::Step() C++ method body** with narrow fake
MemoryManager, GpuGuestMemory and rasterizer dependencies. It tests both
safe/unsafe reads, identical envelope/different RAM content, and a change
to command RAM between enqueue and Step. The fake ProcessCommands only
records method words; this test does NOT execute actual GPU engine methods
or establish device-side use, writes, or Vulkan barriers.

## Impact on the quiescence design

The previous idea, "prepare all page transitions before queuing a
SubmitList", cannot in general derive a complete page dependency set
from the current submitted CommandList headers. A source-compatible
pre-classification that reads the indirect payload earlier also needs
an explicit RAM snapshot, source lifetime and coherency protocol:
the guest may change command RAM between pre-scan and GPU execution.
A blind pre-scan without snapshots is not proof.

A first-use hook at the actual guest-memory read or GPU cache operation
can observe the concrete address, but the GPU worker must NOT synchronously
wait there for quiescence: in the current queue, GPU::TickWork only runs
on a later GPUTickCommand, and GPU::OnCPURead can enqueue such a tick then
wait on it. A synchronous wait risks cyclic head-of-line blocking.

Permissible avenues for future research, not implementation approval:

- A producer-side sealed/snapshotted command plan with proven guest
  memory lifetime, indirect decode, alias and GPU fence ordering.
- A resumable GPU command interpreter that defers only the dependent
  operation, without losing its DMA decode state, silently reordering
  rasterizer work, or starving CPU-read synchronization.
- A bounded transition protocol whose confirmed quiescence occurs
  outside JIT and GPU-thread blocking call stacks.

A new GPU dispatcher must preserve SubmitList ordering, command list
fences, syncpoint callbacks, channel state, and the current shutdown
semantics. The existing DmaPusher::Step also waits for sync_cv when
signal_sync && !synced; this is another suspension point to audit.

## Explicit missing proof

No real Dynarmic + GPU DmaPusher integration test, no native device
memory visibility proof, no CAS/store postpublication, no mutable
GuestMemory alias coverage, and no quantitative performance outcome.
Keep #187 OFF. This host experiment does not justify console or FC27 tests.


## Additional host evidence: safe command reads are not always snapshots

The pinned \`core/guest_memory.h\` \`GuestMemory::Read()\` tries
\`GetSpan()\` first. When that succeeds, \`SafeRead\` calls \`FlushRegion()\`
but exposes a mutable, backing-RAM \`std::span\` rather than copying command
bytes. This is an important distinction: safe cache synchronization does not
freeze an immutable command payload for pre-decode analysis.

The existing \`tools/check-native-guest-memory-coherence-host.py\` now executes
two additional actual-template C++ checks with aligned 32-bit words:

- A contiguous \`SafeRead\` invokes \`FlushRegion\`, holds a live pointer
  into guest backing memory, and observes a subsequent backing-store update.
- A noncontiguous \`SafeRead\` copies via \`ReadBlock\` and retains the
  original word despite the same subsequent RAM update.

These controlled single-thread updates demonstrate alias-vs-copy *semantics*,
not a specific racy runtime write, cache stale-read occurrence, or Vulkan
device-coherence failure. Real GPU command dependencies cannot be considered
sealed just because \`SafeRead\` ran at pre-scan time. A future snapshot
design must guarantee ownership/lifetime and coverage of every indirect
command word, map/unmap generation, and dependent resource before authorizing
any reordered first-use GPU operation. The bridge remains disabled.
