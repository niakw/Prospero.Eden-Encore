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
    if (!::Eden::Performance::cpu_write_defer.load(std::memory_order_relaxed) ||
        ::Eden::GpuDeferredWrite::replaying_guest_write) return false;
    const size_t thread = system.GetCurrentHostThreadID();
    const unsigned core = static_cast<unsigned>(std::min<size_t>(thread, 3));
    return deferred_cpu_write_queue.Enqueue(core, address, size);
}
void MemoryManager::FlushCaching() {
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
    string(PREPEND bridge_mm "#include \"${EDEN_PORT_DIR}/performance.h\"\n#include \"${EDEN_PORT_DIR}/gpu_deferred_replay.h\"\n")
    write_derived("${PORT_BUILD_DIR}/memory_manager_deferred.cpp" "${bridge_mm}")

    # Use maintained Vulkan implementation; do not mutate its byte-pinned
    # active file or the generator/source parity contract.
    file(READ "${PORT_ROOT}/vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp" bridge_vk)
    set(vk_entry "bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {")
    set(vk_buffer_lock "        ::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false);")
    set(vk_texture_lock "        ::Eden::Performance::GuestCacheLock(texture_cache.mutex, true);\n        texture_wait.Stop();")
    foreach(anchor IN ITEMS vk_entry vk_buffer_lock vk_texture_lock)
        string(FIND "${bridge_vk}" "${${anchor}}" found)
        if(found LESS 0)
            message(FATAL_ERROR "Pinned Vulkan guest write anchor changed (${anchor})")
        endif()
    endforeach()
    string(REPLACE "${vk_entry}" [=[bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {
    const bool defer_candidate =
        ::Eden::Performance::cpu_write_defer.load(std::memory_order_relaxed) &&
        !::Eden::GpuDeferredWrite::replaying_guest_write;]=]
        bridge_vk "${bridge_vk}")
    string(REPLACE "${vk_buffer_lock}" [=[
        if (!defer_candidate) {
            ::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false);
        } else if (!buffer_cache.mutex.try_lock()) {
            if (gpu_memory->EnqueueDeferredCPUWrite(addr, size)) return false;
            ::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false);
        }]=] bridge_vk "${bridge_vk}")
    string(REPLACE "${vk_texture_lock}" [=[
        if (!defer_candidate) {
            ::Eden::Performance::GuestCacheLock(texture_cache.mutex, true);
        } else if (!texture_cache.mutex.try_lock()) {
            if (gpu_memory->EnqueueDeferredCPUWrite(addr, size)) return false;
            ::Eden::Performance::GuestCacheLock(texture_cache.mutex, true);
        }
        texture_wait.Stop();]=] bridge_vk "${bridge_vk}")
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

    get_target_property(bridge_sources video_core SOURCES)
    foreach(old IN ITEMS
        "memory_manager.cpp"
        "${PORT_BUILD_DIR}/vulkan_rasterizer.cpp"
        "${PORT_BUILD_DIR}/dma_pusher.cpp"
        "engines/maxwell_dma.cpp"
        "engines/kepler_compute.cpp")
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
        "${PORT_BUILD_DIR}/kepler_compute_deferred.cpp")
    set_property(TARGET video_core PROPERTY SOURCES "${bridge_sources}")
    # IMPORTANT: No code enables cpu_write_defer. Native bridge compilation
    # is not a gameplay qualification or permission to run experiments.
endif()
