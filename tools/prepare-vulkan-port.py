"""Adapt the pinned Eden Vulkan platform boundary and required renderer fixes."""
from pathlib import Path
import struct
import subprocess
import sys
source, output = map(Path, sys.argv[1:])
port = Path(__file__).resolve().parents[1] / 'headless'
def adapt(relative, destination, replacements):
    text = (source / relative).read_text()
    for old, new in replacements:
        if text.count(old) != 1:
            raise RuntimeError(f"Pinned Vulkan anchor changed: {relative}: {old[:60]}")
        text = text.replace(old, new)
    path = output / destination
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != text:
        path.write_text(text)

adapt('src/core/frontend/emu_window.h', 'include/core/frontend/emu_window.h',
      [('    Xcb,', '    Xcb,\n    PS5,')])
adapt('src/video_core/renderer_vulkan/vk_rasterizer.cpp', 'vulkan_rasterizer.cpp', [
    # Compute synchronization (dev_vulkan.h compute_barriers): indirect
    # dispatches returned before the pre-dispatch barrier, and no barrier made a dispatch's
    # writes visible to later indirect arguments, vertex/index fetch, shaders or copies.
    ('void RasterizerVulkan::DispatchCompute() {',
     """namespace {
constexpr VkMemoryBarrier COMPUTE_WRITE_BARRIER{
    .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
    .pNext = nullptr,
    .srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT,
    .dstAccessMask = VK_ACCESS_INDIRECT_COMMAND_READ_BIT | VK_ACCESS_INDEX_READ_BIT |
                     VK_ACCESS_VERTEX_ATTRIBUTE_READ_BIT | VK_ACCESS_UNIFORM_READ_BIT |
                     VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT |
                     VK_ACCESS_TRANSFER_READ_BIT | VK_ACCESS_TRANSFER_WRITE_BIT,
};
constexpr VkMemoryBarrier COMPUTE_INPUT_BARRIER{
    .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
    .pNext = nullptr,
    .srcAccessMask = VK_ACCESS_MEMORY_WRITE_BIT,
    .dstAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_INDIRECT_COMMAND_READ_BIT,
};
constexpr VkPipelineStageFlags COMPUTE_CONSUMER_STAGES =
    VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT | VK_PIPELINE_STAGE_VERTEX_INPUT_BIT |
    VK_PIPELINE_STAGE_ALL_GRAPHICS_BIT | VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT |
    VK_PIPELINE_STAGE_TRANSFER_BIT;
} // namespace

void RasterizerVulkan::DispatchCompute() {"""),
    ('        scheduler.RequestOutsideRenderPassOperationContext();\n        scheduler.Record([pipeline, indirect_buffer = buffer->Handle(),',
     """        scheduler.RequestOutsideRenderPassOperationContext();
        if (::Eden::DevVulkan::compute_barriers) {
            scheduler.Record([](vk::CommandBuffer cmdbuf) {
                cmdbuf.PipelineBarrier(vk::PIPELINE_STAGE_GRAPHICS_COMPUTE_TRANSFER,
                                       VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT | VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT,
                                       0, COMPUTE_INPUT_BARRIER);
            });
        }
        scheduler.Record([pipeline, indirect_buffer = buffer->Handle(),"""),
    ('            cmdbuf.DispatchIndirect(indirect_buffer, indirect_offset);\n',
     """            cmdbuf.DispatchIndirect(indirect_buffer, indirect_offset);
            if (::Eden::DevVulkan::compute_barriers)
                cmdbuf.PipelineBarrier(VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, COMPUTE_CONSUMER_STAGES, 0,
                                       COMPUTE_WRITE_BARRIER);
"""),
    ('        cmdbuf.Dispatch(dim[0], dim[1], dim[2]);\n',
     """        cmdbuf.Dispatch(dim[0], dim[1], dim[2]);
        if (::Eden::DevVulkan::compute_barriers)
            cmdbuf.PipelineBarrier(VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, COMPUTE_CONSUMER_STAGES, 0,
                                   COMPUTE_WRITE_BARRIER);
"""),
    # CounterEnable below starts a query immediately. A deferred clear has no
    # active pass yet, so later realization would end that query in a different
    # render-pass scope (VUID-vkCmdEndQuery-None-07007). Keep the immediate path
    # when the guest enables occlusion counting.
    ('const bool can_defer_clear = ENABLE_DEFERRED_CLEAR &&',
     'const bool can_defer_clear = ENABLE_DEFERRED_CLEAR && !regs.zpass_pixel_count_enable &&'),
    ('#include <algorithm>', '#include <algorithm>\n#include "performance.h"'),
    # Guest threads take the cache locks here (tracked-page writes, flush-area reads).
    ('bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {',
     'bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {\n    ::Eden::Performance::DiagnosticTimer guest_write_timer(::Eden::Performance::guest_cpu_write);'),
    ('VideoCore::RasterizerDownloadArea RasterizerVulkan::GetFlushArea(DAddr addr, u64 size) {',
     'VideoCore::RasterizerDownloadArea RasterizerVulkan::GetFlushArea(DAddr addr, u64 size) {\n    ::Eden::Performance::DiagnosticTimer guest_read_timer(::Eden::Performance::guest_cpu_read);'),
    # ... and wait for those locks spinning briefly before sleeping (performance.h GuestCacheLock).
    ('        std::scoped_lock lock{texture_cache.mutex};\n        auto area = texture_cache.GetFlushArea(addr, size);',
     '        ::Eden::Performance::GuestCacheLock(texture_cache.mutex);\n'
     '        std::lock_guard lock{texture_cache.mutex, std::adopt_lock};\n        auto area = texture_cache.GetFlushArea(addr, size);'),
    ('        std::scoped_lock lock{buffer_cache.mutex};\n        if (buffer_cache.OnCPUWrite(addr, size)) {',
     '        ::Eden::Performance::GuestCacheLock(buffer_cache.mutex);\n'
     '        std::lock_guard lock{buffer_cache.mutex, std::adopt_lock};\n        if (buffer_cache.OnCPUWrite(addr, size)) {'),
    ('        std::scoped_lock lock{texture_cache.mutex};\n        texture_cache.WriteMemory(addr, size);\n    }\n    pipeline_cache.InvalidateRegion(addr, size);',
     '        ::Eden::Performance::GuestCacheLock(texture_cache.mutex);\n'
     '        std::lock_guard lock{texture_cache.mutex, std::adopt_lock};\n        texture_cache.WriteMemory(addr, size);\n    }\n    pipeline_cache.InvalidateRegion(addr, size);'),
    # From upstream ProsperoEden 0dd9dd0 (#102): submitting after 4096 draws
    # can exceed the PS5 GPU watchdog (VK_ERROR_DEVICE_LOST). Cap command
    # buffers at 512 draws, keeping Encore's current worker handoff cadence
    # and runtime diagnostics unchanged. Replace the FULL platform ifdef.
    ('#ifdef __ANDROID__\n    static constexpr u32 DRAWS_TO_DISPATCH = 512;\n    static constexpr u32 CHECK_MASK = 3;\n#else\n    static constexpr u32 DRAWS_TO_DISPATCH = 4096;\n    static constexpr u32 CHECK_MASK = 7;\n#endif // __ANDROID__\n\n    static_assert(DRAWS_TO_DISPATCH % (CHECK_MASK + 1) == 0);\n',
     '    static constexpr u32 DRAWS_TO_DISPATCH = 512;\n'
     '    const u32 CHECK_MASK = ::Eden::Performance::dispatch_mask.load(std::memory_order_relaxed);\n\n'),
    # R309 PS5 watchdog: upstream checked the dispatch cadence BEFORE the 512-draw
    # ceiling. At mask 7 it therefore flushed on draw 519, not 512; at mask 63
    # on draw 575. Enforce the hard ceiling independently of dispatch cadence.
    # Preserve the original pre-flush dispatch calls and all cache/fence locks.
    ('    if ((++draw_counter & CHECK_MASK) != CHECK_MASK) {\n'
     '        return;\n'
     '    }\n'
     '    if (draw_counter < DRAWS_TO_DISPATCH) {\n'
     '        scheduler.DispatchWork();\n'
     '        return;\n'
     '    }\n'
     '    scheduler.Flush();\n'
     '    draw_counter = 0;',
     '''    ++draw_counter;
    if (draw_counter >= DRAWS_TO_DISPATCH) {
        scheduler.Flush();
        draw_counter = 0;
        return;
    }
    if ((draw_counter & CHECK_MASK) == CHECK_MASK) {
        scheduler.DispatchWork();
    }'''),
    # Per-draw count for the GPU-thread report (dispatch time per draw).
    ('    FlushWork();\n    gpu_memory->FlushCaching();\n\n    GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()};',
     '    if (::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed))\n'
     '        ::Eden::Performance::rasterizer_draw.calls.fetch_add(1, std::memory_order_relaxed);\n    FlushWork();\n    gpu_memory->FlushCaching();\n\n    GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()};'),

    # R319: the guest descriptor queue can call scheduler.WaitWorker() on
    # capacity overflow while BOTH GPU caches are locked in ConfigureImpl.
    # Pre-drain the ordinary 0x400-entry reserve on the GPU thread BEFORE
    # the rasterizer takes those mutexes, using the same worker fence as
    # Acquire. Keep Acquire's original larger-descriptor fallback intact.
    ('    gpu_memory->FlushCaching();\n\n    GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()};',
     '''    gpu_memory->FlushCaching();
#ifdef PS5_NATIVE
    if (guest_descriptor_queue.PreflightGuestDraw([this] { scheduler.WaitWorker(); })) {
        // CPU guests can have invalidated texture pages during the drain.
        // Consume those guest remaps before choosing a pipeline/cache views.
        gpu_memory->FlushCaching();
    }
#endif

    GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()};'''),
    # R325: uncommon >0x400-entry pipeline descriptor reservations can still
    # block in Acquire() under both guest cache mutexes. Check their exact
    # immutable reservation and reselect after any actual worker drain.
    ('    GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()};\n'
     '    if (!pipeline) {\n        return;\n    }',
     '''    GraphicsPipeline* pipeline{pipeline_cache.CurrentGraphicsPipeline()};
    if (!pipeline) {
        return;
    }
#ifdef PS5_NATIVE
    for (unsigned preflight = 0; preflight != 2; ++preflight) {
        if (!guest_descriptor_queue.PreflightLargeGuestDraw(
                [this] { scheduler.WaitWorker(); }, pipeline->DescriptorEntryReservation()))
            break;
        gpu_memory->FlushCaching();
        pipeline = pipeline_cache.CurrentGraphicsPipeline();
        if (!pipeline) return;
    }
#endif'''),
    # A forced release blocks the GPU thread until the fence thread has retired
    # every older fence. Time only that producer-side drain.
    ('    fence_manager.WaitPendingFences(force);',
     '''    if (force) {
        ::Eden::Performance::DiagnosticTimer drain_timer(::Eden::Performance::gpu_fence_drain);
        fence_manager.WaitPendingFences(force);
    } else {
        fence_manager.WaitPendingFences(force);
    }'''),
    # UpdateDynamicStates asked the cache for the current pipeline a second time
    # per draw, recomputing the same fixed-state key. Reuse PrepareDraw's result;
    # other callers keep the original lookup.
    ('template <typename Func>\nvoid RasterizerVulkan::PrepareDraw(bool is_indexed, Func&& draw_func) {',
     '''namespace {
// GPU thread only: the pipeline PrepareDraw refreshed for the draw in progress.
GraphicsPipeline* prepared_pipeline = nullptr;
} // namespace

template <typename Func>
void RasterizerVulkan::PrepareDraw(bool is_indexed, Func&& draw_func) {'''),
    ('    std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};\n    // update engine as channel may be different.',
     '''#ifdef PS5_NATIVE
    // Waiting on an eight-frame-old descriptor buffer GPU fence here keeps
    // guest texture writes unblocked while the Vulkan GPU owner waits.
    if (pipeline->CanUseDescriptorBuffer() &&
        descriptor_buffer_ring.PreflightFrameReuse(scheduler)) {
        gpu_memory->FlushCaching();
    }
#endif
    const bool cache_sample = ::Eden::Performance::ShouldSampleCacheDraw();
    const bool previous_sample = ::Eden::Performance::cache_draw_sample_active;
    ::Eden::Performance::cache_draw_sample_active = cache_sample;
    SCOPE_EXIT { ::Eden::Performance::cache_draw_sample_active = previous_sample; };
    ::Eden::Performance::CachePhaseTimer pair_wait{
        ::Eden::Performance::CachePhase::PairWait, cache_sample};
    std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};
    pair_wait.Stop();
    ::Eden::Performance::CachePhaseTimer pair_held{
        ::Eden::Performance::CachePhase::PairHeld, cache_sample};
    prepared_pipeline = pipeline;
    SCOPE_EXIT {
        prepared_pipeline = nullptr;
    };
    // update engine as channel may be different.'''),
    # R310: keep all GPU cache locks unchanged. Only clock 1/16 diagnostic
    # draws to resolve whether actual waits are in Configure or drawing.
    ('    pipeline->SetEngine(maxwell3d, gpu_memory);\n    if (!pipeline->Configure(is_indexed))\n        return;\n\n    UpdateDynamicStates();\n',
     '''    ::Eden::Performance::CachePhaseTimer configure_phase{
        ::Eden::Performance::CachePhase::PipelineConfigure, cache_sample};
    pipeline->SetEngine(maxwell3d, gpu_memory);
    const bool pipeline_ok = pipeline->Configure(is_indexed);
    configure_phase.Stop();
    if (!pipeline_ok)
        return;

    ::Eden::Performance::CachePhaseTimer dynamic_phase{
        ::Eden::Performance::CachePhase::DynamicStates, cache_sample};
    UpdateDynamicStates();
    dynamic_phase.Stop();
'''),
    ('    query_cache.NotifySegment(true);\n    HandleTransformFeedback();\n    query_cache.CounterEnable(VideoCommon::QueryType::ZPassPixelCount64, maxwell3d->regs.zpass_pixel_count_enable);\n    draw_func();',
     '''    ::Eden::Performance::CachePhaseTimer draw_phase{
        ::Eden::Performance::CachePhase::QueryAndDraw, cache_sample};
    query_cache.NotifySegment(true);
    HandleTransformFeedback();
    query_cache.CounterEnable(VideoCommon::QueryType::ZPassPixelCount64, maxwell3d->regs.zpass_pixel_count_enable);
    draw_func();
    draw_phase.Stop();'''),
    ('        if (auto* gp = pipeline_cache.CurrentGraphicsPipeline(); gp && gp->HasDynamicVertexInput()) {',
     '        if (auto* gp = prepared_pipeline ? prepared_pipeline : pipeline_cache.CurrentGraphicsPipeline();\n            gp && gp->HasDynamicVertexInput()) {'),
    # Development GPU fault probe (dev_vulkan.h, pipeline_trace=on): once the runner
    # creates /app0/sync-draws.txt, report every draw/dispatch to klog and wait for the
    # GPU, so the last report before a fatal GPU fault names the operation.
    ('#include "performance.h"', '#include "performance.h"\n#include "dev_vulkan.h"\n#include "diagnostics.h"\n#include <filesystem>'),
    ('GraphicsPipeline* prepared_pipeline = nullptr;',
     'GraphicsPipeline* prepared_pipeline = nullptr;\n'
     '// The pipeline of the last prepared draw, for the development fault probe.\n'
     'GraphicsPipeline* probe_pipeline = nullptr;\n'
     'bool SyncProbeActive() {\n'
     '    static unsigned poll = 0;\n'
     '    static bool active = false;\n'
     '    if (!active && ::Eden::DevVulkan::trace_pipelines && (++poll & 255) == 0)\n'
     '        active = std::filesystem::exists("/app0/sync-draws.txt");\n'
     '    return active;\n'
     '}\n'
     'void SyncProbe(Scheduler& scheduler, const char* kind, const void* pipeline) {\n'
     '    if (!SyncProbeActive()) return;\n'
     '    static unsigned long long sequence = 0;\n'
     '    char text[96];\n'
     '    std::snprintf(text, sizeof(text), "%s #%llu p=%p", kind, ++sequence, pipeline);\n'
     '    ::Eden::Report("sync", text);\n'
     '    scheduler.Finish();\n'
     '}'),
    ('    prepared_pipeline = pipeline;\n', '    prepared_pipeline = pipeline;\n    probe_pipeline = pipeline;\n'),
    ('        }\n    });\n}\n\nvoid RasterizerVulkan::DrawIndirect() {',
     '        }\n    });\n    SyncProbe(scheduler, "draw", probe_pipeline);\n}\n\nvoid RasterizerVulkan::DrawIndirect() {'),
    ('void RasterizerVulkan::DrawTexture() {', 'void RasterizerVulkan::DrawTexture() {\n    SCOPE_EXIT { SyncProbe(scheduler, "draw_texture", nullptr); };'),
    ('void RasterizerVulkan::Clear(u32 layer_count) {', 'void RasterizerVulkan::Clear(u32 layer_count) {\n    SCOPE_EXIT { SyncProbe(scheduler, "clear", nullptr); };'),
    ('    ComputePipeline* const pipeline{pipeline_cache.CurrentComputePipeline()};\n    if (!pipeline) {\n        return;\n    }',
     '    ComputePipeline* const pipeline{pipeline_cache.CurrentComputePipeline()};\n    if (!pipeline) {\n        return;\n    }\n'
     '    SCOPE_EXIT { SyncProbe(scheduler, "dispatch", pipeline); };'),
])
# Host conditional rendering (VK_EXT_conditional_rendering, dev_vulkan.h hcr_mode): count each
# decision (EDEN_DEV_GUEST cond= slots 13-19); hcr=exact sends the conditions Eden would draw
# unconditionally, or predicate from a pending host query, to the exact CPU evaluation;
# hcr=cpu evaluates every condition on the CPU and predicates from constant 0/1 buffers.
adapt('src/video_core/renderer_vulkan/vk_query_cache.cpp', 'vulkan_query_cache.cpp', [
    ('#include "video_core/vulkan_common/vulkan_wrapper.h"\n',
     '#include "video_core/vulkan_common/vulkan_wrapper.h"\n#include "dev_vulkan.h"\n#include "performance.h"\n'),
    ('    vk::Buffer hcr_resolve_buffer;\n',
     '    vk::Buffer hcr_resolve_buffer;\n    vk::Buffer hcr_constant_buffer; // hcr=cpu: predicates 0 and 1\n'),
    ('        hcr_resolve_buffer = memory_allocator.CreateBuffer(buffer_ci, MemoryUsage::DeviceLocal);\n    }\n',
     '''        hcr_resolve_buffer = memory_allocator.CreateBuffer(buffer_ci, MemoryUsage::DeviceLocal);
        if (device.IsExtConditionalRendering() && ::Eden::DevVulkan::hcr_mode == 2) {
            VkBufferCreateInfo constant_ci = buffer_ci;
            constant_ci.size = 2 * sizeof(u32);
            constant_ci.usage = VK_BUFFER_USAGE_CONDITIONAL_RENDERING_BIT_EXT;
            hcr_constant_buffer = memory_allocator.CreateBuffer(constant_ci, MemoryUsage::Upload);
            const u32 predicates[2]{0, 1};
            std::memcpy(hcr_constant_buffer.Mapped().data(), predicates, sizeof(predicates));
            hcr_constant_buffer.Flush();
        }
    }
'''),
    ('''bool QueryCacheRuntime::HostConditionalRenderingCompareValue(VideoCommon::LookupData object_1,
                                                             [[maybe_unused]] bool qc_dirty) {
    if (!impl->device.IsExtConditionalRendering()) {
        return false;
    }
    HostConditionalRenderingCompareBCImpl(object_1.address, true, true);
    return true;
}''',
     '''namespace {
// hcr=cpu: Maxwell3D::ProcessQueryCondition's exact evaluation (the read flushes pending GPU
// results), then the driver predicates the draws from a constant buffer. kind: 0 Conditional,
// 1 IfEqual, 2 IfNotEqual.
bool HostConditionalRenderingOnCpu(QueryCacheRuntime& runtime, QueryCacheRuntimeImpl& impl, DAddr address,
                                   unsigned kind) {
    if (address == 0 || !impl.hcr_constant_buffer) {
        ::Eden::Performance::CountCondition(13);
        runtime.EndHostConditionalRendering();
        return false;
    }
    u32 compare[6]{};
    impl.device_memory.ReadBlock(address, compare, sizeof(compare));
    const bool equal = compare[0] == compare[4] && compare[1] == compare[5];
    const bool execute = kind == 0 ? compare[0] != 0 && compare[1] != 0 : (kind == 1 ? equal : !equal);
    ::Eden::Performance::CountCondition(execute ? 17 : 18);
    const bool was_running = impl.is_hcr_running;
    if (was_running) {
        runtime.PauseHostConditionalRendering();
    }
    impl.hcr_setup.buffer = *impl.hcr_constant_buffer;
    impl.hcr_setup.offset = execute ? sizeof(u32) : 0;
    impl.hcr_setup.flags = 0;
    impl.hcr_is_set = true;
    impl.is_hcr_running = false;
    if (was_running) {
        runtime.ResumeHostConditionalRendering();
    }
    return true;
}
} // namespace

bool QueryCacheRuntime::HostConditionalRenderingCompareValue(VideoCommon::LookupData object_1,
                                                             [[maybe_unused]] bool qc_dirty) {
    if (!impl->device.IsExtConditionalRendering()) {
        return false;
    }
    if (::Eden::DevVulkan::hcr_mode == 2) {
        return HostConditionalRenderingOnCpu(*this, *impl, object_1.address, 0);
    }
    if (::Eden::DevVulkan::hcr_mode == 1 && qc_dirty) {
        ::Eden::Performance::CountCondition(19);
        EndHostConditionalRendering();
        return false;
    }
    ::Eden::Performance::CountCondition(16);
    HostConditionalRenderingCompareBCImpl(object_1.address, true, true);
    return true;
}'''),
    ('''    if (!impl->device.IsExtConditionalRendering()) {
        return false;
    }

    const auto check_in_bc = [&](DAddr address) {''',
     '''    if (!impl->device.IsExtConditionalRendering()) {
        return false;
    }
    if (::Eden::DevVulkan::hcr_mode == 2) {
        return HostConditionalRenderingOnCpu(*this, *impl, object_1.address, equal_check ? 1 : 2);
    }

    const auto check_in_bc = [&](DAddr address) {'''),
    ('''    if (!is_in_ac[0] && !is_in_ac[1]) {
        EndHostConditionalRendering();
        return false;
    }

    if (!qc_dirty && !is_in_bc[0] && !is_in_bc[1]) {
        EndHostConditionalRendering();
        return false;
    }
''',
     '''    if (!is_in_ac[0] && !is_in_ac[1]) {
        ::Eden::Performance::CountCondition(13);
        EndHostConditionalRendering();
        return false;
    }

    if (!qc_dirty && !is_in_bc[0] && !is_in_bc[1]) {
        ::Eden::Performance::CountCondition(13);
        EndHostConditionalRendering();
        return false;
    }
    // hcr=exact: a pending host query is not in any buffer yet; the CPU evaluation waits for it.
    if (::Eden::DevVulkan::hcr_mode == 1 && qc_dirty) {
        ::Eden::Performance::CountCondition(19);
        EndHostConditionalRendering();
        return false;
    }
'''),
    ('''            HostConditionalRenderingCompareValueImpl(*objects[j], equal_check);
            return true;''',
     '''            ::Eden::Performance::CountCondition(15);
            HostConditionalRenderingCompareValueImpl(*objects[j], equal_check);
            return true;'''),
    ('''    if (!is_gpu_high) {
        EndHostConditionalRendering();
        return true;
    }

    if (!is_in_bc[0] && !is_in_bc[1]) {
        EndHostConditionalRendering();
        return true;
    }
    HostConditionalRenderingCompareBCImpl(object_1.address, equal_check);''',
     '''    // Eden draws these unconditionally; hcr=exact evaluates them on the CPU instead.
    if (!is_gpu_high || (!is_in_bc[0] && !is_in_bc[1])) {
        ::Eden::Performance::CountCondition(14);
        EndHostConditionalRendering();
        return ::Eden::DevVulkan::hcr_mode != 1;
    }
    ::Eden::Performance::CountCondition(16);
    HostConditionalRenderingCompareBCImpl(object_1.address, equal_check);'''),
])

# R319: avoid descriptor-ring overflow waits while holding the paired guest
# buffer/texture cache mutexes. Only the graphics queue invokes this method.
# Normal draws add one cheap space check; overflow still waits using exactly
# scheduler.WaitWorker(), which was the original UpdateDescriptorQueue gate.
adapt('src/video_core/renderer_vulkan/vk_update_descriptor.h',
      'include/video_core/renderer_vulkan/vk_update_descriptor.h', [
    ('    void Acquire(Scheduler& scheduler, size_t required_entries = 0,\n'
     '                 bool use_descriptor_buffer_ = false);',
     '''    void Acquire(Scheduler& scheduler, size_t required_entries = 0,
                 bool use_descriptor_buffer_ = false);
#ifdef PS5_NATIVE
    template <typename WaitWorker>
    [[nodiscard]] bool PreflightGuestDraw(WaitWorker&& wait_worker) {
        // The common graphics descriptor reservation is at most 0x400
        // entries. Overflow waits are not allowed to hold both cache locks.
        constexpr size_t ordinary_reserve = 0x400;
        const size_t used = static_cast<size_t>(payload_cursor - payload_start);
        if (used + ordinary_reserve < frame_payload_size)
            return false;
        wait_worker();
        payload_cursor = payload_start;
        return true;
    }
    template <typename WaitWorker>
    [[nodiscard]] bool PreflightLargeGuestDraw(WaitWorker&& wait_worker, size_t entries) {
        // Keep the exact Acquire fallback, including oversized reservations.
        if (entries <= 0x400 || entries >= frame_payload_size)
            return false;
        const size_t used = static_cast<size_t>(payload_cursor - payload_start);
        if (used + entries < frame_payload_size)
            return false;
        wait_worker();
        payload_cursor = payload_start;
        return true;
    }
#endif'''),
])

adapt('src/video_core/renderer_vulkan/vk_swapchain.cpp', 'vulkan_swapchain.cpp', [
    # An acquisition error has no usable image index. Forward it to the existing
    # renderer recovery path instead of indexing or presenting an invalid image.
    ('LOG_ERROR(Render_Vulkan, "vkAcquireNextImageKHR returned {}", string_VkResult(result));',
     'LOG_ERROR(Render_Vulkan, "vkAcquireNextImageKHR returned {}", string_VkResult(result));\n        vk::Check(result);'),
    ('LOG_CRITICAL(Render_Vulkan, "Failed to present with error {}", string_VkResult(result));',
     'LOG_CRITICAL(Render_Vulkan, "Failed to present with error {}", string_VkResult(result));\n        vk::Check(result);'),
])
# Keep the overlay in the existing display composition pass (also used for
# frontend screenshots), excluding guest applet captures. Cache its pipeline.
# Preserve upstream ABI, including consumers whose quoted includes resolve to
# the original header. Display/capture purpose belongs to the draw call.
adapt('src/video_core/present.h', 'include/video_core/present.h', [])
adapt('src/video_core/renderer_vulkan/vk_present_manager.h',
      'include/video_core/renderer_vulkan/vk_present_manager.h', [
    ('#include <mutex>', '#include <mutex>\n#include <exception>'),
    # R336: present worker can recreate swapchain while GPU renderer reads its metadata.
    ('#include <condition_variable>', '#include <atomic>\n#include <condition_variable>'),
    ('    [[nodiscard]] size_t MaxExtraFrames() const;',
     '    [[nodiscard]] size_t MaxExtraFrames() const;\n'
     '    [[nodiscard]] std::size_t SwapchainImageCount() const { return swapchain_image_count.load(); }\n'
     '    [[nodiscard]] VkFormat SwapchainImageFormat() const { return swapchain_image_format.load(); }\n'
     '    [[nodiscard]] VkFormat SwapchainImageViewFormat() const { return swapchain_image_view_format.load(); }'),
    ('    std::size_t image_count{};',
     '    std::atomic<std::size_t> image_count{};\n'
     '    std::atomic<std::size_t> swapchain_image_count{};\n'
     '    std::atomic<VkFormat> swapchain_image_format{};\n'
     '    std::atomic<VkFormat> swapchain_image_view_format{};'),
    ('    std::jthread present_thread;',
     '    bool present_in_flight{}; // guarded by queue_mutex\n'
     '    std::exception_ptr present_failure;\n    std::jthread present_thread;'),
    # R335: declare frame abandonment on repeated surface loss.
    ('    void SetImageCount();',
     '    void DiscardFrame(Frame* frame);\n\n    void SetImageCount();'),
])
adapt('src/video_core/renderer_vulkan/vk_present_manager.cpp', 'vulkan_present_manager.cpp', [
    # R335: bounded recovery from VK_ERROR_SURFACE_LOST_KHR. Upstream #4509
    # October 8 2026 avoids a permanent while(true) Vulkan present loop.
    ('constexpr size_t MAX_FRAMES_IN_FLIGHT = 7;',
     'constexpr size_t MAX_FRAMES_IN_FLIGHT = 7;\nconstexpr u32 MAX_PRESENT_ATTEMPTS = 3;'),
    # Capture presenter-owned swapchain metadata without data races.
    ('    image_count = std::min<size_t>(swapchain.GetImageCount(), MAX_FRAMES_IN_FLIGHT);\n#endif',
     '    image_count = std::min<size_t>(swapchain.GetImageCount(), MAX_FRAMES_IN_FLIGHT);\n#endif\n'
     '    swapchain_image_count.store(swapchain.GetImageCount());\n'
     '    swapchain_image_format.store(swapchain.GetImageFormat());\n'
     '    swapchain_image_view_format.store(swapchain.GetImageViewFormat());'),
    ('void PresentManager::CopyToSwapchain(Frame* frame) {',
     '''void PresentManager::DiscardFrame(Frame* frame) {
    static constexpr VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT;
    const VkSemaphore render_ready = *frame->render_ready;
    const VkSubmitInfo submit_info{
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .pNext = nullptr,
        .waitSemaphoreCount = 1U,
        .pWaitSemaphores = &render_ready,
        .pWaitDstStageMask = &wait_stage,
        .commandBufferCount = 0U,
        .pCommandBuffers = nullptr,
        .signalSemaphoreCount = 0U,
        .pSignalSemaphores = nullptr,
    };
    std::scoped_lock submit_lock{scheduler.submit_mutex};
    void(device.GetGraphicsQueue().Submit(submit_info, *frame->present_done));
}

void PresentManager::CopyToSwapchain(Frame* frame) {'''),
    ('    while (true) {\n        try {\n            // Recreate surface and swapchain if needed.',
     '    for (u32 attempt = 0; attempt < MAX_PRESENT_ATTEMPTS; ++attempt) {\n'
     '        try {\n            // Recreate surface and swapchain if needed.'),
    ('    }\n}\n\nvoid PresentManager::CopyToSwapchainImpl(Frame* frame) {',
     '    }\n    DiscardFrame(frame);\n}\n\nvoid PresentManager::CopyToSwapchainImpl(Frame* frame) {'),
    # R334: the existing RecreateFrame unconditionally assigns a new VkImage
    # while its previous VkFramebuffer and VkImageViews are still live.
    # Release dependents in Vulkan parent-child order before image replacement.
    ('    frame->image = memory_allocator.CreateImage({',
     '    frame->framebuffer = vk::Framebuffer{};\n'
     '    frame->storage_view = vk::ImageView{};\n'
     '    frame->image_view = vk::ImageView{};\n'
     '    frame->image = memory_allocator.CreateImage({'),
    # The upstream reset of storage_view after the new image_view is built
    # is now redundant: it is already released before the old VkImage.
    ('    frame->storage_view = vk::ImageView{};\n    if (storage_supported) {',
     '    if (storage_supported) {'),
    ('#include "video_core/renderer_vulkan/vk_present_manager.h"',
     '#include "video_core/renderer_vulkan/vk_present_manager.h"\n#include "gpu_failure.h"\n#include "performance.h"'),
    # GetRenderFrame runs on the GPU thread: time its free-frame and
    # present-completion waits (FIFO back-pressure on the producer).
    ('    // Wait for free presentation frames\n    std::unique_lock lock{free_mutex};',
     '    // Wait for free presentation frames\n    ::Eden::Performance::DiagnosticTimer present_wait_timer(::Eden::Performance::gpu_present_wait);\n    std::unique_lock lock{free_mutex};'),
    ('PresentThread(token);', '''try {
            PresentThread(token);
        } catch (...) {
            const auto error = std::current_exception();
            {
                std::scoped_lock lock{queue_mutex, free_mutex};
                present_failure = error;
                present_queue.clear();
                present_in_flight = false;
            }
            free_cv.notify_all();
            frame_cv.notify_all();
            Eden::RecordGpuFailure(error);
        }'''),
    ('free_cv.wait(lock, [this] { return !free_queue.empty(); });',
     '''free_cv.wait(lock, [this] { return present_failure || !free_queue.empty(); });
    if (present_failure) std::rethrow_exception(present_failure);'''),
    # Once dequeued, only GetRenderFrame owns this Frame until it returns.
    # Do not block PresentThread's free-queue handoff on a GPU fence wait.
    ('    free_queue.pop_front();',
     '    free_queue.pop_front();\n'
     '    // Exclusive ownership transferred to this caller. Let the present\n'
     '    // thread recycle OTHER frames during our Vulkan GPU fence wait.\n'
     '    lock.unlock();'),
    ('            present_queue.push_back(frame);',
     '            if (present_failure) return;\n            present_queue.push_back(frame);'),
    ('            present_queue.pop_front();',
     '            present_queue.pop_front();\n            present_in_flight = true;'),
    ('            std::scoped_lock fl{free_mutex};\n'
     '            free_queue.push_back(frame);\n'
     '            free_cv.notify_one();',
     '            {\n'
     '                std::scoped_lock fl{free_mutex};\n'
     '                free_queue.push_back(frame);\n'
     '                free_cv.notify_one();\n'
     '            }\n'
     '            // Publish completion only AFTER presentation and frame handoff.\n'
     '            // Release swapchain mutex before reacquiring queue_mutex.\n'
     '            lock.unlock();\n'
     '            {\n'
     '                std::lock_guard queue_lock{queue_mutex};\n'
     '                present_in_flight = false;\n'
     '            }\n'
     '            frame_cv.notify_all();'),
    ('frame_cv.wait(queue_lock, [this] { return present_queue.empty(); });',
     'frame_cv.wait(queue_lock, [this] { return present_failure || '
     '(present_queue.empty() && !present_in_flight); });\n'
     '        if (present_failure) std::rethrow_exception(present_failure);'),
    # R316 PS5: swapchain and present frame use the SAME VkFormat.
    # When extents already match, vkCmdCopyImage is exact and avoids a
    # redundant filtered blit. Keep the linear blit for actual scaling,
    # and keep non-PS5/upstream behavior unchanged.
    ('    if (blit_supported) {\n        cmdbuf.BlitImage(',
     '    if (blit_supported\n'
     '#ifdef PS5_NATIVE\n'
     '        && (frame->width != extent.width || frame->height != extent.height)\n'
     '#endif\n'
     '    ) {\n        cmdbuf.BlitImage('),

])
# Descriptor buffers: Eden's null buffer (nullDescriptor devices) has device address 0,
# but WriteDescriptorBuffer passed it with the binding's range. RADV then builds a real
# descriptor at GPU address 0; desktop kernels only log the resulting page fault, the PS5
# kills the title (TCP read at VA 0).
# The spec requires a null pAddressInfo (or VK_WHOLE_SIZE) for a null descriptor.
# Development A/B switches for device features (headless/dev_vulkan.h, dev-settings).
adapt('src/video_core/vulkan_common/vulkan_device.cpp', 'vulkan_device.cpp', [
    ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include "dev_vulkan.h"\n#include "performance.h"\n#include "vulkan_pool_capacity.h"'),
    # "Memory in use" for the texture and buffer caches: on the console, the budget less what is
    # left of the pool the CPU shares with the GPU (performance.h, graphics_memory_free).
    ('u64 Device::GetDeviceMemoryUsage() const {\n',
     'namespace {\n'
     '// The largest block of the shared pool that was free when the device was made: about the most\n'
     '// graphics can be given in this session.\n'
     '::Eden::VulkanMemory::PoolCapacityLatch graphics_capacity;\n'
     '}\n\n'
     'u64 Device::GetDeviceMemoryUsage() const {\n'
     '    if (const auto free_memory = ::Eden::Performance::graphics_memory_free.load(std::memory_order_relaxed);\n'
     '        free_memory && ::Eden::Performance::graphics_usage_from_pool.load(std::memory_order_relaxed)) {\n'
     '        // The caches evict what is unused 1.6 GiB under the budget and evict hard 0.8 GiB under\n'
     '        // it. Where the pool could never give graphics 6.4 GiB, those marks become a quarter\n'
     '        // and an eighth of what it could give.\n'
     '        // One existing throttled kernel callback; never probe a second time here.\n'
     '        const u64 observed_free = free_memory();\n'
     '        // A failed initial probe is not permanent zero capacity: accept\n'
     '        // the first later nonzero sample for THIS device lifetime.\n'
     '        const u64 session_capacity = graphics_capacity.Observe(observed_free);\n'
     '        const double scale = session_capacity != 0 && session_capacity < 6400_MiB\n'
     '                                 ? static_cast<double>(6400_MiB) / static_cast<double>(session_capacity)\n'
     '                                 : 1.0;\n'
     '        const u64 free_bytes = static_cast<u64>(static_cast<double>(observed_free) * scale);\n'
     '        return device_access_memory > free_bytes ? device_access_memory - free_bytes : 0;\n'
     '    }\n'),
    ('    extensions.descriptor_buffer = features.descriptor_buffer.descriptorBuffer;',
     '    extensions.descriptor_buffer = features.descriptor_buffer.descriptorBuffer &&\n'
     '        !::Eden::DevVulkan::disable_descriptor_buffer;'),
    ('    features.robustness2.robustBufferAccess2 = VK_FALSE;\n'
     '    features.robustness2.robustImageAccess2 = VK_FALSE;\n'
     '    extensions.robustness_2 = features.robustness2.nullDescriptor;',
     '    if (!::Eden::DevVulkan::robustness2) {\n'
     '        features.robustness2.robustBufferAccess2 = VK_FALSE;\n'
     '        features.robustness2.robustImageAccess2 = VK_FALSE;\n'
     '    }\n'
     '    if (::Eden::DevVulkan::disable_null_descriptor) {\n'
     '        features.robustness2.nullDescriptor = VK_FALSE;\n'
     '    }\n'
     '    extensions.robustness_2 = features.robustness2.nullDescriptor;'),
    ('            (queue_family_properties[*graphics].queueFlags & VK_QUEUE_SPARSE_BINDING_BIT) != 0;',
     '            (queue_family_properties[*graphics].queueFlags & VK_QUEUE_SPARSE_BINDING_BIT) != 0 &&\n'
     '            !::Eden::DevVulkan::disable_sparse;'),
    ('            features.custom_border_color.customBorderColorWithoutFormat;\n    }\n'
     '    RemoveExtensionFeatureIfUnsuitable(extensions.custom_border_color',
     '            features.custom_border_color.customBorderColorWithoutFormat &&\n'
     '            !::Eden::DevVulkan::disable_custom_border;\n    }\n'
     '    RemoveExtensionFeatureIfUnsuitable(extensions.custom_border_color'),
    # dev-settings conditional_rendering=off: guest render-enable conditions are resolved
    # without VK_EXT_conditional_rendering (the path Eden takes on drivers without it).
    ('    // VK_EXT_border_color_swizzle\n',
     '    if (::Eden::DevVulkan::disable_conditional_rendering) {\n'
     '        extensions.conditional_rendering = false;\n    }\n'
     '    // VK_EXT_border_color_swizzle\n'),
    # The heaps and the budget the texture/buffer caches size themselves from.
    ('            device_access_memory = std::min<u64>(device_access_memory, normal_memory + scaler_memory);\n'
     '        }\n    }\n}\n',
     '            device_access_memory = std::min<u64>(device_access_memory, normal_memory + scaler_memory);\n'
     '        }\n    }\n'
     '    const auto free_memory = ::Eden::Performance::graphics_memory_free.load(std::memory_order_relaxed);\n'
     '    // Reset on each new VkDevice, even when a first kernel probe fails.\n'
     '    graphics_capacity.Reset(free_memory ? free_memory() : 0);\n'
     '    std::printf("EDEN_VULKAN_MEMORY integrated=%d heaps=%zu local=%llu initial_usage=%llu device_access=%llu "\n'
     '                "capacity=%llu\\n",\n'
     '                int(is_integrated), valid_heap_memory.size(), static_cast<unsigned long long>(local_memory),\n'
     '                static_cast<unsigned long long>(device_initial_usage),\n'
     '                static_cast<unsigned long long>(device_access_memory),\n'
     '                static_cast<unsigned long long>(graphics_capacity.Value()));\n}\n'),
])
# Development GPU fault probe (dev_vulkan.h, submit_sync=on): wait for every
# submission, so the CPU never records against work the GPU has not finished.
GPU_TIME_HELPERS = r'''
namespace {
// Development GPU execution time (dev_vulkan.h gpu_time): timestamps at the start and end
// of every scheduler command buffer, summed once the GPU has run them and printed every
// 5 s as EDEN_GPU_TIME. Worker thread only.
struct GpuTimeProbe {
    static constexpr u32 SLOTS = 512;
    vk::QueryPool pool;
    PFN_vkCmdWriteTimestamp write{};
    double period_ns{};
    u64 next{}, first_pending{};
    u64 session{};  // reset before first command of a new VkDevice/title
    u32 current{};
    u64 busy_ns{}, max_ns{}, submissions{};
    std::chrono::steady_clock::time_point report{};
    bool failed{};
} gpu_time;

void GpuTimeBegin(const Device& device, vk::CommandBuffer cmdbuf) {
    if (!::Eden::DevVulkan::gpu_time) return;
    const u64 session = ::Eden::DevVulkan::gpu_time_session.load(std::memory_order_acquire);
    if (gpu_time.session != session) {
        // Previous VkDevice teardown implicitly destroyed its query pool.
        // The process-global probe must discard that device's handle, counters
        // and failures before any query on the next title can be recorded.
        gpu_time = GpuTimeProbe{};
        gpu_time.session = session;
    }
    if (gpu_time.failed) return;
    if (!gpu_time.write) {
        const auto& dld = device.GetDispatchLoader();
        gpu_time.write = reinterpret_cast<PFN_vkCmdWriteTimestamp>(
            dld.vkGetDeviceProcAddr(*device.GetLogical(), "vkCmdWriteTimestamp"));
        gpu_time.period_ns = device.GetPhysical().GetProperties().limits.timestampPeriod;
        if (!gpu_time.write || gpu_time.period_ns <= 0) { gpu_time.failed = true; return; }
        gpu_time.pool = device.GetLogical().CreateQueryPool({
            .sType = VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO,
            .pNext = nullptr,
            .flags = 0,
            .queryType = VK_QUERY_TYPE_TIMESTAMP,
            .queryCount = GpuTimeProbe::SLOTS * 2,
            .pipelineStatistics = 0,
        });
        gpu_time.report = std::chrono::steady_clock::now();
    }
    if (gpu_time.next - gpu_time.first_pending >= GpuTimeProbe::SLOTS) {
        gpu_time.failed = true; // results stopped arriving; never overwrite a pending slot
        std::printf("EDEN_GPU_TIME failed=ring\n");
        return;
    }
    gpu_time.current = static_cast<u32>(gpu_time.next++ % GpuTimeProbe::SLOTS);
    cmdbuf.ResetQueryPool(*gpu_time.pool, gpu_time.current * 2, 2);
    gpu_time.write(*cmdbuf, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, *gpu_time.pool, gpu_time.current * 2);
}

void GpuTimeEnd(vk::CommandBuffer cmdbuf) {
    if (!::Eden::DevVulkan::gpu_time || gpu_time.failed || !gpu_time.write) return;
    gpu_time.write(*cmdbuf, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, *gpu_time.pool, gpu_time.current * 2 + 1);
}

void GpuTimeCollect(const Device& device) {
    if (!::Eden::DevVulkan::gpu_time || gpu_time.failed || !gpu_time.write) return;
    while (gpu_time.first_pending + 1 < gpu_time.next) {
        const u32 slot = static_cast<u32>(gpu_time.first_pending % GpuTimeProbe::SLOTS);
        std::array<u64, 2> stamps{};
        if (device.GetLogical().GetQueryResults(*gpu_time.pool, slot * 2, 2, sizeof(stamps), stamps.data(),
                                               sizeof(u64), VK_QUERY_RESULT_64_BIT) != VK_SUCCESS) break;
        const u64 ns = stamps[1] > stamps[0]
                           ? static_cast<u64>(double(stamps[1] - stamps[0]) * gpu_time.period_ns) : 0;
        gpu_time.busy_ns += ns;
        gpu_time.max_ns = (std::max)(gpu_time.max_ns, ns);
        ++gpu_time.submissions;
        ++gpu_time.first_pending;
    }
    const auto now = std::chrono::steady_clock::now();
    const auto wall = std::chrono::duration_cast<std::chrono::nanoseconds>(now - gpu_time.report).count();
    if (wall >= 5'000'000'000) {
        std::printf("EDEN_GPU_TIME wall_ms=%.1f busy_ms=%.1f submissions=%llu max_ms=%.2f\n", wall / 1e6,
                    gpu_time.busy_ns / 1e6, static_cast<unsigned long long>(gpu_time.submissions),
                    gpu_time.max_ns / 1e6);
        gpu_time.busy_ns = gpu_time.max_ns = gpu_time.submissions = 0;
        gpu_time.report = now;
    }
}

// VkQueryPool is a device child. It must be destroyed explicitly while the
// owner VkDevice remains live (not forgotten when the next title begins).
void GpuTimeDestroy(const Device& device) {
    if (!gpu_time.pool) return;
    const auto& dld = device.GetDispatchLoader();
    const VkDevice handle = *device.GetLogical();
    (void)dld.vkDeviceWaitIdle(handle);
    dld.vkDestroyQueryPool(handle, *gpu_time.pool, nullptr);
    gpu_time = GpuTimeProbe{};
}
} // namespace
'''
adapt('src/video_core/renderer_vulkan/vk_scheduler.cpp', 'vulkan_scheduler.cpp', [
    ('#include <memory>', '#include <memory>\n#include <array>\n#include <chrono>\n#include <cstdio>\n#include "dev_vulkan.h"'),
    ('namespace Vulkan {\n', 'namespace Vulkan {\n' + GPU_TIME_HELPERS),
    # The default destructor joins worker_thread only AFTER its body. If a
    # dev timestamp probe created a query pool, join before destroying it.
    ('Scheduler::~Scheduler() = default;',
     '''Scheduler::~Scheduler() {
    // The worker writes gpu_time.pool. Do not test that field until the
    // worker has stopped: the old conditional check raced with its first
    // CreateQueryPool on a quick title exit, risking use-after-free.
    worker_thread.request_stop();
    event_cv.notify_all();
    if (worker_thread.joinable()) worker_thread.join();
    if (gpu_time.pool) GpuTimeDestroy(device);
}'''),
    ('        .pInheritanceInfo = nullptr,\n    });\n    current_upload_cmdbuf = vk::CommandBuffer(command_pool->Commit(), device.GetDispatchLoader());',
     '        .pInheritanceInfo = nullptr,\n    });\n    GpuTimeBegin(device, current_cmdbuf);\n'
     '    current_upload_cmdbuf = vk::CommandBuffer(command_pool->Commit(), device.GetDispatchLoader());'),
    ('        upload_cmdbuf.End();\n        cmdbuf.End();\n',
     '        upload_cmdbuf.End();\n        GpuTimeEnd(cmdbuf);\n        cmdbuf.End();\n'),
    ('            vk::Check(result);\n            break;\n        }\n    });\n    chunk->MarkSubmit();',
     '            vk::Check(result);\n            break;\n        }\n        GpuTimeCollect(device);\n    });\n    chunk->MarkSubmit();'),
    ('    const u64 signal_value = SubmitExecution(signal_semaphore, wait_semaphore);\n'
     '    AllocateNewContext();\n    return signal_value;',
     '    const u64 signal_value = SubmitExecution(signal_semaphore, wait_semaphore);\n'
     '    if (::Eden::DevVulkan::sync_submissions) {\n        Wait(signal_value);\n    }\n'
     '    AllocateNewContext();\n    return signal_value;'),
])
adapt('src/video_core/renderer_vulkan/pipeline_helper.h',
      'include/video_core/renderer_vulkan/pipeline_helper.h', [
    ('            VkDescriptorGetInfoEXT get_info{',
     '            const VkDescriptorAddressInfoEXT* const buffer_info{\n'
     '                entry.address.address != 0 ? &address_info : nullptr};\n'
     '            VkDescriptorGetInfoEXT get_info{'),
    ('get_info.data.pUniformBuffer = &address_info;', 'get_info.data.pUniformBuffer = buffer_info;'),
    ('get_info.data.pStorageBuffer = &address_info;', 'get_info.data.pStorageBuffer = buffer_info;'),
    ('get_info.data.pUniformTexelBuffer = &address_info;', 'get_info.data.pUniformTexelBuffer = buffer_info;'),
    ('get_info.data.pStorageTexelBuffer = &address_info;', 'get_info.data.pStorageTexelBuffer = buffer_info;'),
])
adapt('src/video_core/renderer_vulkan/vk_blit_screen.h',
      'include/video_core/renderer_vulkan/vk_blit_screen.h', [
    ('VkFormat current_swapchain_view_format);',
     'VkFormat current_swapchain_view_format, bool draw_hud = false);'),
])
adapt('src/video_core/renderer_vulkan/renderer_vulkan.h',
      'include/video_core/renderer_vulkan/renderer_vulkan.h', [
    ('    void Composite(', '    void PresentLoading();\n    void Composite('),
])
adapt('src/video_core/renderer_vulkan/renderer_vulkan.cpp', 'vulkan_renderer.cpp', [
    ('#include "video_core/renderer_vulkan/renderer_vulkan.h"',
     '#include "video_core/renderer_vulkan/renderer_vulkan.h"\n#include "display_refresh.h"'),
    # A frame the display has no refresh for is not presented: a game patched for more frames
    # than the output shows keeps its pace instead of waiting for a refresh per frame
    # (headless/display_refresh.h). The frame still ends as any other.
    ('    RenderScreenshot(framebuffers);\n    Frame* frame = present_manager.GetRenderFrame();',
     '    RenderScreenshot(framebuffers);\n'
     '    if (::Eden::Display::SkipFrame()) {\n'
     '        gpu.RendererFrameEndNotify();\n'
     '        rasterizer.TickFrame();\n'
     '        return;\n'
     '    }\n'
     '    Frame* frame = present_manager.GetRenderFrame();'),
    ('    Report();', '    PresentLoading();\n    Report();'),
    # The graphics worker must not read mutable swapchain dimensions/format
    # directly while the background present worker can call RecreateSwapchain.
    ('render_window.GetFramebufferLayout(), swapchain.GetImageCount(),',
     'render_window.GetFramebufferLayout(), present_manager.SwapchainImageCount(),'),
    ('frame_gen.Process(device, frame, swapchain.GetImageFormat(), GuestExtent(framebuffers));',
     'frame_gen.Process(device, frame, present_manager.SwapchainImageFormat(), GuestExtent(framebuffers));'),
    ('swapchain.GetImageViewFormat());', 'present_manager.SwapchainImageViewFormat(), true);'),
    ('layout, 1, format);', 'layout, 1, format, true);'),
    ('void RendererVulkan::Report() const {',
     (port / 'vulkan_loading.inc').read_text() + '\nvoid RendererVulkan::Report() const {'),
    # Present() only records the hand-off into a fresh chunk. Dispatch it now so
    # the present thread gets this frame immediately instead of after the
    # producer's next 8-draw dispatch (upstream does this only with LSFG).
    ('    present_manager.Present(frame);\n#ifdef HAS_LSFG\n    scheduler.DispatchWork();\n#endif',
     '    present_manager.Present(frame);\n    scheduler.DispatchWork();'),
    ('} // namespace Vulkan', '''} // namespace Vulkan
namespace Eden {
void PresentVulkanLoading(VideoCore::RendererBase& renderer) {
    static_cast<Vulkan::RendererVulkan&>(renderer).PresentLoading();
}
}'''),
])
adapt('src/video_core/renderer_vulkan/present/window_adapt_pass.h',
      'include/video_core/renderer_vulkan/present/window_adapt_pass.h', [
    ('const Layout::FramebufferLayout& layout, Frame* dst);',
     'const Layout::FramebufferLayout& layout, Frame* dst, bool draw_hud = false);'),
    ('    vk::Pipeline coverage_pipeline;',
     '    vk::Pipeline coverage_pipeline;\n    vk::PipelineLayout hud_layout;\n    vk::Pipeline hud_pipeline;'),
])
adapt('src/video_core/renderer_vulkan/present/window_adapt_pass.cpp', 'vulkan_window_adapt_pass.cpp', [
    ('#include "core/frontend/framebuffer_layout.h"',
     '#include "core/frontend/framebuffer_layout.h"\n#include "hud.h"\n#include "vulkan_hud_shaders.h"'),
    ('const Layout::FramebufferLayout& layout, Frame* dst) {',
     'const Layout::FramebufferLayout& layout, Frame* dst, bool draw_hud) {'),
    ('    scheduler.Record([=](vk::CommandBuffer cmdbuf) {',
     (port / 'vulkan_hud_prepare.inc').read_text() + '\n    scheduler.Record([=](vk::CommandBuffer cmdbuf) {'),
    ('        cmdbuf.EndRenderPass();',
     (port / 'vulkan_hud_draw.inc').read_text() + '\n        cmdbuf.EndRenderPass();'),
])
# R328: Framebuffer dimension / format changes and runtime antialias setting
# changes can destroy old FXAA/SMAA images and descriptors with GPU work still
# in flight. The raw-image resource ticks are waited *after* emplace today,
# too late for the AA variant. Drain only if an AA pass actually exists.
# Do not impose idle waits on normal draws or when the filter is disabled.
adapt('src/video_core/renderer_vulkan/present/layer.cpp', 'vulkan_present_layer.cpp', [
    # R331: ReleaseRawImages destroys the VkImage before the VkImageView(s)
    # which reference it. Vulkan images must outlive their views. Free each
    # view first, then the image; this is used on resize and Layer destruction.
    ('    raw_images.clear();\n    buffer.reset();',
     '    raw_image_views.clear();\n    raw_images.clear();\n    buffer.reset();'),
    # R329: the staging buffer has exactly ci.size mapped bytes (pinned VMA
    # allocator), and that size depends on framebuffer STRIDE as well as the
    # visible extent/format. A same-size framebuffer with a different stride
    # must reallocate, or UpdateRawImage's subspan can exceed the buffer.
    # R330: for a pitch-only change, replace ONLY the upload buffer after
    # per-image tick waits; preserve AA resources and avoid vkDeviceWaitIdle.
    ('        framebuffer.pixel_format == pixel_format && !raw_images.empty()) {\n'
     '        return;\n    }',
     '''        framebuffer.pixel_format == pixel_format && !raw_images.empty() &&
        buffer.Mapped().size() == CalculateBufferSize(framebuffer)) {
        return;
    }
#ifdef PS5_NATIVE
    // Same dimensions and format, but the guest row pitch changed. Recycle
    // only the upload buffer after its last referenced GPU tick; AA images,
    // descriptors, renderpasses and pipelines remain valid. Do NOT trigger
    // a full-device WaitIdle or recreate the FXAA/SMAA pass on pitch changes.
    if (framebuffer.width == raw_width && framebuffer.height == raw_height &&
        framebuffer.pixel_format == pixel_format && !raw_images.empty()) {
        for (const u64 tick : resource_ticks) {
            scheduler.Wait(tick);
        }
        CreateStagingBuffer(device, framebuffer);
        return;
    }
#endif'''),
    ('    pixel_format = framebuffer.pixel_format;\n'
     '    anti_alias.emplace<std::monostate>();\n\n'
     '    ReleaseRawImages();',
     '''    pixel_format = framebuffer.pixel_format;
#ifdef PS5_NATIVE
    if (!std::holds_alternative<std::monostate>(anti_alias)) {
        // Existing FXAA/SMAA images and descriptors may still be referenced
        // by command buffers submitted for prior presentation frames.
        scheduler.Finish();
        device.GetLogical().WaitIdle();
    }
#endif
    anti_alias.emplace<std::monostate>();

    ReleaseRawImages();'''),
    ('    anti_alias_setting = filters.get_anti_aliasing();\n\n'
     '    const VkExtent2D render_area{',
     '''#ifdef PS5_NATIVE
    if (!std::holds_alternative<std::monostate>(anti_alias)) {
        // Swapping the AA variant frees GPU resources, not just host state.
        scheduler.Finish();
        device.GetLogical().WaitIdle();
    }
#endif
    anti_alias_setting = filters.get_anti_aliasing();

    const VkExtent2D render_area{'''),
])

adapt('src/video_core/renderer_vulkan/vk_blit_screen.cpp', 'vulkan_blit_screen.cpp', [
    # R327: a change in the number of guest presentation layers destroys
    # the prior descriptors, FSR/FXAA images, and views. The ordinary window
    # reconfiguration waits for outstanding GPU work, but this resize path
    # previously cleared layers immediately. Drain only when removing live
    # layers, never on steady frames or initial construction.
    ('    if (layers.size() != framebuffers.size()) {\n        layers.clear();',
     '''    if (layers.size() != framebuffers.size()) {
#ifdef PS5_NATIVE
        if (!layers.empty()) {
            // Old layer resources can still be in queued Vulkan draws.
            WaitIdle(device);
        }
#endif
        layers.clear();'''),
    ('VkFormat current_swapchain_view_format) {',
     'VkFormat current_swapchain_view_format, bool draw_hud) {'),
    ('image_index, layers, framebuffers, layout, frame);',
     'image_index, layers, framebuffers, layout, frame, draw_hud);'),
])
shader_header = '#pragma once\n#include <cstdint>\n'
for stage in ('vert', 'frag'):
    binary = output / f'vulkan_hud.{stage}.spv'
    subprocess.run(['glslangValidator', '-V', '--target-env', 'vulkan1.0',
                    '-o', str(binary), str(port / f'vulkan_hud.{stage}')], check=True)
    subprocess.run(['spirv-val', '--target-env', 'vulkan1.0', str(binary)], check=True)
    data = binary.read_bytes()
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    shader_header += f'inline constexpr uint32_t EDEN_HUD_{stage.upper()}_SPV[] = {{\n'
    shader_header += ','.join(hex(word) for word in words) + '\n};\n'
path = output / 'vulkan_hud_shaders.h'
if not path.exists() or path.read_text() != shader_header:
    path.write_text(shader_header)
adapt('src/video_core/vulkan_common/vulkan.h', 'include/video_core/vulkan_common/vulkan.h',
      [('#else\n#define VK_USE_PLATFORM_XLIB_KHR', '#elif defined(PS5_NATIVE)\n// Native display-plane presentation, no desktop window-system headers.\n#else\n#define VK_USE_PLATFORM_XLIB_KHR')])
adapt('src/video_core/vulkan_common/vulkan_instance.cpp', 'vulkan_instance.cpp', [
    ('namespace Vulkan {', 'extern "C" VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetInstanceProcAddr(VkInstance, const char*);\n\nnamespace Vulkan {'),
    ('    case Core::Frontend::WindowSystemType::Headless:', '    case Core::Frontend::WindowSystemType::PS5:\n        extensions.push_back(VK_KHR_DISPLAY_EXTENSION_NAME);\n        break;\n    case Core::Frontend::WindowSystemType::Headless:'),
    ('#else\n    case Core::Frontend::WindowSystemType::X11:', '#elif !defined(PS5_NATIVE)\n    case Core::Frontend::WindowSystemType::X11:'),
    ('''    if (!library.IsOpen()) {
        LOG_ERROR(Render_Vulkan, "Vulkan library not available");
        throw vk::Exception(VK_ERROR_INITIALIZATION_FAILED);
    }
    if (!library.GetSymbol("vkGetInstanceProcAddr", &dld.vkGetInstanceProcAddr)) {
        LOG_ERROR(Render_Vulkan, "vkGetInstanceProcAddr not present in Vulkan");
        throw vk::Exception(VK_ERROR_INITIALIZATION_FAILED);
    }''', '    (void)library;\n    dld.vkGetInstanceProcAddr = &::vkGetInstanceProcAddr;'),
])
adapt('src/video_core/vulkan_common/vulkan_library.cpp', 'vulkan_library.cpp', [
    ('#if defined(__ANDROID__) && defined(ARCHITECTURE_arm64)', '#if defined(PS5_NATIVE)\n    return std::make_shared<Common::DynamicLibrary>();\n#elif defined(__ANDROID__) && defined(ARCHITECTURE_arm64)'),
])
adapt('src/video_core/vulkan_common/vulkan_wrapper.h', 'include/video_core/vulkan_common/vulkan_wrapper.h', [
    ('#include <array>', '#include <array>\n#include <cstdio>\n#include "performance.h"'),
    ('return dld->vkQueueSubmit(queue,', 'auto timer = Eden::Performance::VulkanTimer(2);\n        return dld->vkQueueSubmit(queue,'),
    ('return dld->vkQueueSubmit2(queue,', 'auto timer = Eden::Performance::VulkanTimer(2);\n        return dld->vkQueueSubmit2(queue,'),
    ('return dld->vkWaitForFences(owner,', 'auto timer = Eden::Performance::VulkanTimer(3);\n        return dld->vkWaitForFences(owner,'),
    ('const VkResult result = dld->vkWaitSemaphores(owner,', 'auto timer = Eden::Performance::VulkanTimer(4);\n        const VkResult result = dld->vkWaitSemaphores(owner,'),
    ('return dld->vkDeviceWaitIdle(handle);', 'auto timer = Eden::Performance::VulkanTimer(5);\n        return dld->vkDeviceWaitIdle(handle);'),
    ('''inline void Check(VkResult result) {
    if (result != VK_SUCCESS) {
        throw Exception(result);''', '''inline void Check(VkResult result, const char* file = __builtin_FILE(),
                  int line = __builtin_LINE(), const char* operation = __builtin_FUNCTION()) {
    if (result != VK_SUCCESS) {
        std::fprintf(stderr, "[ProsperoEden] Vulkan failure: %s:%d (%s) VkResult=%d\\n",
                     file, line, operation, static_cast<int>(result));
        throw Exception(result);'''),
])
adapt('src/video_core/vulkan_common/vulkan_wrapper.cpp', 'vulkan_wrapper.cpp', [
    ('#include "video_core/vulkan_common/vulkan_wrapper.h"', '#include "video_core/vulkan_common/vulkan_wrapper.h"\n#include "performance.h"'),
    ('auto const result = dld->vkCreateGraphicsPipelines(', 'auto timer = Eden::Performance::VulkanTimer(0);\n    auto const result = dld->vkCreateGraphicsPipelines('),
    ('Check(dld->vkCreateComputePipelines(', 'auto timer = Eden::Performance::VulkanTimer(1);\n    Check(dld->vkCreateComputePipelines('),
])
download_source = (source / 'src/video_core/texture_cache/texture_cache.h').read_text()
download_begin = download_source.index('void TextureCache<P>::DownloadMemory(DAddr cpu_addr, size_t size)')
download_loop = download_source.index('    for (const ImageId image_id : images) {', download_begin)
download_prefix = download_source[download_begin:download_loop]
# Reuse DeleteImage's exact accounting to stop lookahead when its existing
# pressure policy changes. Fail on source drift rather than inventing a budget.
delete_begin = download_source.index('    if (image.HasScaled()) {', download_source.index('void TextureCache<P>::DeleteImage('))
delete_end = download_source.index('    const GPUVAddr gpu_addr', delete_begin)
reclaimed_bytes = download_source[delete_begin:delete_end].replace('total_used_memory -=', 'bytes +=')
gc_begin = download_source.index('void TextureCache<P>::RunGarbageCollector() {')
gc_end = download_source.index('\ntemplate <class P>', gc_begin)
gc_original = download_source[gc_begin:gc_end]
gc = gc_original
gc_setup = '''    const auto ReclaimedBytes = [&](const ImageBase& image) {
        u64 bytes = 0;
''' + reclaimed_bytes + '''        return bytes;
    };
''' + (port / 'vulkan_gc_downloads.inc').read_text()
for old, new in [
    ('    const auto Cleanup = [this, &num_iterations, &high_priority_mode, &aggressive_mode]',
     gc_setup + '\n    const auto Cleanup = [&, this]'),
    ('        if (must_download) {', '        if (must_download && !UsePrefetched(image_id, image)) {'),
    ('(!high_priority_mode && must_download)) {', '(!DirtyEvictions() && must_download)) {'),
    ('    Configure(false);', '    Configure(false);\n    PrefetchDownloads();'),
    ('        Configure(true);', '        Configure(true);\n        PrefetchDownloads();'),
]:
    if gc.count(old) != 1:
        raise RuntimeError(f'Pinned GC anchor changed: {old}')
    gc = gc.replace(old, new)
# Upstream u64 frame_tick starts at zero and subtracts ages 10/25/50.
# It relied on unsigned wrap plus the pinned LRU signed comparison as an
# accidental startup grace period. Replace with a saturated cutoff and
# explicit age guards for both cleanup passes and Vulkan prefetch.
unsafe_cutoff = "frame_tick - ticks_to_destroy"
if gc.count(unsafe_cutoff) != 3:
    raise RuntimeError("Pinned GC needs three safe LRU cutoffs: prefetch and both cleanup passes")
gc = gc.replace(unsafe_cutoff,
                "::Eden::VulkanMemory::OldestEvictionTick(frame_tick, ticks_to_destroy)")
# The pinned LeastRecentlyUsedCache::ForEachItemBelow uses an inclusive
# comparison. Passing a saturated zero WITHOUT a guard would evict textures
# created at frame 0! Wait for the requested age before touching any entries.
cleanup_cutoff = ("    lru_cache.ForEachItemBelow("
                  "::Eden::VulkanMemory::OldestEvictionTick(frame_tick, ticks_to_destroy), Cleanup);")
if gc.count(cleanup_cutoff) != 2:
    raise RuntimeError("Pinned GC must preserve both cleanup passes")
gc = gc.replace(cleanup_cutoff,
                "    if (frame_tick >= ticks_to_destroy) {\n"
                "        lru_cache.ForEachItemBelow("
                "::Eden::VulkanMemory::OldestEvictionTick(frame_tick, ticks_to_destroy), Cleanup);\n"
                "    }")
texture_costs = []
for signature, index in (
    ('RunGarbageCollector()', 13), ('DownloadMemory(DAddr cpu_addr, size_t size)', 14),
    ('PopAsyncFlushes()', 15),
):
    anchor = f'void TextureCache<P>::{signature} {{'
    scope = f'''
    std::optional<Eden::Performance::Timer> cost_timer;
    if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {{
        if (Eden::Performance::vulkan_cost_enabled.load(std::memory_order_relaxed))
            cost_timer.emplace(Eden::Performance::vulkan_api[{index}]);
    }}
'''
    if index == 13:
        scope += '''    if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {
        if ((cost_timer || Eden::Performance::texture_budget_log.load(std::memory_order_relaxed)) &&
            frame_tick % 300 == 0)
            std::printf("EDEN_VULKAN_TEXTURE_BUDGET frame=%llu usage=%llu expected=%llu critical=%llu "
                        "keep_dirty=%d memory_short=%d\\n",
                        static_cast<unsigned long long>(frame_tick),
                        static_cast<unsigned long long>(total_used_memory),
                        static_cast<unsigned long long>(expected_memory),
                        static_cast<unsigned long long>(critical_memory),
                        int(Eden::Performance::gc_keep_dirty.load(std::memory_order_relaxed)),
                        int(Eden::Performance::graphics_memory_short.load(std::memory_order_relaxed)));
    }
'''
    texture_costs.append((anchor, anchor + scope))
# R322: the old 1440p samples showed FillImageViews long outliers but
# could not attribute them to CPU image upload, alias scanning, or copying.
# Profile only if the R310 sampled draw TLS flag is true. The standard
# non-diagnostic code makes no clock reads and changes no image semantics.
texture_costs.extend([
    ('    image.flags &= ~ImageFlagBits::CpuModified;\n\n    TrackImage(image, image_id);',
     '#ifdef PS5_NATIVE\n'
     '    ::Eden::Performance::CachePhaseTimer upload_phase{\n'
     '        ::Eden::Performance::CachePhase::TextureCpuRefresh};\n'
     '#endif\n'
     '    image.flags &= ~ImageFlagBits::CpuModified;\n\n    TrackImage(image, image_id);'),
    ('    bool any_rescaled = True(image.flags & ImageFlagBits::Rescaled);\n'
     '    bool any_modified = True(image.flags & ImageFlagBits::GpuModified);',
     '#ifdef PS5_NATIVE\n'
     '    ::Eden::Performance::CachePhaseTimer alias_scan_phase{\n'
     '        ::Eden::Performance::CachePhase::TextureAliasScan};\n'
     '#endif\n'
     '    bool any_rescaled = True(image.flags & ImageFlagBits::Rescaled);\n'
     '    bool any_modified = True(image.flags & ImageFlagBits::GpuModified);'),
    ('    if (aliased_images.empty()) {\n'
     '        return;\n'
     '    }\n'
     '    const bool can_rescale = ImageCanRescale(image);',
     '    if (aliased_images.empty()) {\n'
     '        return;\n'
     '    }\n'
     '#ifdef PS5_NATIVE\n'
     '    alias_scan_phase.Stop();\n'
     '    ::Eden::Performance::CachePhaseTimer alias_copy_phase{\n'
     '        ::Eden::Performance::CachePhase::TextureAliasCopy};\n'
     '#endif\n'
     '    const bool can_rescale = ImageCanRescale(image);'),
])
adapt('src/video_core/texture_cache/texture_cache.h',
      'vulkan-cache/video_core/texture_cache/texture_cache.h', [
    ('namespace VideoCommon {', '#include "performance.h"\n#include "vulkan_gc_budget.h"\n#include "common/scope_exit.h"\nnamespace Vulkan { class TextureCacheRuntime; }\n\nnamespace VideoCommon {'),
    (download_prefix, download_prefix + (port / 'vulkan_download_batch.inc').read_text() + '\n'),
    (gc_original, gc),
    # Vulkan's total_used_memory may be a driver-reported snapshot rather than
    # the exact sum of per-image logical costs. Never allow a DeleteImage
    # subtraction to wrap u64 into enormous phantom VRAM pressure. OpenGL's
    # accounting remains unchanged.
    ('total_used_memory -= GetScaledImageSizeBytes(image);',
     'if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {\n'
     '            total_used_memory = ::Eden::VulkanMemory::AfterProjectedEviction(\n'
     '                total_used_memory, GetScaledImageSizeBytes(image));\n'
     '        } else {\n'
     '            total_used_memory -= GetScaledImageSizeBytes(image);\n'
     '        }'),
    ('total_used_memory -= Common::AlignUp(tentative_size, 1024);',
     'if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {\n'
     '        total_used_memory = ::Eden::VulkanMemory::AfterProjectedEviction(\n'
     '            total_used_memory, Common::AlignUp(tentative_size, 1024));\n'
     '    } else {\n'
     '        total_used_memory -= Common::AlignUp(tentative_size, 1024);\n'
     '    }'),
    # RADV reports all Vulkan allocations, not just cached textures. A game's
    # measured ~1.9 GiB working set triggered dirty eviction at the old 1.6 GiB
    # threshold despite a 4 GiB budget. Retain 40% headroom; keep the original
    # critical threshold and minimum 1 GiB spacing. OpenGL remains unchanged.
    ('const s64 min_vacancy_expected = (6 * mem_threshold) / 10;',
     'const s64 min_vacancy_expected =\n            ((std::is_same_v<Runtime, Vulkan::TextureCacheRuntime> ? 4 : 6) * mem_threshold) / 10;'),
] + texture_costs)

# R323 PS5: the Vulkan descriptor ring can call scheduler.Wait(previous
# frame tick) inside ConfigureDraw while BOTH rasterizer cache mutexes are
# held. Pre-drain that SAME frame fence before the locks only for graphics
# pipelines with descriptor-buffer payloads. No change to over-capacity GPU
# Finish fallback or to the original Allocate memory-ordering checks.
adapt('src/video_core/renderer_vulkan/vk_descriptor_buffer.h',
      'include/video_core/renderer_vulkan/vk_descriptor_buffer.h', [
    ('    void TouchFrame(Scheduler& scheduler);',
     '    void TouchFrame(Scheduler& scheduler);\n'
     '#ifdef PS5_NATIVE\n'
     '    [[nodiscard]] bool PreflightFrameReuse(Scheduler& scheduler);\n'
     '#endif'),
])
adapt('src/video_core/renderer_vulkan/vk_descriptor_buffer.cpp',
      'vulkan_descriptor_buffer.cpp', [
    ('void DescriptorBufferRing::TouchFrame(Scheduler& scheduler) {\n'
     '    frame_ticks[frame_index] = scheduler.CurrentTick();\n'
     '}',
     '''void DescriptorBufferRing::TouchFrame(Scheduler& scheduler) {
    frame_ticks[frame_index] = scheduler.CurrentTick();
}
#ifdef PS5_NATIVE
bool DescriptorBufferRing::PreflightFrameReuse(Scheduler& scheduler) {
    // This is the GPU-owner thread, called before the paired buffer/texture
    // cache locks. Reuse the EXACT previous-frame tick the Allocate fallback
    // would wait for; preserve fallback in case no preflight ran.
    if (!frame_reused || chunks.empty())
        return false;
    scheduler.Wait(frame_ticks[frame_index]);
    frame_reused = false;
    return true;
}
#endif'''),
])

# R313: adapt the original graphics pipeline ABI so the fast-first object
# owns both a valid first-use handle and a finished optimized Vulkan handle.
# No preloaded disk pipelines are rebuilt: the constructor's worker_thread
# is null for those. OptimizeState is allocated lazily, not per cached pipeline.
adapt('src/video_core/renderer_vulkan/vk_graphics_pipeline.h',
      'include/video_core/renderer_vulkan/vk_graphics_pipeline.h', [
    ('    GraphicsPipeline(const GraphicsPipeline&) = delete;',
     '    GraphicsPipeline(const GraphicsPipeline&) = delete;\n    ~GraphicsPipeline();'),
    ('    void MakePipeline(VkRenderPass render_pass);',
     '    void MakePipeline(VkRenderPass render_pass, VkPipelineCreateFlags extra_flags = 0,\n'
     '                      vk::Pipeline* target = nullptr);\n'
     '    void QueueOptimizedPipeline(VkRenderPass render_pass);'),
    ('    vk::Pipeline pipeline;',
     '    vk::Pipeline pipeline;\n'
     '    struct OptimizeState {\n'
     '        std::mutex mutex;\n'
     '        std::condition_variable done;\n'
     '        bool cancelled{false};\n'
     '        bool running{false};\n'
     '    };\n'
     '    std::shared_ptr<OptimizeState> optimize_state; // allocated ONLY for active R313 builds\n'
     '    vk::Pipeline optimized_pipeline;\n'
     '    std::atomic_bool optimized_ready{false};'),
    # Guard pre-drain to pipelines that can actually allocate descriptors.
    ('    bool HasDynamicVertexInput() const noexcept { return key.state.dynamic_vertex_input; }',
     '    bool HasDynamicVertexInput() const noexcept { return key.state.dynamic_vertex_input; }\n'
     '#ifdef PS5_NATIVE\n'
     '    [[nodiscard]] bool CanUseDescriptorBuffer() const noexcept {\n'
     '        return uses_descriptor_buffer && descriptor_set_layout;\n'
     '    }\n'
     '    [[nodiscard]] size_t DescriptorEntryReservation() const noexcept {\n'
     '        return num_descriptor_entries != 0 ? num_descriptor_entries : 0x400;\n'
     '    }\n'
     '#endif'),
    ('#include <atomic>', '#include <atomic>\n#include <memory>'),
])

# Adapted from Mihawk PS5 fast-first pipelines with important corrections:
# * one optimizer worker to avoid contending with guest JIT cores
# * only runtime-discovered pipelines, not preloaded disk cache entries
# * no illegal VulkanTimer(24): timing array has 24 entries, indexed 0..23
# * lazy state so optimized baseline and disk-loaded pipelines add no heap work
# * cancellation is checked BEFORE touching an asynchronously destroyed pipeline
optimize_worker = """
namespace {
Common::ThreadWorker& OptimizeWorker() {
    static Common::ThreadWorker worker(1, "VkPipelineOptimize");
    return worker;
}
} // namespace

GraphicsPipeline::~GraphicsPipeline() {
    const auto state = optimize_state;
    if (!state) return;
    std::unique_lock lock{state->mutex};
    state->cancelled = true;
    state->done.wait(lock, [&] { return !state->running; });
}

void GraphicsPipeline::QueueOptimizedPipeline(VkRenderPass render_pass) {
    optimize_state = std::make_shared<OptimizeState>();
    const auto state = optimize_state;
    OptimizeWorker().QueueWork([this, state, render_pass] {
        {
            std::scoped_lock lock{state->mutex};
            if (state->cancelled) return;
            state->running = true;
        }
        try {
            MakePipeline(render_pass, 0, &optimized_pipeline);
            optimized_ready.store(true, std::memory_order_release);
        } catch (const std::exception& exception) {
            // Keep the already-built, valid first-use pipeline after any
            // optimization failure. Completion must always release shutdown.
            LOG_WARNING(Render_Vulkan, "Optimized pipeline rebuild failed: {}", exception.what());
        } catch (...) {
            LOG_WARNING(Render_Vulkan, "Optimized pipeline rebuild failed: unknown exception");
        }
        {
            std::scoped_lock lock{state->mutex};
            state->running = false;
        }
        state->done.notify_all();
    });
}

void GraphicsPipeline::MakePipeline(VkRenderPass render_pass, VkPipelineCreateFlags extra_flags,
                                    vk::Pipeline* target) {"""

# These costs sit outside vkCreateGraphicsPipelines: guest shader translation,
# worker readiness, and background serialization can block different threads.
for name in ('vk_graphics_pipeline', 'vk_compute_pipeline'):
    replacements = [
        ('#include <algorithm>', '#include <algorithm>\n#include "performance.h"'),
        ('            std::unique_lock lock{build_mutex};',
         '            auto timer = Eden::Performance::VulkanTimer(16);\n            std::unique_lock lock{build_mutex};'),
    ]
    if name == 'vk_graphics_pipeline':
        replacements.extend([
            ('#include <algorithm>',
             '#include <algorithm>\n#include <exception>\n#include "common/thread_worker.h"\n#include "dev_vulkan.h"'),
            ('auto func{[this, shader_notify, &render_pass_cache, pipeline_statistics] {',
             'auto func{[this, shader_notify, &render_pass_cache, pipeline_statistics, '
             'fast_first_runtime = (worker_thread != nullptr)] {'),
            ('            MakePipeline(render_pass);',
             '            if (::Eden::DevVulkan::fast_first_pipelines && fast_first_runtime) {\n'
             '                MakePipeline(render_pass, VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT);\n'
             '                QueueOptimizedPipeline(render_pass);\n'
             '            } else {\n'
             '                MakePipeline(render_pass);\n'
             '            }'),
            ('void GraphicsPipeline::MakePipeline(VkRenderPass render_pass) {',
             optimize_worker),
            ('    pipeline = device.GetLogical().CreateGraphicsPipeline({',
             '    (target ? *target : pipeline) = device.GetLogical().CreateGraphicsPipeline({'),
            ('        .flags = flags,', '        .flags = flags | extra_flags,'),
            ('cmdbuf.BindPipeline(VK_PIPELINE_BIND_POINT_GRAPHICS, *pipeline);',
             'cmdbuf.BindPipeline(VK_PIPELINE_BIND_POINT_GRAPHICS,\n'
             '    optimized_ready.load(std::memory_order_acquire) ? *optimized_pipeline : *pipeline);'),
        ])
        # The sample decision is set by the GPU owner's PrepareDraw, so the
        # nested stages measure exactly the same draw without extra clocks.
        for expression, phase in (
            ('texture_cache.SynchronizeDescriptors(false);', 'TextureDescriptorSync'),
            ('texture_cache.FillImageViews(std::span(views.data(), views.size()), false, Spec::has_images);', 'TextureFillImageViews'),
            ('buffer_cache.UpdateGraphicsBuffers(is_indexed);', 'GraphicsBufferUpdate'),
            ('guest_descriptor_queue.Acquire(scheduler, num_descriptor_entries, uses_descriptor_buffer);', 'DescriptorQueueAcquire'),
        ):
            replacements.append(
                ('    ' + expression,
                 '    { ::Eden::Performance::CachePhaseTimer cost{::Eden::Performance::CachePhase::' + phase +
                 '};\n        ' + expression + '\n    }'))
    adapt(f'src/video_core/renderer_vulkan/{name}.cpp', name + '_cost.cpp', replacements)
shader_costs = [
    ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include "pipeline_trace_registry.h"\n'
     '#include "performance.h"\n#include "dev_vulkan.h"\n#include "diagnostics.h"'),
    # Development crash probes: report each pipeline's first use (stage hashes) to klog,
    # which survives a GPU fault that kills the title.
    ('    current_pipeline = pipeline.get();\n    return BuiltPipeline(current_pipeline);\n}',
     '    current_pipeline = pipeline.get();\n'
     '    if (::Eden::DevVulkan::trace_pipelines) {\n'
     '        const auto first_use = ::Eden::PipelineTrace::graphics_first_use.Record(\n'
     '            ::Eden::DevVulkan::gpu_time_session.load(std::memory_order_acquire), current_pipeline);\n'
     '        if (first_use != 0) {\n'
     '            const auto& h = graphics_key.unique_hashes;\n'
     '            char text[256];\n'
     '            std::snprintf(text, sizeof(text), "G%zu p=%p new=%d va=%llx vb=%llx tc=%llx te=%llx gs=%llx fs=%llx",\n'
     '                          first_use, (const void*)current_pipeline, int(is_new), (unsigned long long)h[0], (unsigned long long)h[1],\n'
     '                          (unsigned long long)h[2], (unsigned long long)h[3], (unsigned long long)h[4],\n'
     '                          (unsigned long long)h[5]);\n'
     '            ::Eden::Report("pipeline", text);\n'
     '            LOG_INFO(Render_Vulkan, "EDEN_PIPELINE_FIRST_USE {}", text);\n'
     '        }\n'
     '    }\n'
     '    return BuiltPipeline(current_pipeline);\n}'),
    ('    if (!is_new) {\n        return pipeline.get();\n    }\n    pipeline = CreateComputePipeline(key, shader);\n    return pipeline.get();\n}',
     '    if (is_new) {\n'
     '        pipeline = CreateComputePipeline(key, shader);\n'
     '    }\n'
     '    if (::Eden::DevVulkan::trace_pipelines && pipeline) {\n'
     '        const auto first_use = ::Eden::PipelineTrace::compute_first_use.Record(\n'
     '            ::Eden::DevVulkan::gpu_time_session.load(std::memory_order_acquire), pipeline.get());\n'
     '        if (first_use != 0) {\n'
     '            char text[160];\n'
     '            std::snprintf(text, sizeof(text), "C%zu p=%p new=%d cs=%llx shared=%u wg=%u,%u,%u", first_use,\n'
     '                          (const void*)pipeline.get(), int(is_new), (unsigned long long)key.unique_hash, unsigned(key.shared_memory_size),\n'
     '                          unsigned(key.workgroup_size[0]), unsigned(key.workgroup_size[1]),\n'
     '                          unsigned(key.workgroup_size[2]));\n'
     '            ::Eden::Report("pipeline", text);\n'
     '            LOG_INFO(Render_Vulkan, "EDEN_PIPELINE_FIRST_USE {}", text);\n'
     '        }\n'
     '    }\n'
     '    return pipeline.get();\n}'),
    ('std::unique_ptr<GraphicsPipeline> PipelineCache::CreateGraphicsPipeline() {',
     'std::unique_ptr<GraphicsPipeline> PipelineCache::CreateGraphicsPipeline() {\n    auto timer = Eden::Performance::VulkanTimer(17);'),
    ('    const ComputePipelineCacheKey& key, const ShaderInfo* shader) {',
     '    const ComputePipelineCacheKey& key, const ShaderInfo* shader) {\n    auto timer = Eden::Performance::VulkanTimer(17);'),
    # The cache serializer is rewritten above, so its old "try" signature
     # no longer exists here. Instrument the FINAL generated signature.
     ('                                                 u32 cache_version) {\n#ifdef PS5_NATIVE',
     '                                                 u32 cache_version) {\n    auto timer = Eden::Performance::VulkanTimer(18);\n#ifdef PS5_NATIVE'),
    ('}\n\nPipelineCache::~PipelineCache()',
     '    if (Eden::Performance::vulkan_cost_enabled.load(std::memory_order_relaxed))\n'
     '        std::printf("EDEN_VULKAN_DYNAMIC blend=%u enables=%u vertex=%u\\n",\n'
     '                    unsigned(dynamic_features.has_extended_dynamic_state_3_blend),\n'
     '                    unsigned(dynamic_features.has_extended_dynamic_state_3_enables),\n'
     '                    unsigned(dynamic_features.has_dynamic_vertex_input));\n'
     '}\n\nPipelineCache::~PipelineCache()'),
]
# Time both graphics and compute preparation, without modifying the compiler or
# reading guest state on another thread. These intervals overlap shader_prepare.
shader_source = (source / 'src/video_core/renderer_vulkan/vk_pipeline_cache.cpp').read_text()
# The permanent Vulkan pipeline worker pool cannot safely be interrupted by
# StatefulThreadWorker::WaitForRequests(stop_token): it requests stop on each
# worker, so later on-demand shader compilation would lose its pool. Instead,
# initialize the game's persistent pipeline filenames/driver cache and return
# before scheduling any warmup tasks when an already-stopped token is passed.
# Real guest shaders still compile asynchronously and serialize during play.
lazy_vulkan_cache_anchor = '''    if (use_vulkan_pipeline_cache) {
        vulkan_pipeline_cache_filename = base_dir / "vulkan_pipelines.bin";
        vulkan_pipeline_cache =
            LoadVulkanPipelineCache(vulkan_pipeline_cache_filename, CACHE_VERSION);
    }

    struct {'''
lazy_vulkan_cache_replacement = '''    if (use_vulkan_pipeline_cache) {
        vulkan_pipeline_cache_filename = base_dir / "vulkan_pipelines.bin";
        vulkan_pipeline_cache =
            LoadVulkanPipelineCache(vulkan_pipeline_cache_filename, CACHE_VERSION);
    }

#ifdef PS5_NATIVE
    // The PS5 is launching one foreground game, so do not delay it by
    // compiling the full backlog of shaders from earlier sessions.
    // An already-stopped token is a special initialization-only request:
    // after naming the per-title cache, leave workers RUNNING for later jobs.
    if (stop_loading.stop_requested()) {
        LOG_INFO(Render_Vulkan, "PS5 lazy shader cache ready for {:016x}", title_id);
        return;
    }
#endif

    struct {'''
if shader_source.count(lazy_vulkan_cache_anchor) != 1:
    raise RuntimeError("Pinned Vulkan persistent-cache setup changed")
shader_source = shader_source.replace(lazy_vulkan_cache_anchor, lazy_vulkan_cache_replacement)
# A driver's VkPipelineCache blob can become incompatible after a RADV
# update without changing Eden's guest shader CACHE_VERSION. The SDK may
# reject initial data. Retry with an empty Vulkan cache instead of aborting
# the entire game at initialization; retain guest shader disk metadata.
vulkan_cache_create_anchor = '''        return device.GetLogical().CreatePipelineCache(pipeline_cache_ci);
    };
    try {
        std::ifstream file(filename, std::ios::binary | std::ios::ate);'''
vulkan_cache_create_replacement = '''        try {
            return device.GetLogical().CreatePipelineCache(pipeline_cache_ci);
        } catch (const std::exception& error) {
            if (data_size == 0) throw;
            LOG_WARNING(Render_Vulkan,
                        "Ignoring incompatible driver pipeline cache: {}", error.what());
            pipeline_cache_ci.initialDataSize = 0;
            pipeline_cache_ci.pInitialData = nullptr;
            return device.GetLogical().CreatePipelineCache(pipeline_cache_ci);
        }
    };
    try {
        std::ifstream file(filename, std::ios::binary | std::ios::ate);'''
if shader_source.count(vulkan_cache_create_anchor) != 1:
    raise RuntimeError("Pinned Vulkan pipeline-cache constructor changed")
shader_source = shader_source.replace(vulkan_cache_create_anchor, vulkan_cache_create_replacement)

# PS5 game exit and crashes must not truncate the *last valid* driver cache.
# Serialize off to a .new file and atomically rename over the current file
# only after flush/close succeed. A local mutex prevents two asynchronous
# serializations from sharing the same staging path during shutdown.
# The same directory guarantees an in-filesystem rename on PS5.
vulkan_cache_save_anchor = '''void PipelineCache::SerializeVulkanPipelineCache(const std::filesystem::path& filename,
                                                 const vk::PipelineCache& pipeline_cache,
                                                 u32 cache_version) try {
    std::ofstream file(filename, std::ios::binary);
    file.exceptions(std::ifstream::failbit);
    if (!file.is_open()) {
        LOG_ERROR(Common_Filesystem, "Failed to open Vulkan driver pipeline cache file {}",
                  Common::FS::PathToUTF8String(filename));
        return;
    }
    file.write(VULKAN_CACHE_MAGIC_NUMBER.data(), VULKAN_CACHE_MAGIC_NUMBER.size())
        .write(reinterpret_cast<const char*>(&cache_version), sizeof(cache_version));

    size_t cache_size = 0;
    std::vector<char> cache_data;
    if (pipeline_cache) {
        pipeline_cache.Read(&cache_size, nullptr);
        cache_data.resize(cache_size);
        pipeline_cache.Read(&cache_size, cache_data.data());
    }
    file.write(cache_data.data(), cache_size);

    LOG_INFO(Render_Vulkan, "Vulkan driver pipelines cached at: {}",
             Common::FS::PathToUTF8String(filename));

} catch (const std::ios_base::failure& e) {
    LOG_ERROR(Common_Filesystem, "{}", e.what());
    if (!Common::FS::RemoveFile(filename)) {
        LOG_ERROR(Common_Filesystem, "Failed to delete Vulkan driver pipeline cache file {}",
                  Common::FS::PathToUTF8String(filename));
    }
}
'''
vulkan_cache_save_replacement = '''void PipelineCache::SerializeVulkanPipelineCache(const std::filesystem::path& filename,
                                                 const vk::PipelineCache& pipeline_cache,
                                                 u32 cache_version) {
#ifdef PS5_NATIVE
    // The foreground title may exit while background serializer work exists.
    // Serialize staged files to one writer at a time. Never erase the
    // previously verified driver cache in a write/rename failure path.
    static std::mutex save_mutex;
    const std::lock_guard save_lock{save_mutex};
    auto staging = filename;
    staging += ".new";
    try {
        std::ofstream file;
        file.exceptions(std::ios::failbit | std::ios::badbit);
        file.open(staging, std::ios::binary | std::ios::trunc);
        file.write(VULKAN_CACHE_MAGIC_NUMBER.data(), VULKAN_CACHE_MAGIC_NUMBER.size())
            .write(reinterpret_cast<const char*>(&cache_version), sizeof(cache_version));

        size_t cache_size = 0;
        std::vector<char> cache_data;
        if (pipeline_cache) {
            pipeline_cache.Read(&cache_size, nullptr);
            cache_data.resize(cache_size);
            pipeline_cache.Read(&cache_size, cache_data.data());
        }
        if (cache_size != 0)
            file.write(cache_data.data(), static_cast<std::streamsize>(cache_size));
        file.flush();
        file.close();
        std::error_code rename_error;
        std::filesystem::rename(staging, filename, rename_error);
        if (rename_error) {
            LOG_WARNING(Common_Filesystem, "Driver cache rename failed: {}", rename_error.message());
            std::error_code cleanup_error;
            std::filesystem::remove(staging, cleanup_error);
            return;
        }
        LOG_INFO(Render_Vulkan, "Saved PS5 driver pipeline cache atomically: {}",
                 Common::FS::PathToUTF8String(filename));
    } catch (const std::exception& error) {
        LOG_WARNING(Common_Filesystem, "Retained old driver cache after failed save: {}", error.what());
        std::error_code cleanup_error;
        std::filesystem::remove(staging, cleanup_error);
    }
#else
    try {
        std::ofstream file(filename, std::ios::binary);
        file.exceptions(std::ifstream::failbit);
        if (!file.is_open())
            return;
        file.write(VULKAN_CACHE_MAGIC_NUMBER.data(), VULKAN_CACHE_MAGIC_NUMBER.size())
            .write(reinterpret_cast<const char*>(&cache_version), sizeof(cache_version));
        size_t cache_size = 0;
        std::vector<char> cache_data;
        if (pipeline_cache) {
            pipeline_cache.Read(&cache_size, nullptr);
            cache_data.resize(cache_size);
            pipeline_cache.Read(&cache_size, cache_data.data());
        }
        file.write(cache_data.data(), cache_size);
    } catch (const std::ios_base::failure& error) {
        LOG_ERROR(Common_Filesystem, "{}", error.what());
    }
#endif
}
'''
if shader_source.count(vulkan_cache_save_anchor) != 1:
    raise RuntimeError("Pinned Vulkan driver cache serializer changed")
shader_source = shader_source.replace(vulkan_cache_save_anchor, vulkan_cache_save_replacement)
# Native affinity masks describe the CPUs the *process can schedule on*;
# hardware_concurrency() can report more than the PS5 runtime permits.
pipeline_ps5_headers = f'''#ifdef PS5_NATIVE
#include <pthread.h>
#include <sched.h>
#include <sys/param.h>
#include <sys/cpuset.h>
#include <cstdio>
#include "{port / 'performance.h'}"
#endif
'''
if shader_source.count('#include <thread>') != 1:
    raise RuntimeError('Pinned Vulkan pipeline header changed')
shader_source = shader_source.replace('#include <thread>', '#include <thread>\n' + pipeline_ps5_headers)
# PS5 shader worker occupancy must use the affinity of THIS thread,
# not a global count or a guess that every affinity mask still includes the
# guest/GPU primary cores. On R237 the native shader thread inherited an
# 8-logical-CPU secondary mask 0x1fe0, but this policy reserved 7 primary
# slots a SECOND time and launched ONE shader compiler. Compare the thread's
# actual affinity with the verified primary worker mask and reserve those
# primary slots only when they are actually in this mask. Keep two secondary
# logical slots for audio/presentation/services. Topology-unknown falls back
# to the original conservative 7-slot reservation. Cap builders at six.
pipeline_worker_anchor = '''    return max_core_threads;
#endif
}'''
pipeline_worker_replacement = '''#ifdef PS5_NATIVE
    const size_t reported = std::max<size_t>(static_cast<size_t>(std::thread::hardware_concurrency()), 2ULL);
    cpuset_t allowed{};
    const int affinity_rc = cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1, 8, &allowed);
    size_t available = 0;
    std::uint64_t allowed_mask = 0;
    if (affinity_rc == 0) {
        for (unsigned cpu = 0; cpu < 64; ++cpu) {
            if (CPU_ISSET(cpu, &allowed)) {
                ++available;
                allowed_mask |= std::uint64_t{1} << cpu;
            }
        }
    }
    // Reserve only what is REALLY shared with guest/GPU workers in the
    // CURRENT thread's allowed mask. The masked-off primaries have already
    // been excluded by SetSecondaryPlacement: do NOT subtract them again.
    // The kernel's confirmed affinity is authoritative. C++ hardware_concurrency()
    // is only a hint: on constrained firmware it can under-report the CPUs
    // actually granted to this thread and silently starve shader compilers.
    // Never borrow CPUs outside the read-back allowed mask.
    const size_t schedulable = available ? available : std::min<size_t>(reported, 4);
    const std::uint64_t primary_mask = ::Eden::Performance::PinnedWorkerMask();
    size_t primary_in_mask = 0;
    if (affinity_rc == 0 && primary_mask) {
        for (unsigned cpu = 0; cpu < 64; ++cpu)
            if (CPU_ISSET(cpu, &allowed) && (primary_mask & (std::uint64_t{1} << cpu)))
                ++primary_in_mask;
    }
    // A logical-only dev A/B trial may have already pinned the SHADER
    // parent to a kernel-verified secondary mask. It is then wrong to
    // subtract the seven primary CPU/GPU services AGAIN. Do not equate
    // this proof of LOGICAL nonoverlap with physical/SMT core identity.
    const std::uint64_t secondary_mask = ::Eden::Performance::VerifiedSecondaryPlacementMask();
    const bool secondary_isolated = affinity_rc == 0 && allowed_mask != 0 &&
        secondary_mask != 0 && (allowed_mask & ~secondary_mask) == 0;
    constexpr size_t secondary_headroom = 2;
    constexpr size_t unverified_reserved = 7;
    constexpr size_t max_pipeline_workers = 6;
    const size_t reserved = affinity_rc == 0 && primary_mask ?
        primary_in_mask + secondary_headroom :
        secondary_isolated ? secondary_headroom : unverified_reserved;
    const size_t spare = schedulable > reserved ? schedulable - reserved : 0ULL;
    const size_t selected = std::max<size_t>(1ULL, std::min(spare, max_pipeline_workers));
    std::printf("EDEN_PS5_SHADER_WORKERS reported=%zu available=%zu workers=%zu "
                "reserved=%zu primary_in_mask=%zu physical_verified=%u logical_isolated=%u affinity_rc=%d "
                "allowed_mask=0x%llx primary_mask=0x%llx secondary_mask=0x%llx\\n",
                reported, available, selected, reserved, primary_in_mask,
                unsigned(primary_mask != 0), unsigned(secondary_isolated), affinity_rc,
                static_cast<unsigned long long>(allowed_mask),
                static_cast<unsigned long long>(primary_mask),
                static_cast<unsigned long long>(secondary_mask));
    return selected;
#else
    return max_core_threads;
#endif
#endif
}'''
if shader_source.count(pipeline_worker_anchor) != 1:
    raise RuntimeError('Pinned Vulkan pipeline worker policy changed')
shader_source = shader_source.replace(pipeline_worker_anchor, pipeline_worker_replacement)
for expression, index, count in (
    ('main_pools.ReleaseContents()', 19, 2),
    ('TranslateProgram(pools.inst, pools.block, env, cfg, host_info)', 21, 3),
    ('EmitSPIRV(profile, runtime_info, program, binding)', 22, 1),
    ('EmitSPIRV(profile, program)', 22, 1),
    ('BuildShader(device, code)', 23, 2),
):
    if shader_source.count(expression) != count:
        raise RuntimeError(f'Shader cost anchor changed: {expression}')
    shader_source = shader_source.replace(expression,
        f'([&] {{ auto cost = Eden::Performance::VulkanTimer({index}); '
        f'return {expression}; }}())')
for statement in (
    'Shader::Maxwell::Flow::CFG cfg(env, pools.flow_block, cfg_offset, index == 0);',
    'Shader::Maxwell::Flow::CFG cfg{env, pools.flow_block, env.StartAddress()};',
):
    expected = 2 if 'cfg_offset' in statement else 1  # graphics exception dump too
    if shader_source.count(statement) != expected:
        raise RuntimeError(f'Shader CFG anchor changed: {statement}')
    shader_source = shader_source.replace(statement,
        'auto cfg_cost = Eden::Performance::VulkanTimer(20);\n        ' + statement +
        '\n        cfg_cost.reset();')
for old, new in shader_costs:
    if shader_source.count(old) != 1:
        raise RuntimeError(f'Shader pipeline anchor changed: {old[:60]}')
    shader_source = shader_source.replace(old, new)
shader_output = output / 'vk_pipeline_cache_cost.cpp'
if not shader_output.exists() or shader_output.read_text() != shader_source:
    shader_output.write_text(shader_source)

# Scope only the existing synchronous operations; never alter their ordering.
# Report these caller costs separately from the overlapping API totals.
import re
# Development GPU fault probes (dev_vulkan.h): multi-range storage buffers are
# the one path that binds sparse ranges of the console's device memory.
probes = {
    'vk_multi_range_buffer': [
        ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include "dev_vulkan.h"\n#include "diagnostics.h"'),
        ('    if (bind_result != VK_SUCCESS) {\n        return SparseBuffer{};\n    }',
         '    if (bind_result != VK_SUCCESS) {\n'
         '        if (::Eden::DevVulkan::trace_pipelines) ::Eden::Report("multirange", "sparse bind failed");\n'
         '        return SparseBuffer{};\n    }'),
        ('    retired.push_back(Retired{',
         '    if (::Eden::DevVulkan::trace_pipelines) {\n'
         '        static unsigned retires = 0;\n'
         '        if (++retires <= 64) {\n'
         '            char text[96];\n'
         '            std::snprintf(text, sizeof(text), "retire #%u sparse=%d tick=%llu", retires,\n'
         '                          int(bool(entry.sparse_handle)), (unsigned long long)scheduler.CurrentTick());\n'
         '            ::Eden::Report("multirange", text);\n'
         '        }\n'
         '    }\n'
         '    retired.push_back(Retired{'),
        ('    entries.emplace(key, std::move(entry));',
         '    if (::Eden::DevVulkan::trace_pipelines) {\n'
         '        static unsigned created = 0;\n'
         '        if (++created <= 256) {\n'
         '            char text[192];\n'
         '            std::snprintf(text, sizeof(text), "new #%u key=%llx total=%llu sources=%zu sparse=%d addr=%llx",\n'
         '                          created, (unsigned long long)key, (unsigned long long)total, sources.size(),\n'
         '                          int(bool(entry.sparse_handle)), (unsigned long long)entry.address);\n'
         '            ::Eden::Report("multirange", text);\n'
         '        }\n'
         '    }\n'
         '    entries.emplace(key, std::move(entry));'),
    ],
    'vk_buffer_cache': [
        ('#include <algorithm>', '#include <algorithm>\n#include "dev_vulkan.h"'),
        ('bool BufferCacheRuntime::BindMultiRangeStorageBuffer(u64 key, bool is_written) {\n',
         'bool BufferCacheRuntime::BindMultiRangeStorageBuffer(u64 key, bool is_written) {\n'
         '    if (::Eden::DevVulkan::disable_multi_range) {\n        return false;\n    }\n'),
    ],
    # With custom border colours off (the console default), report which clamp-to-border
    # samplers ask for a colour the three standard ones cannot give exactly.
    'vk_texture_cache': [
        ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include "dev_vulkan.h"\n#include "diagnostics.h"'),
        ('    has_custom_border_colors = samples_border && device.IsCustomBorderColorUsable();',
         '    if (::Eden::DevVulkan::trace_pipelines && samples_border) {\n'
         '        static std::vector<std::array<float, 4>> reported;\n'
         '        const auto report = [](const std::array<float, 4>& c, const char* kind) {\n'
         '            if (c == std::array<float, 4>{0, 0, 0, 0} || c == std::array<float, 4>{0, 0, 0, 1} ||\n'
         '                c == std::array<float, 4>{1, 1, 1, 1} || reported.size() >= 32 ||\n'
         '                std::find(reported.begin(), reported.end(), c) != reported.end()) return;\n'
         '            reported.push_back(c);\n'
         '            char text[128];\n'
         '            std::snprintf(text, sizeof(text), "non-standard %s border %g %g %g %g", kind, c[0], c[1],\n'
         '                          c[2], c[3]);\n'
         '            ::Eden::Report("sampler", text);\n'
         '        };\n'
         '        report(border_color, "linear");\n'
         '        if (tsc.srgb_conversion) report(srgb_border_color, "srgb");\n'
         '    }\n'
         '    has_custom_border_colors = samples_border && device.IsCustomBorderColorUsable();'),
    ],
}
for name, index, expected in (
    ('vk_fence_manager', 6, 1), ('vk_buffer_cache', 7, 3),
    ('vk_texture_cache', 8, 1), ('vk_swapchain', 9, 6),
    ('vk_descriptor_buffer', 10, 3), ('vk_multi_range_buffer', 11, 1),
    ('vk_compute_pass', 12, 1),
):
    relative = f'src/video_core/renderer_vulkan/{name}.cpp'
    destination = 'vulkan_swapchain.cpp' if name == 'vk_swapchain' else name + '_cost.cpp'
    # The descriptor source is adapted earlier for R323, just like the swapchain
    # is adapted for error-recovery. The cost wrapper MUST preserve that source.
    # Native CMake links vk_descriptor_buffer_cost.cpp, not the intermediate
    # vulkan_descriptor_buffer.cpp; re-reading the pinned upstream here would
    # silently discard PreflightFrameReuse and break the PS5 link.
    path = output / destination
    if name == 'vk_descriptor_buffer':
        text = (output / 'vulkan_descriptor_buffer.cpp').read_text()
    elif name == 'vk_swapchain':
        text = path.read_text()
    else:
        text = (source / relative).read_text()
    pattern = r'(?m)^( +)(scheduler\.(?:Wait|Finish)\([^\n]*\);)$'
    matches = list(re.finditer(pattern, text))
    if len(matches) != expected:
        raise RuntimeError(f'Wait-site anchors changed: {name}: {len(matches)} != {expected}')
    text = re.sub(pattern, lambda m: m[1] + '{ auto timer = Eden::Performance::VulkanTimer('
                  + str(index) + '); ' + m[2] + ' }', text)
    if name == 'vk_compute_pass':
        # ASTC decode has no CPU consumer. Its existing image barrier orders
        # later shaders, and staging/descriptor reuse is protected by ticks.
        text = text.replace('VulkanTimer(12); scheduler.Finish();',
                            'VulkanTimer(12); scheduler.Flush();')
    for probe_old, probe_new in probes.get(name, []):
        if text.count(probe_old) != 1:
            raise RuntimeError(f'Probe anchor changed: {name}: {probe_old[:60]}')
        text = text.replace(probe_old, probe_new)
    text = '#include "performance.h"\n' + text
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
