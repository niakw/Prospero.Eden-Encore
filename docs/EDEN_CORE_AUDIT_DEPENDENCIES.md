# Eden Encore — active native dependency audit register

**Branch:** dev/ps5-sparse-jit. **Updated:** 2026-10-17. **Baseline reviewed:** 8ac4929.
**Technical scope:** guest CPU/HLE, JIT, GPU worker, Vulkan, memory coherency,
native build/CI. Launcher and theme work belongs to its separate conversation.

This is the **single place to resume this technical audit**. Do not open
previously reviewed files without naming a concrete new source change or new
evidence. Other chats may change the branch concurrently; re-read HEAD before
any operation, and avoid unrelated files.

## Status is not success in game

- **HOST**: a *specific property* was exercised by a host test. A passing
  test may deliberately prove an unsafe behavior. It does NOT certify
  end-to-end console performance, correct emulation or freeze resolution.
- **SOURCE**: located and inspected in source, but no causal or end-to-end
  proof. Do not count it as solved.
- **OPEN**: concrete source-level question not resolved yet.
- **PARKED**: intentionally stopped. Deferred native bridge #187 stays OFF.

Priority **P0** means actual frozen gameplay/HUD/long-frame causality;
**P1** means correctness and native integration; **P2** means experimental
memory bridge safety. A HOST property can still have an unmet device gate.

## Dependency order / no more circular audits

- Runtime build: B01 => Q01/Q02/Q03 => V01 => V02/V04/V05 => S01/S02
- Guest progress: B01 => J01/J02/J03/J04 => H01/H02/H03
- Deferred bridge only: D01/D02 + M01/M02/M03/M04 (**PARKED**, not a
  prerequisite to fixing normal game freezes).

**Next work in order:** T01 exact legacy CI source-rewrite count; then
H03 using already reviewed H01/H02; then V02 and V04 if there is a
presentation/HUD stall distinct from guest progress; then J01 and V05
only for remaining *unattributed* long-frame events. Do not return to
aggregate JIT/cache statistics already studied.

## Source files, functions and acceptance criteria

IDs are stable across commits. Depends lists IDs that must be understood
first, not a claim that they are semantically proved. Source paths and
function/contract tokens are checked by CI for existence only; the
**Remaining acceptance** column is what still needs proof.

<!-- AUDIT_ROWS_START -->
| ID | Priority | Depends | Source file | Function / contract | State | Prior proof / audit | Remaining acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | P1 | - | headless/CMakeLists.txt | EDEN_SHARED_JIT; EDEN_JIT_COMPILE_BATCH | SOURCE | tools/check-native-build-recipe.py | Verify selected native build flags before claiming integration |
| B02 | P1 | B01 | headless/CMakeLists.txt | write_derived; queue_slot_repair | HOST | tools/check-native-gpu-queue-slot-lifetime-host.py | Check native toolchain separately; host regression covers derived slot lifecycle |
| Q01 | P1 | B02 | vendor/sources/eden/src/common/bounded_threadsafe_queue.h | TryEmplace; Pop; std::construct_at | HOST | tools/check-native-gpu-queue-slot-lifetime-host.py | No claim about a specific game's resource lifetime |
| Q02 | P1 | Q01 | headless/gpu_queue_stop_wait.inc | EmplaceWaitWithStopToken | SOURCE | tools/check-gpu-producer-stop.py | Keep stop-aware producer wake and ownership checks |
| Q03 | P1 | Q01,Q02 | vendor/encore-active/eden-gpu/gpu_thread_dev.cpp | ThreadManager::RunWorker; ThreadManager::PushCommand; ThreadManager::Stop | SOURCE | tools/check-vendored-gpu-thread.py | Worker can stall without fatal exception; prove progress separately |
| Q04 | P1 | Q03 | vendor/sources/eden/src/video_core/gpu.cpp | GPU::OnCPURead; GPU::WaitForSyncOperation; GPU::TickWork | SOURCE | docs/2026-10-16_GPU_SYNC_TICK_SNAPSHOT.md | Check queued CPU read tick dependencies before any FIFO modification |
| D01 | P2 | Q03 | vendor/sources/eden/src/video_core/dma_pusher.cpp | DmaPusher::Step; DmaPusher::DispatchCalls; DmaPusher::ProcessCommands | HOST | tools/check-native-dma-resume-boundary-host.py | Unsafe restart proved; no native replay or partial continuation |
| D02 | P2 | D01 | vendor/sources/eden/src/video_core/dma_pusher.cpp | DmaPusher::Step; DmaPusher::SetState | HOST | tools/check-native-dma-indirect-dependencies-host.py | Late guest-RAM command decoding remains unsealed |
| V01 | P0 | Q03 | vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp | Scheduler::WorkerThread; Scheduler::WaitWorker; Scheduler::Finish | SOURCE | docs/FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md | Separate worker queue drain from physical GPU device fence wait |
| V02 | P0 | V01 | vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp | PresentManager::GetRenderFrame; PresentManager::PresentThread; PresentManager::WaitPresent | SOURCE | tools/check-vulkan-present-wait-host.py | Identify actual presentation stall boundary versus guest HUD |
| V03 | P0 | V02 | vendor/encore-active/eden-vulkan/vulkan_swapchain.cpp | Swapchain::AcquireNextImage | HOST | tools/check-ps5-vulkan-swapchain-acquire-bounds.py | Acquire retries bounded; no device-liveness claim |
| V04 | P0 | V02 | vendor/encore-active/eden-vulkan/vulkan_renderer.cpp | RendererVulkan::Composite; RendererVulkan::PresentLoading | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Prove compositor remains alive when guest match is frozen |
| V05 | P0 | V01,V04 | vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp | RasterizerVulkan::PrepareDraw; RasterizerVulkan::OnCPUWrite; RasterizerVulkan::GetFlushArea | SOURCE | tools/check-ps5-vulkan-cache-phases.py | Identify mutex owner for rare 285-ms texture wait; no guessing |
| V06 | P1 | V05 | vendor/sources/eden/src/video_core/texture_cache/texture_cache.h | TextureCache<P>::RunGarbageCollector; TextureCache<P>::TickFrame | SOURCE | tools/check-vulkan-gc-budget-host.py | Zero GC evictions near 3300-3600; deprioritized for that window |
| V07 | P1 | V05 | vendor/sources/eden/src/video_core/renderer_vulkan/vk_pipeline_cache.cpp | PipelineCache::CurrentGraphicsPipeline | SOURCE | tools/check-vulkan-shader-workers.py | Link pipeline work to an otherwise unexplained long frame |
| V08 | P1 | V05 | vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp | RasterizerVulkan::TickFrame | SOURCE | tools/check-ps5-vulkan-cache-phases.py | Only time critical sections if evidence identifies new window |
| J01 | P0 | B01 | headless/performance.cpp | eden_jit_compile; eden_jit_phases | SOURCE | docs/FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md | Distinguish newly compiled blocks versus invalidation and duplicates |
| J02 | P1 | J01 | vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_64.cpp | ArmDynarmic64::SignalInterrupt | SOURCE | docs/DEFERRED_JIT_QUIESCENCE_ARCHITECTURE_2026-10-17.md | Interrupt request alone is not JIT-exit acknowledgment |
| J03 | P1 | J02 | vendor/sources/eden/src/core/hle/kernel/physical_core.cpp | PhysicalCore::RunThread; PhysicalCore::Interrupt; PhysicalCore::ClearInterrupt; PhysicalCore::IsInterrupted | HOST | tools/check-native-physical-core-atomic-host.py | Atomic flag fixed in derived build; epoch handoff not implemented |
| J04 | P0 | J03 | vendor/sources/eden/src/core/cpu_manager.cpp | MultiCoreRunGuestThread | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Find the guest core wait versus actual resumed JIT execution |
| H01 | P0 | J04 | vendor/sources/eden/src/core/hle/kernel/k_condition_variable.cpp | KConditionVariable::Wait; KConditionVariable::Signal | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Determine real wait/notify ownership; last-SVC sample is not a stack |
| H02 | P0 | H01 | vendor/sources/eden/src/core/hle/kernel/k_scheduler.cpp | KScheduler::Schedule; KScheduler::Preempt | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Verify whether guest progress stalls in scheduler/wakeup |
| H03 | P0 | H02 | vendor/sources/eden/src/core/hle/kernel/k_thread.cpp | KThread::SetState; KThread::Wait | OPEN | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Inspect actual blocked thread state transitions; no HUD cause yet |
| H04 | P2 | J03 | vendor/sources/eden/src/core/hle/kernel/k_interrupt_manager.cpp | HandleInterrupt; ClearInterrupt | SOURCE | docs/DEFERRED_JIT_QUIESCENCE_ARCHITECTURE_2026-10-17.md | Keep ordinary interrupt clearing independent of future epoch gate |
| M01 | P2 | J03,V05 | vendor/sources/eden/src/core/guest_memory.h | GetSpan; FlushRegion; ReadBlock | HOST | tools/check-native-guest-memory-coherence-host.py | Direct SafeRead aliases remain mutable; no sealed snapshot |
| M02 | P2 | M01,D02 | headless/gpu_deferred_replay.h | kNativePostStorePublicationReady | PARKED | tools/check-deferred-native-bridge-contract.py | Bridge remains false until quiescence, FIFO and snapshot proofs |
| M03 | P2 | J03,M02 | docs/DEFERRED_JIT_QUIESCENCE_ARCHITECTURE_2026-10-17.md | QUIESCE; CONFIRM | PARKED | tools/check-native-jit-quiescence-model-host.py | No active native JIT-exit ACK/transition generation yet |
| M04 | P2 | D01,D02,M02 | docs/DEFERRED_GPU_INDIRECT_DEPENDENCY_2026-10-17.md | DmaPusher::Step | PARKED | tools/check-native-gpu-fifo-quiescence-host.py | No unsafe GPU-worker blocking wait or FIFO reorder |
| S01 | P0 | J01,V05,V02 | tools/analyze-ps5-cache-contention.py | def windows(; def report( | HOST | tools/check-fc27-cache-contention-classifier.py | Five-second aggregates cannot attribute one long frame |
| S02 | P0 | S01,H01,V04 | tools/analyze-fc27-frozen-workload.py | def analyze(; def self_test( | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Game logic can stop while compositor still emits 30 FPS |
| S03 | P0 | S01,V04 | docs/FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md | Root cause; Vulkan | SOURCE | tools/check-fc27-cache-contention-classifier.py | Do not reclassify existing October 15 logs without new evidence |
| T01 | P1 | B01 | tools/check-maintained-audio-units.py | cmake.count; gpu_producer_wait; gpu_read_capture | HOST | tools/check-maintained-audio-units.py | Allow exactly two named slot-lifetime rewrites; preserve old 227 ceiling |
| T02 | P1 | T01,Q01 | tools/check-native-gpu-queue-slot-lifetime-host.py | PINNED_GPU_QUEUE_SLOT_DESTRUCTOR_REUSE_PASS | HOST | tools/check-native-gpu-queue-slot-lifetime-host.py | Queue regression passed, but whole preflight failed on T01 gate |
<!-- AUDIT_ROWS_END -->

## Established findings — do not re-run without changed evidence

1. October 15 FC27 session uses **Vulkan**. The 285.3 ms mutex wait is
   time lost by a guest CPU callback; the mutex *owner* is unknown.
   Texture-GC evictions were zero around frames 3300-3600. An ~980 ms
   frame had much less lock contention. See S01/S03 and the linked triage.
2. Nearly perfect 30 FPS can coexist with the **guest match remaining
   frozen**. This is not evidence the guest simulation advances.
   Sampled last-SVC values are NOT actual live waiting stacks.
   See S02 and the earlier guest freeze forensic report.
3. Atomic native physical-core flag fix (8f88877): host PASS, but
   interrupt request is not JIT exit acknowledgment. DMA partial
   resume/restart is unsafe by the prior host witness.
4. Native GPU queue slot lifetime fix (3e5af13, 8ac4929): the
   specific queue host regression PASSED inside preflight 38992155660,
   but that entire workflow FAILED due to the independent T01
   generator budget guard. This register must be updated after T01 CI.
5. Native post-store #187 bridge is still DISABLED. Negative
   host witnesses for FIFO, aliases or DMA are not permission to
   enable the bridge or request a console build.

## How to update after each task

1. Read this register, the current branch HEAD, its linked evidence,
   then only the immediate caller/callee of the first relevant OPEN
   (or SOURCE with new evidence). Preserve concurrent work ownership.
2. Record an explicit hypothesis and a falsifiable check **before**
   changing behavior. If a previous hypothesis was disproved, do not
   reopen it without a code change or new observation.
3. After a narrow fix, update its row with the test, the *actual*
   completed CI URL/conclusion and the next still-unmet acceptance.
   A green test is not a green workflow; a green workflow is not
   a console game test.
4. When blocked or out of evidence, say so and leave the row open.
   Do not add another speculative test or pseudo-progress commit.
5. Keep source/derived file distinction. Console release/build
   only upon demonstrated benefit and authorization. No UI edits here.

The automated host register check validates paths, symbols, IDs,
dependency acyclicity and statuses, **not** behavior.
