# JIT tracked-page quiescence architecture — host model only

Branch: dev/ps5-sparse-jit. Baseline: 1c970b0.

**NO-GO: native deferred bridge #187 stays disabled.** This is not a
gameplay fix. The new host-only model never changes runtime code.

## Facts from native source

1. PhysicalCore::Interrupt() sets an interrupt flag then calls the
   active ArmInterface::SignalInterrupt(). Dynarmic A32/A64 request
   HaltExecution(BreakLoop). This requests an exit, not proof of one.
2. PhysicalCore::RunThread() has an EnterContext/ExitContext boundary
   enclosing actual JIT execution. ExitContext unlocks the thread and
   clears the active interface; there is no per-title handoff epoch.
3. CpuManager::MultiCoreRunGuestThread() can enter RunThread again.
   A new admission therefore must be blocked while a transition is pending.
4. KernelCore::SuspendEmulation() waits for scheduler threads to stop.
   It must not be called synchronously by an active JIT callback or by the
   GPU worker when a CPU core may be waiting for that GPU worker.
5. RasterizerMarkRegionCached() changes the checked fastmem access
   permissions and page-table mark. A pre-checked direct JIT store can
   nevertheless still be in flight at the GPU's first dependent use.

## Candidate two-phase handoff

REQUEST:
- Under a short coordinator lock, declare a generation/epoch pending.
  Reject new JIT run admission, protect tracked-page fastmem access and
  mark the affected page table entries, and request interrupts on active
  cores. Return immediately to guest callbacks, including the requester
  itself. Do not wait under any memory, scheduler or GPU cache lock.
- The GPU owner must be able to defer only dependent commands, and keep
  servicing unrelated commands and CPU-to-GPU/GPU-to-CPU requests.

QUIESCE:
- A core acknowledges only after its actual old-generation JIT run
  has stopped and all its direct writes have completed.
- A signal, interrupt flag, scheduler suspend request, or partial callback
  return is not itself such an acknowledgment. The restart path must
  check the pending epoch before entering another JIT run.
- Account for idle cores, concurrent processes, guest span writers,
  error shutdown and asynchronous renderer callbacks independently.

CONFIRM:
- Permit first GPU use of the page only after all relevant JIT runs have
  acknowledged AND page mappings, host memory, and device-visible writes
  are synchronized. Finalization must not race another transition.
- Release run admission with acquire/release ordering, and keep the
  marked-page callback path active for new guest accesses.
- If interrupted workers cannot exit or a fence fails, fail closed
  instead of releasing an unqualified page.

## Deterministic host witness

tools/check-native-jit-quiescence-model-host.py compiles a C++20 model
with three controlled schedules: a stale pre-checked writer while another
core waits for GPU work, a request issued from inside an active JIT run,
and terminal failure. The gate is modeled at RUN entry/exit only; the
GPU owner continues to service work while the transition is pending.

PASS proves only the synthetic scheduling protocol. It does not execute
Dynarmic, PhysicalCore, or a Vulkan device fence, and it gives no
performance measurements. It does not prove absence of real lock cycles.

## Unmet enablement gates

- Prove actual interrupt-to-ExitContext acknowledgments and restart
  admission with a real host Dynarmic integration test.
- Prove the GPU dispatcher can defer dependent use without deadlocking
  GPU-read/download requests triggered by guest callbacks.
- Close mutable CPU-side GuestMemory span producer and lifetime gaps.
- Join CAS read/device fence, reserve/store/publish, GPU invalidate/dirty
  replay and cancellation/fatal paths with a concrete lock ordering proof.
- Quantify normal-run and contested-run overhead, transition latency
  p50/p95/p99 and worst-case tails before considering native activation.

No console build, release or FC27 test is requested.

## Newly verified FIFO head-of-line hazard

The pinned GPU worker (`video_core/gpu_thread.cpp`) pops ONE
`CommandDataContainer` and completes its SubmitList branch before
dispatching the next entry. GPU read synchronization uses
`RequestSyncOperation` + `gpu_thread.TickGPU` to enqueue a later
`GPUTickCommand`, which invokes `GPU::TickWork`.

If an earlier dependent SubmitList blocks the GPU worker awaiting JIT
quiescence, while a JIT core waits for its GPU read fence via the later
GPUTick, the GPU queue cannot advance. This produces a precise wait cycle:
SubmitList → JIT exit → CPU read fence → GPUTick → SubmitList completion.

`tools/check-native-gpu-fifo-quiescence-host.py` reproduces this bounded
head-of-line stall from a FIFO model tied to actual source anchors.
It also demonstrates a hypothetical *independently qualified* GPU control
path which services the read synchronization but leaves later graphics
submits ordered. The model does NOT prove it is safe to process such a
control request ahead of the blocked SubmitList in real Vulkan or DMA.
If independence or fence ordering is unknown, it explicitly fails closed.

**Design impact:** before adding any quiescence wait to `DispatchCalls`,
`FlushCaching`, a rasterizer operation or a queued SubmitList, either
(i) resolve the transition before the dependent command enters the FIFO,
or (ii) introduce a separately proven non-blocking command suspension
and control-plane progress mechanism. Do not pump arbitrary GPU commands,
call `TickWork` out of order, or bypass graphics FIFO merely to avoid
the deadlock. Both approaches still require real hardware/device-fence
qualification. The native deferred bridge gate remains false.


## Real PhysicalCore method boundary: interrupt request versus exit acknowledgment

The added host fixture \`tools/check-native-physical-core-interrupt-ack-host.py\`
compiles the **unchanged source method bodies** of
\`PhysicalCore::RunThread()\`, \`PhysicalCore::Interrupt()\`, and
\`PhysicalCore::ClearInterrupt()\` from the pinned native core.
A narrow fake \`ArmInterface\` blocks inside its JIT \`RunThread()\` method
and reports entry, interrupt calls and final guest-thread unlocks.
This is a real *core control flow* test but not a real Dynarmic JIT build.

Expected finite scenarios:

- With one RUN deliberately blocked, \`Interrupt()\` returns and calls
  \`SignalInterrupt()\` while \`ExitContext()\` has not yet unlocked the
  guest thread. Interrupt REQUEST is therefore not the quiescence ACK.
- Once the mocked JIT returns \`BreakLoop\`, the original
  \`ExitContext()\` unlocks the guest thread and clears active members.
- Calling \`RunThread()\` while its interrupt flag remains set returns
  without another JIT RUN admission.
- Calling \`ClearInterrupt()\` and then \`RunThread()\` permits a second
  execution. The current source does not hold a separate page-transition
  epoch or conditional admission barrier across that restart.

This is the precise native insertion opportunity for future design:
ACK must be recorded only after the actual \`ExitContext\` work completes;
RESUME must consult an independently controlled transition generation
before clearing the interrupt or allowing another JIT admission.
A naive ACK inside \`Interrupt()\` or unconditional \`ClearInterrupt()\`
would reintroduce a stale direct-write/first-GPU-use window.

Strict limits: mock \`SignalInterrupt()\` simply records a request; it
does not execute Dynarmic, guarantee interrupt latency, exercise code
patching, handle multi-core migration, prove any memory or GPU fence,
or implement the barrier. Existing Source/JIT native gate remains OFF,
and no gameplay improvement is claimed.


## IsInterrupted: eliminate a real host data race without ABI changes

Core::PhysicalCore was storing m_is_interrupted under m_guard and
reading it without a lock in IsInterrupted(), including the guest CPU
scheduler's MultiCoreRunGuestThread loop. Under the C++ memory model
that is a conflicting concurrent plain read/write, even though the
writers take a mutex. This is independent of the disabled #187 bridge.

The native-only CMake source derivation now includes
headless/physical_core_interrupt_atomic.cmake immediately before the
existing physical_core.cpp output. The helper requires exactly five
pinned accesses (six in the diagnostic profile variant), replacing
ALL reads and writes with std::atomic_ref<bool> / atomic_ref<const bool>
relaxed load/store. The original bool field and its layout remain
unchanged; no vendored file is modified. The existing m_guard mutex
continues to protect active ArmInterface/thread pointers and
the Idle condition-variable predicate. Relaxed atomic operations are
sufficient for this flag's standalone visibility; they do not provide
a JIT-exit acknowledgment, release a page epoch or synchronize GPU
memory. If the pinned source grows new accesses, CMake aborts rather
than allowing new unsynchronized mixed atomic/plain accesses.

The host-only test tools/check-native-physical-core-atomic-host.py
actually runs CMake -P against the pinned native source for both
shipping and diagnostic profile variants, checks every transformed
access, and compiles/runs the unchanged derived RunThread, Interrupt,
ClearInterrupt and IsInterrupted C++ method bodies. It injects a
bounded two-thread flag reader/toggler, while retaining the existing
mocked JIT interrupt/exit/reentry witness. It does not execute
the native console binary or prove Dynarmic/GPU handoff safety.

This is a concrete fix for a C++ data race in the native-derived code,
NOT a claim that the freezes/HUD stalls are fixed. #187 stays disabled.
