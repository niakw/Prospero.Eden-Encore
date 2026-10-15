# Experimental native replay bridge. Never part of normal native packages.
option(EDEN_GUEST_WRITE_BRIDGE_DEV "Compile inactive native deferred-write bridge" OFF)
if(EDEN_GUEST_WRITE_BRIDGE_DEV)
    if(NOT PS5_NATIVE OR NOT EDEN_PS5_VULKAN OR NOT EDEN_DEV_PROFILE)
        message(FATAL_ERROR "Guest write bridge requires native Vulkan developer profile")
    endif()
    target_compile_definitions(video_core PRIVATE EDEN_GUEST_WRITE_BRIDGE_DEV=1)

    # The queue belongs to the guest GPU address space, not a process-global.
    file(READ "${PROJECT_SOURCE_DIR}/src/video_core/memory_manager.h" bridge_h)
    set(h_api "    void FlushCaching();")
    set(h_owner "    Core::System& system;")
    foreach(anchor IN ITEMS h_api h_owner)
        string(FIND "${bridge_h}" "${${anchor}}" found)
        if(found LESS 0)
            message(FATAL_ERROR "Pinned GPU memory manager layout changed (${anchor})")
        endif()
    endforeach()
    string(REPLACE "${h_api}"
        "    bool EnqueueDeferredCPUWrite(u64 address, u64 size);\n    void FlushCaching();"
        bridge_h "${bridge_h}")
    string(REPLACE "${h_owner}"
        "    ::Eden::GpuDeferredWrite::Queue deferred_cpu_write_queue;\n    Core::System& system;"
        bridge_h "${bridge_h}")
    string(PREPEND bridge_h "#include \"${EDEN_PORT_DIR}/gpu_deferred_replay.h\"\n")
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/video_core")
    write_derived("${PORT_BUILD_DIR}/include/video_core/memory_manager.h" "${bridge_h}")
    target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/include")
    target_include_directories(core BEFORE PRIVATE "${PORT_BUILD_DIR}/include")
    # The pinned GPU-dirty collector has an unsafe read/exchange handoff:
    # concurrent Collect from the guest and renderer can discard another
    # producer's pending transform. Derive a host-tested synchronized version
    # ONLY when this opt-in bridge is compiled, leaving pinned sources intact.
    file(READ "${PROJECT_SOURCE_DIR}/src/core/gpu_dirty_memory_manager.h" bridge_dirty)
    set(dirty_entry "    void Collect(PAddr address, size_t size) {\n        TransformAddress t = BuildTransform(address, size);")
    set(dirty_nested "                    std::scoped_lock lk(guard);\n                    back_buffer.emplace_back(tmp);")
    foreach(anchor IN ITEMS dirty_entry dirty_nested)
        string(FIND "${bridge_dirty}" "${${anchor}}" found)
        if(found LESS 0)
            message(FATAL_ERROR "Pinned GPU-dirty collector changed (${anchor})")
        endif()
    endforeach()
    string(REPLACE "${dirty_entry}"
        "    void Collect(PAddr address, size_t size) {\n        std::scoped_lock lk(guard);\n        TransformAddress t = BuildTransform(address, size);"
        bridge_dirty "${bridge_dirty}")
    # Do not recursively acquire guard inside the now-serialized Collect.
    string(REPLACE "${dirty_nested}"
        "                    back_buffer.emplace_back(tmp);"
        bridge_dirty "${bridge_dirty}")
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/deferred-core/core")
    write_derived("${PORT_BUILD_DIR}/deferred-core/core/gpu_dirty_memory_manager.h"
        "${bridge_dirty}")
    target_include_directories(core BEFORE PRIVATE "${PORT_BUILD_DIR}/deferred-core")
    target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/deferred-core")


    # Derive the actual GPU memory manager, explicitly using the shadow header.
    file(READ "${PROJECT_SOURCE_DIR}/src/video_core/memory_manager.cpp" bridge_mm)
    string(FIND "${bridge_mm}" "#include \"memory_manager.h\"" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned GPU MemoryManager local header changed")
    endif()
    string(REPLACE "#include \"memory_manager.h\""
        "#include \"video_core/memory_manager.h\"" bridge_mm "${bridge_mm}")
    set(flush_api "void MemoryManager::FlushCaching() {")
    string(FIND "${bridge_mm}" "${flush_api}" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned GPU FlushCaching entry changed")
    endif()
    set(bridge_flush [=[
bool MemoryManager::EnqueueDeferredCPUWrite(u64 address, u64 size) {
    // The native producer still enqueues BEFORE writing guest backing RAM.
    // No runtime setting may activate this until the post-store bridge exists.
    if (!::Eden::GpuDeferredWrite::kNativePostStorePublicationReady ||
        !::Eden::Performance::cpu_write_defer.load(std::memory_order_relaxed) ||
        ::Eden::GpuDeferredWrite::replaying_guest_write) return false;
    const unsigned core = ::Eden::GpuDeferredWrite::guest_write_origin_core;
    if (core >= ::Eden::GpuDeferredWrite::Queue::Cores) return false;
    return deferred_cpu_write_queue.Enqueue(core, address, size);
}
void MemoryManager::FlushCaching() {
    // A failed replay may have partially modified cache state. Never allow
    // a later GPU command to proceed through this developer-only bridge.
    if (deferred_cpu_write_queue.Failed()) std::terminate();
    if (deferred_cpu_write_queue.Pending()) {
        ::Eden::GpuDeferredWrite::ScopedReplay replay_guard;
        auto dirty = system.GetGPUDirtyMemoryManager();
        ::Eden::GpuDeferredWrite::ReplayQueued(deferred_cpu_write_queue,
            [&](std::uint64_t address, std::uint64_t size) {
                return rasterizer->OnCPUWrite(address, size);
            },
            [&](unsigned core, std::uint64_t address, std::uint64_t size) {
                dirty[core].Collect(address, size);
            });
    }
]=])
    string(REPLACE "${flush_api}" "${bridge_flush}" bridge_mm "${bridge_mm}")
    string(PREPEND bridge_mm "#include \"core/gpu_dirty_memory_manager.h\"\n#include \"${EDEN_PORT_DIR}/performance.h\"\n#include \"${EDEN_PORT_DIR}/gpu_deferred_replay.h\"\n")
    write_derived("${PORT_BUILD_DIR}/memory_manager_deferred.cpp" "${bridge_mm}")

    # Use maintained Vulkan implementation; do not mutate its byte-pinned
    # active file or the generator/source parity contract.
    file(READ "${PORT_ROOT}/vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp" bridge_vk)
    set(vk_entry "bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {")
    set(vk_buffer_lock "        ::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false);")
    # The texture lock MUST retain the original blocking path. Once
    # buffer_cache.OnCPUWrite runs, postponing the texture invalidation
    # would replay an operation whose first half already mutated cache state.
    foreach(anchor IN ITEMS vk_entry vk_buffer_lock)
        string(FIND "${bridge_vk}" "${${anchor}}" found)
        if(found LESS 0)
            message(FATAL_ERROR "Pinned Vulkan guest write anchor changed (${anchor})")
        endif()
    endforeach()
    string(REPLACE "${vk_entry}" [=[bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {
    const bool defer_candidate =
        ::Eden::GpuDeferredWrite::kNativePostStorePublicationReady &&
        ::Eden::Performance::cpu_write_defer.load(std::memory_order_relaxed) &&
        ::Eden::GpuDeferredWrite::guest_write_origin_core < ::Eden::GpuDeferredWrite::Queue::Cores &&
        !::Eden::GpuDeferredWrite::replaying_guest_write;]=]
        bridge_vk "${bridge_vk}")
    string(REPLACE "${vk_buffer_lock}" [=[
        if (!defer_candidate) {
            ::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false);
        } else if (!buffer_cache.mutex.try_lock()) {
            if (gpu_memory->EnqueueDeferredCPUWrite(addr, size)) return false;
            ::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false);
        }]=] bridge_vk "${bridge_vk}")
    string(PREPEND bridge_vk "#include \"${EDEN_PORT_DIR}/gpu_deferred_replay.h\"\n#include \"video_core/memory_manager.h\"\n")
    write_derived("${PORT_BUILD_DIR}/vulkan_rasterizer_deferred.cpp" "${bridge_vk}")

    # At the producer and fence boundaries, queued guest writes must drain.
    if(NOT EXISTS "${PORT_BUILD_DIR}/dma_pusher.cpp")
        message(FATAL_ERROR "Missing derived native DMA pusher")
    endif()
    file(READ "${PORT_BUILD_DIR}/dma_pusher.cpp" bridge_dma)
    string(FIND "${bridge_dma}" "void DmaPusher::DispatchCalls() {" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned DMA dispatch entry changed")
    endif()
    string(REPLACE "void DmaPusher::DispatchCalls() {"
        "void DmaPusher::DispatchCalls() {\n    memory_manager.FlushCaching();"
        bridge_dma "${bridge_dma}")
    string(FIND "${bridge_dma}" "    system.GPU().OnCommandListEnd();" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned DMA command fence changed")
    endif()
    string(REPLACE "    system.GPU().OnCommandListEnd();"
        "    memory_manager.FlushCaching();\n    system.GPU().OnCommandListEnd();"
        bridge_dma "${bridge_dma}")
    write_derived("${PORT_BUILD_DIR}/dma_pusher_deferred.cpp" "${bridge_dma}")

    # The buffer clear fast path bypasses the old conditional DMA flush.
    file(READ "${PROJECT_SOURCE_DIR}/src/video_core/engines/maxwell_dma.cpp" bridge_maxwell)
    string(FIND "${bridge_maxwell}" "void MaxwellDMA::Launch() {" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned Maxwell DMA launch changed")
    endif()
    string(REPLACE "void MaxwellDMA::Launch() {"
        "void MaxwellDMA::Launch() {\n    memory_manager.FlushCaching();"
        bridge_maxwell "${bridge_maxwell}")
    write_derived("${PORT_BUILD_DIR}/maxwell_dma_deferred.cpp" "${bridge_maxwell}")

    file(READ "${PROJECT_SOURCE_DIR}/src/video_core/engines/kepler_compute.cpp" bridge_kepler)
    string(FIND "${bridge_kepler}" "void KeplerCompute::ProcessLaunch() {" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned Kepler launch changed")
    endif()
    string(REPLACE "void KeplerCompute::ProcessLaunch() {"
        "void KeplerCompute::ProcessLaunch() {\n    memory_manager.FlushCaching();"
        bridge_kepler "${bridge_kepler}")
    write_derived("${PORT_BUILD_DIR}/kepler_compute_deferred.cpp" "${bridge_kepler}")

    # An inline memory upload can touch cached guest data BEFORE the next
    # renderer draw/dispatch. Drain ahead of linear and tiled uploads alike.
    file(READ "${PROJECT_SOURCE_DIR}/src/video_core/engines/engine_upload.cpp" bridge_upload)
    set(upload_anchor "void State::ProcessData(std::span<const u8> read_buffer) {")
    string(FIND "${bridge_upload}" "${upload_anchor}" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned upload State::ProcessData moved")
    endif()
    string(REPLACE "${upload_anchor}"
        "void State::ProcessData(std::span<const u8> read_buffer) {\n    memory_manager.FlushCaching();"
        bridge_upload "${bridge_upload}")
    write_derived("${PORT_BUILD_DIR}/engine_upload_deferred.cpp" "${bridge_upload}")

    # Only a real guest-memory write may produce deferred work. The original
    # HandleRasterizerWrite knows the exact guest core, including syscore 3.
    # Preserve that origin across GPU::OnCPUWrite, rather than inferring a core
    # from whichever host thread later invokes the Vulkan rasterizer.
    set(bridge_cpu_source "${PORT_BUILD_DIR}/memory-ps5.cpp")
    if(NOT EXISTS "${bridge_cpu_source}")
        message(FATAL_ERROR "Missing canonical native guest memory translation unit")
    endif()
    file(READ "${bridge_cpu_source}" bridge_cpu)
    set(bridge_guest_origin [=[                auto const do_collection = (address != 0 && size != 0)
                    && system.GPU().OnCPUWrite(address, size);]=])
    string(FIND "${bridge_cpu}" "${bridge_guest_origin}" found)
    if(found LESS 0)
        message(FATAL_ERROR "Pinned HandleRasterizerWrite guest origin changed")
    endif()
    string(REPLACE "${bridge_guest_origin}" [=[                ::Eden::GpuDeferredWrite::ScopedGuestWriteOrigin guest_origin{
                    static_cast<unsigned>(core)};
                auto const do_collection = (address != 0 && size != 0)
                    && system.GPU().OnCPUWrite(address, size);]=]
        bridge_cpu "${bridge_cpu}")
    string(PREPEND bridge_cpu "#include \"${EDEN_PORT_DIR}/gpu_deferred_replay.h\"\n")
    write_derived("${PORT_BUILD_DIR}/memory-ps5-deferred.cpp" "${bridge_cpu}")
    get_target_property(bridge_core_sources core SOURCES)
    list(FIND bridge_core_sources "${bridge_cpu_source}" core_memory_index)
    if(core_memory_index EQUAL -1)
        message(FATAL_ERROR "Canonical native guest memory TU missing from core target")
    endif()
    list(REMOVE_ITEM bridge_core_sources "${bridge_cpu_source}")
    list(APPEND bridge_core_sources "${PORT_BUILD_DIR}/memory-ps5-deferred.cpp")
    set_property(TARGET core PROPERTY SOURCES "${bridge_core_sources}")

    get_target_property(bridge_sources video_core SOURCES)
    foreach(old IN ITEMS
        "memory_manager.cpp"
        "${PORT_BUILD_DIR}/vulkan_rasterizer.cpp"
        "${PORT_BUILD_DIR}/dma_pusher.cpp"
        "engines/maxwell_dma.cpp"
        "engines/kepler_compute.cpp"
        "engines/engine_upload.cpp")
        list(FIND bridge_sources "${old}" found)
        if(found EQUAL -1)
            message(FATAL_ERROR "Missing native source ${old}")
        endif()
        list(REMOVE_ITEM bridge_sources "${old}")
    endforeach()
    list(APPEND bridge_sources
        "${PORT_BUILD_DIR}/memory_manager_deferred.cpp"
        "${PORT_BUILD_DIR}/vulkan_rasterizer_deferred.cpp"
        "${PORT_BUILD_DIR}/dma_pusher_deferred.cpp"
        "${PORT_BUILD_DIR}/maxwell_dma_deferred.cpp"
        "${PORT_BUILD_DIR}/kepler_compute_deferred.cpp"
        "${PORT_BUILD_DIR}/engine_upload_deferred.cpp")
    set_property(TARGET video_core PROPERTY SOURCES "${bridge_sources}")
    # IMPORTANT: No code enables cpu_write_defer. Native bridge compilation
    # is not a gameplay qualification or permission to run experiments.
endif()
