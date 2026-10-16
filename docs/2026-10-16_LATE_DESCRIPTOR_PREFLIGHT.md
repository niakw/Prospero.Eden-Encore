# Descriptor queue: final preflight after pipeline reselection

## Source-level hazard

The native Vulkan draw path preflights the guest descriptor queue before taking
the buffer and texture cache mutexes. An independent descriptor-buffer ring
capacity preflight may still call Scheduler::Finish, consume pending guest
invalidations, and reselect a different graphics pipeline. That pipeline can
reserve more descriptor entries than the pipeline checked earlier.

UpdateDescriptorQueue::Acquire contains a WaitWorker fallback. Without a final
check, the fallback can run inside GraphicsPipeline::Configure while both
cache mutexes are held. The retained native-only change repeats
PreflightLargeGuestDraw after the ring-triggered pipeline reselection, before
the cache mutex pair. If a drain is required, it flushes guest invalidations
and reselects the pipeline again. No descriptor guest state is read ahead
of the cache locks and no actual GPU fence or queue order is changed.

The host test compiles the exact active C++ header preflights under Clang
ASan/UBSan and reproduces a changed reservation that was too large for the
earlier check. The model proves the late drain occurs outside both locks.
Source ordering guards pin the new call after the ring refresh and before
the paired lock. This is a bounded safety/preflight correction, not a
replacement for the full #187 guest CPU write deferral protocol.

**Limits:** no console build, shader workload tracing, or evidence that
FC27 encountered this exact late pipeline change. No FPS/HUD/freeze
improvement is claimed.
