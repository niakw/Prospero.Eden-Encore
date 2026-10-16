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
