file(READ "${PROJECT_SOURCE_DIR}/src/video_core/gpu.cpp" gpu_source)
string(REPLACE ": gpu_thread{system_}\n        , system{system_}" ": system{system_}" gpu_source "${gpu_source}")
string(REPLACE ", is_async{is_async_}" ", is_async{is_async_}\n        , gpu_thread{system_}" gpu_source "${gpu_source}")
string(REPLACE "    // Destruction of thread must be done before all (non trivial)\n    // previous members has been destroyed\n    VideoCommon::GPUThread::ThreadManager gpu_thread;\n" "" gpu_source "${gpu_source}")
string(REPLACE "    u64 pending_composite_fence{};" "    u64 pending_composite_fence{};\n    VideoCommon::GPUThread::ThreadManager gpu_thread;" gpu_source "${gpu_source}")
if(EDEN_PS5_OPENGL)
    set(EDEN_MAINTAINED_GL_BUFFER_CACHE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_buffer_cache.cpp")
    if(NOT EXISTS "${EDEN_MAINTAINED_GL_BUFFER_CACHE}")
        message(FATAL_ERROR "Missing maintained OpenGL buffer cache source")
    endif()
    list(REMOVE_ITEM video_sources renderer_opengl/gl_buffer_cache.cpp)
    list(APPEND video_sources "${EDEN_MAINTAINED_GL_BUFFER_CACHE}")
    if(PS5_NATIVE)
        # PS5 permits reading an ended query while another query is active.
        # Retain the upstream NVIDIA workaround on all other builds.
        set(EDEN_MAINTAINED_GL_QUERY_CACHE
            "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_query_cache.cpp")
        if(NOT EXISTS "${EDEN_MAINTAINED_GL_QUERY_CACHE}")
            message(FATAL_ERROR "Missing maintained native OpenGL query cache")
        endif()
        list(REMOVE_ITEM video_sources renderer_opengl/gl_query_cache.cpp)
        list(APPEND video_sources "${EDEN_MAINTAINED_GL_QUERY_CACHE}")
    endif()
        # Guest draw instrumentation is selected from complete Encore sources.
    if(EDEN_DEV_PROFILE)
        # The development-only OpenGL copy diagnostics are a tracked C++
        # source, byte-for-byte equivalent to the old CMake substitution.
        set(EDEN_MAINTAINED_DEV_GL_TEXTURE
            "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_texture_cache.cpp")
        if(NOT EXISTS "${EDEN_MAINTAINED_DEV_GL_TEXTURE}")
            message(FATAL_ERROR "Missing maintained development GL texture cache")
        endif()
        list(REMOVE_ITEM video_sources renderer_opengl/gl_texture_cache.cpp)
        list(APPEND video_sources "${EDEN_MAINTAINED_DEV_GL_TEXTURE}")
        target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")
    endif()
    # Each profile selects one full translation unit; never splice C++ in CMake.
    set(EDEN_MAINTAINED_GL_RASTERIZER_ROOT
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/renderer_opengl")
    set(EDEN_MAINTAINED_GL_RASTERIZER
        "${EDEN_MAINTAINED_GL_RASTERIZER_ROOT}/gl_rasterizer.cpp")
    if(EDEN_DEV_PROFILE)
        set(EDEN_MAINTAINED_GL_RASTERIZER
            "${EDEN_MAINTAINED_GL_RASTERIZER_ROOT}/gl_rasterizer_dev.cpp")
    endif()
    if(NOT EXISTS "${EDEN_MAINTAINED_GL_RASTERIZER}")
        message(FATAL_ERROR "Missing maintained OpenGL rasterizer variant")
    endif()
    list(REMOVE_ITEM video_sources renderer_opengl/gl_rasterizer.cpp)
    list(APPEND video_sources "${EDEN_MAINTAINED_GL_RASTERIZER}")
    # renderer_opengl.cpp is byte-identical to the pinned source. Keep the
    # original in video_sources: copying it into a derived TU adds no behavior.
    # Join the GPU worker before transferring its context to the teardown thread.
    if(PS5_NATIVE)
        # Native MacroJIT exception recovery is selected from Encore, not generated.
        set(EDEN_MAINTAINED_MACRO
            "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/macro.cpp")
        if(NOT EXISTS "${EDEN_MAINTAINED_MACRO}")
            message(FATAL_ERROR "Missing maintained native macro unit")
        endif()
        list(REMOVE_ITEM video_sources macro.cpp)
        list(APPEND video_sources "${EDEN_MAINTAINED_MACRO}")
    endif()
    # R345: PS5 compiles our versioned, complete GPU worker and queue sources.
    # No source-code string rewrites execute during native configuration.
    if(PS5_NATIVE)
        set(EDEN_ACTIVE_GPU "${PORT_ROOT}/vendor/encore-active/eden-gpu")
        if(EDEN_DEV_PROFILE)
            set(EDEN_GPU_WORKER_VARIANT "gpu_thread_dev.cpp")
        else()
            set(EDEN_GPU_WORKER_VARIANT "gpu_thread_quiet.cpp")
        endif()
        file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/common" "${PORT_BUILD_DIR}/include/video_core")
        configure_file("${EDEN_ACTIVE_GPU}/include/common/bounded_threadsafe_queue.h"
            "${PORT_BUILD_DIR}/include/common/bounded_threadsafe_queue.h" COPYONLY)
        configure_file("${EDEN_ACTIVE_GPU}/include/video_core/gpu_thread.h"
            "${PORT_BUILD_DIR}/include/video_core/gpu_thread.h" COPYONLY)
        configure_file("${EDEN_ACTIVE_GPU}/${EDEN_GPU_WORKER_VARIANT}"
            "${PORT_BUILD_DIR}/gpu_thread.cpp" COPYONLY)
        list(REMOVE_ITEM video_sources gpu_thread.cpp)
        list(APPEND video_sources "${PORT_BUILD_DIR}/gpu_thread.cpp")
        string(PREPEND gpu_source "#include <glad/glad.h>\n")
    else()
    # PS5 GPU queue is already copied from the complete eden-gpu source above.
    # Host-specific GPU header is a tracked source, not generated C++.
    set(EDEN_MAINTAINED_HOST_GPU_HEADER
        "${PORT_ROOT}/vendor/encore-active/eden-core/host-gpu/include/video_core/gpu_thread.h")
    if(NOT EXISTS "${EDEN_MAINTAINED_HOST_GPU_HEADER}")
        message(FATAL_ERROR "Missing maintained host GPU header")
    endif()
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/video_core")
    configure_file("${EDEN_MAINTAINED_HOST_GPU_HEADER}"
        "${PORT_BUILD_DIR}/include/video_core/gpu_thread.h" COPYONLY)
    endif()
    target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/include")
    string(REPLACE "    ~Impl() = default;" "    ~Impl() { gpu_thread.Stop(); if (renderer && Settings::IsOpenGL()) { renderer->Context().MakeCurrent(); glFinish(); } }" gpu_source "${gpu_source}")
    # Join before unique_ptr destruction clears GPU::impl: queued draws call back
    # through GPU::TickWork. NotifyShutdown also protects service-owned state.
    set(old_gpu_shutdown "    void NotifyShutdown() {\n        std::unique_lock lk{sync_mutex};\n        shutting_down.store(true, std::memory_order::relaxed);\n        sync_cv.notify_all();\n    }")
    string(FIND "${gpu_source}" "${old_gpu_shutdown}" gpu_shutdown_offset)
    if(gpu_shutdown_offset LESS 0)
        message(FATAL_ERROR "Pinned GPU shutdown changed")
    endif()
    string(REPLACE "${old_gpu_shutdown}"
        "    void NotifyShutdown() {\n        {\n            std::unique_lock lk{sync_mutex};\n            shutting_down.store(true, std::memory_order::relaxed);\n            sync_cv.notify_all();\n        }\n        gpu_thread.Stop();\n    }" gpu_source "${gpu_source}")
    # In-flight guest waits must also unwind before Stop can join the worker.
    # G20: select maintained normal/DEV guest GPU command processor units.
    # The DMA input already contains the shipping #4473/#4477 backport.
    set(EDEN_MAINTAINED_GUEST_GPU_ROOT
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core")
    if(EDEN_DEV_PROFILE)
        set(EDEN_MAINTAINED_GPU_DMA "${EDEN_MAINTAINED_GUEST_GPU_ROOT}/dma_pusher_dev.cpp")
        set(EDEN_MAINTAINED_GPU_PULLER "${EDEN_MAINTAINED_GUEST_GPU_ROOT}/engines/puller_dev.cpp")
        target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")
    else()
        set(EDEN_MAINTAINED_GPU_DMA "${EDEN_MAINTAINED_GUEST_GPU_ROOT}/dma_pusher.cpp")
        set(EDEN_MAINTAINED_GPU_PULLER "${EDEN_MAINTAINED_GUEST_GPU_ROOT}/engines/puller.cpp")
    endif()
    if(NOT EXISTS "${EDEN_MAINTAINED_GPU_DMA}" OR
       NOT EXISTS "${EDEN_MAINTAINED_GPU_PULLER}")
        message(FATAL_ERROR "Missing maintained GPU command processor variants")
    endif()
    list(REMOVE_ITEM video_sources dma_pusher.cpp engines/puller.cpp)
    list(APPEND video_sources "${EDEN_MAINTAINED_GPU_DMA}" "${EDEN_MAINTAINED_GPU_PULLER}")
    # Once the worker has joined, queued callbacks can never execute. Drop them
    # before waking waiters: some callbacks borrow their callers' stack storage.
    string(REPLACE "        gpu_thread.Stop();\n    }"
        "        gpu_thread.Stop();\n        {\n            std::lock_guard lock{sync_request_mutex};\n            sync_requests.clear();\n            sync_requests_stopped = true;\n        }\n        sync_request_cv.notify_all();\n    }" gpu_source "${gpu_source}")
    string(REPLACE "    u64 pending_composite_fence{};" "    bool sync_requests_stopped{}; // Protected by sync_request_mutex.\n    u64 pending_composite_fence{};" gpu_source "${gpu_source}")
    string(REPLACE "        const u64 fence = ++last_sync_fence;" "        if (sync_requests_stopped) return CurrentSyncRequestFence();\n        const u64 fence = ++last_sync_fence;" gpu_source "${gpu_source}")
    string(REPLACE "return CurrentSyncRequestFence() >= fence;" "return sync_requests_stopped || CurrentSyncRequestFence() >= fence;" gpu_source "${gpu_source}")
    # Queued CPU read flushes must own the download area's address range.
    # If a worker failure makes WaitForSyncOperation throw, OnCPURead's
    # stack unwinds while the callback can remain queued. Capturing the
    # local raster_area by reference would leave a dangling reference.
    set(gpu_read_capture_original "RequestSyncOperation([this, &raster_area]() {")
    string(FIND "${gpu_source}" "${gpu_read_capture_original}" gpu_read_capture_at)
    if(gpu_read_capture_at LESS 0)
        message(FATAL_ERROR "Pinned GPU read callback lifetime changed")
    endif()
    string(REPLACE "${gpu_read_capture_original}"
        "RequestSyncOperation([this, raster_area]() {"
        gpu_source "${gpu_source}")
    # A worker exception can stop GPU ticks before a pending CPU fence is
    # acknowledged. The ordinary shutdown cancellation runs only after
    # joining that worker, and cannot rescue a guest already stuck on its
    # CPU-side WaitForSyncOperation. Source-gated native correction: observe
    # the existing fatal GPU error without consuming it for other waiters.
    set(gpu_sync_wait_original [=[    void WaitForSyncOperation(const u64 fence) {
        std::unique_lock lck{sync_request_mutex};
        sync_request_cv.wait(lck, [this, fence] { return sync_requests_stopped || CurrentSyncRequestFence() >= fence; });
    }]=])
    string(FIND "${gpu_source}" "${gpu_sync_wait_original}" gpu_sync_wait_position)
    if(gpu_sync_wait_position LESS 0)
        message(FATAL_ERROR "Pinned native GPU synchronization wait changed")
    endif()
    file(READ "${PORT_ROOT}/vendor/encore-active/eden-core/gpu-injections/gpu_sync_failure_wait.inc" gpu_sync_wait_replacement)
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${PORT_ROOT}/vendor/encore-active/eden-core/gpu-injections/gpu_sync_failure_wait.inc")
    string(REPLACE "${gpu_sync_wait_original}" "${gpu_sync_wait_replacement}"
        gpu_source "${gpu_source}")
    string(PREPEND gpu_source "#include \"${EDEN_PORT_DIR}/gpu_failure.h\"\n")
    # TickWork previously unlocked its mutex through the raw object while a
    # unique_lock still believed it owned that mutex. On an exception from a
    # GPU callback, the unique_lock destructor would attempt another unlock.
    # Keep ownership tracking correct before worker failure propagation.
    # A continuously replenished sync request queue must not monopolize the
    # worker's GPUTick command: replay only the FIFO batch already queued
    # when the tick began. New requests retain their own queued GPU ticks.
    # Advance each fence ONLY after its callback returns normally.
    set(gpu_tick_lock_original [=[        while (!sync_requests.empty()) {
            auto request = std::move(sync_requests.front());
            sync_requests.pop_front();
            sync_request_mutex.unlock();
            request();
            current_sync_fence.fetch_add(1, std::memory_order_release);
            sync_request_mutex.lock();
            sync_request_cv.notify_all();
        }]=])
    set(gpu_tick_lock_safe [=[        for (auto remaining = sync_requests.size(); remaining != 0; --remaining) {
            auto request = std::move(sync_requests.front());
            sync_requests.pop_front();
            lck.unlock();
            request();
            current_sync_fence.fetch_add(1, std::memory_order_release);
            lck.lock();
            sync_request_cv.notify_all();
        }]=])
    string(FIND "${gpu_source}" "${gpu_tick_lock_original}" gpu_tick_lock_position)
    if(gpu_tick_lock_position LESS 0)
        message(FATAL_ERROR "Pinned native GPU callback lock ownership changed")
    endif()
    string(REPLACE "${gpu_tick_lock_original}" "${gpu_tick_lock_safe}"
        gpu_source "${gpu_source}")
    # Commit a GPU sync fence only after its callback enters the FIFO.
    # On a throwing copy/allocation, no unfulfillable fence may be issued.
    set(gpu_enqueue_fence_original [=[        const u64 fence = ++last_sync_fence;
        sync_requests.emplace_back(std::forward<Func>(action));
        return fence;]=])
    set(gpu_enqueue_fence_atomic [=[        sync_requests.emplace_back(std::forward<Func>(action));
        return ++last_sync_fence;]=])
    string(FIND "${gpu_source}" "${gpu_enqueue_fence_original}" gpu_enqueue_fence_position)
    if(gpu_enqueue_fence_position LESS 0)
        message(FATAL_ERROR "Pinned native GPU sync enqueue/fence contract changed")
    endif()
    string(REPLACE "${gpu_enqueue_fence_original}" "${gpu_enqueue_fence_atomic}"
        gpu_source "${gpu_source}")
    string(REPLACE "GPU::~GPU() = default;" "GPU::~GPU() { impl->NotifyShutdown(); }" gpu_source "${gpu_source}")
    string(REPLACE "void GPU::PushGPUEntries(s32 channel, Tegra::CommandList&& entries) {"
        "void GPU::PushGPUEntries(s32 channel, Tegra::CommandList&& entries) {\n    static std::atomic<unsigned> submissions{};\n    const auto count = ++submissions;\n    if (count <= 3) LOG_INFO(Render_OpenGL, \"EDEN_GUEST_GPU_SUBMIT count={} channel={}\", count, channel);"
        gpu_source "${gpu_source}")
    if(EDEN_DEV_PROFILE)
        string(PREPEND gpu_source "#include \"${EDEN_PORT_DIR}/performance.h\"\n")
        string(REPLACE "    if (count <= 3) LOG_INFO(Render_OpenGL, \"EDEN_GUEST_GPU_SUBMIT count={} channel={}\", count, channel);"
            "    if (count <= 3 || ::Eden::Performance::BootTrace()) LOG_INFO(Render_OpenGL, \"EDEN_GUEST_GPU_SUBMIT count={} channel={} entries={}\", count, channel, entries.command_lists.size());"
            gpu_source "${gpu_source}")
    endif()
endif()
write_derived("${PORT_BUILD_DIR}/gpu.cpp" "${gpu_source}")
list(APPEND video_sources "${PORT_BUILD_DIR}/gpu.cpp")
