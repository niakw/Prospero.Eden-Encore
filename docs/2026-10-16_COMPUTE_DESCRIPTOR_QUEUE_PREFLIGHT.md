# Compute guest descriptor queue preflight (native-only)

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

## Source defect

`RasterizerVulkan::DispatchCompute` held both guest cache mutexes while
`ComputePipeline::Configure` called `GuestDescriptorQueue::Acquire`. The
latter retains an overflow fallback that waits for the GPU command worker.
Unlike the draw path, compute had no ordinary descriptor queue preflight before
the mutex pair. This is a source-reachable wait-under-lock risk, not an
observed FC27 event.

## Bounded fix

The native dispatch path now runs the already-existing
`PreflightGuestDraw` before choosing the compute pipeline and before locking
the guest caches. When the queue needs a worker drain, it consumes guest memory
invalidations with `gpu_memory->FlushCaching()` before selecting the compute
pipeline, mirroring the graphics path.

The original `Acquire` fallback remains for atypical reservations greater
than 0x400 entries and other configurations. The descriptor buffer ring's
`Allocate` fallback may also still wait under the caches: this patch does
**not** solve that separate issue.

## Proof and limits

`tools/check-ps5-compute-guest-descriptor-preflight-host.py` extracts the
production `PreflightGuestDraw` method verbatim for Clang ASan/UBSan host
testing. Static guards require the new call and invalidation refresh to
precede pipeline selection and both mutexes. The existing generator preserves
the insertion on fresh source preparation. No console build, release, hardware
test or performance improvement is claimed.
