# TEST-ONLY original M12 generator, NEVER selected by the build.
# Experimental native replay bridge. Never part of normal native packages.
option(EDEN_GUEST_WRITE_BRIDGE_DEV "Compile inactive native deferred-write bridge" OFF)
if(EDEN_GUEST_WRITE_BRIDGE_DEV)
    if(NOT PS5_NATIVE OR NOT EDEN_PS5_VULKAN OR NOT EDEN_DEV_PROFILE)
        message(FATAL_ERROR "Guest write bridge requires native Vulkan developer profile")
    endif()
    target_compile_definitions(video_core PRIVATE EDEN_GUEST_WRITE_BRIDGE_DEV=1)

    # M04 migrated: complete experimental header maintained in Encore.
    set(EDEN_DEFERRED_MEMORY_HEADER
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/memory_manager.h")
    if(NOT EXISTS "${EDEN_DEFERRED_MEMORY_HEADER}")
        message(FATAL_ERROR "Missing maintained experimental memory manager header")
    endif()
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/include/video_core")
    configure_file("${EDEN_DEFERRED_MEMORY_HEADER}"
        "${PORT_BUILD_DIR}/include/video_core/memory_manager.h" COPYONLY)
    target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/include")
    target_include_directories(core BEFORE PRIVATE "${PORT_BUILD_DIR}/include")
    # M05: the synchronized dirty collector is a complete Encore-maintained
    # experimental header. No C++ lock rewriting is allowed in this module.
    set(EDEN_DEFERRED_DIRTY_HEADER
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/gpu_dirty_memory_manager.h")
    if(NOT EXISTS "${EDEN_DEFERRED_DIRTY_HEADER}")
        message(FATAL_ERROR "Missing maintained deferred dirty collector header")
    endif()
    file(MAKE_DIRECTORY "${PORT_BUILD_DIR}/deferred-core/core")
    configure_file("${EDEN_DEFERRED_DIRTY_HEADER}"
        "${PORT_BUILD_DIR}/deferred-core/core/gpu_dirty_memory_manager.h" COPYONLY)
    target_include_directories(core BEFORE PRIVATE "${PORT_BUILD_DIR}/deferred-core")
    target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/deferred-core")


    # M06 migrated: complete experimental translation unit is maintained
    # in encore-active. This recipe only selects/copies it.
    set(EDEN_DEFERRED_MEMORY_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/memory_manager.cpp")
    if(NOT EXISTS "${EDEN_DEFERRED_MEMORY_SOURCE}")
        message(FATAL_ERROR "Missing maintained deferred memory manager source")
    endif()
    configure_file("${EDEN_DEFERRED_MEMORY_SOURCE}"
        "${PORT_BUILD_DIR}/memory_manager_deferred.cpp" COPYONLY)

    # M07: the developer-only Vulkan replay variant is a full, maintained
    # source. The original Vulkan fork and normal build stay untouched.
    set(EDEN_DEFERRED_VULKAN_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp")
    if(NOT EXISTS "${EDEN_DEFERRED_VULKAN_SOURCE}")
        message(FATAL_ERROR "Missing maintained M07 deferred Vulkan source")
    endif()
    configure_file("${EDEN_DEFERRED_VULKAN_SOURCE}"
        "${PORT_BUILD_DIR}/vulkan_rasterizer_deferred.cpp" COPYONLY)

    # At the producer and fence boundaries, queued guest writes must drain.
    # M08: source-complete DEV DMA processor based on G20's actual selected
    # maintained source. No synthetic PORT_BUILD_DIR/dma_pusher.cpp exists.
    set(EDEN_DEFERRED_DMA_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/dma_pusher.cpp")
    set(EDEN_EXPECTED_DEV_DMA_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/dma_pusher_dev.cpp")
    if(NOT EDEN_MAINTAINED_GPU_DMA STREQUAL EDEN_EXPECTED_DEV_DMA_SOURCE)
        message(FATAL_ERROR "Deferred DMA bridge requires G20 DEV maintained source")
    endif()
    if(NOT EXISTS "${EDEN_DEFERRED_DMA_SOURCE}")
        message(FATAL_ERROR "Missing maintained M08 deferred DMA source")
    endif()
    configure_file("${EDEN_DEFERRED_DMA_SOURCE}"
        "${PORT_BUILD_DIR}/dma_pusher_deferred.cpp" COPYONLY)

    # The buffer clear fast path bypasses the old conditional DMA flush.
    # M09: select a complete experimental Encore-maintained source.
    set(EDEN_DEFERRED_MAXWELL_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/maxwell_dma.cpp")
    if(NOT EXISTS "${EDEN_DEFERRED_MAXWELL_SOURCE}")
        message(FATAL_ERROR "Missing maintained M09 guest bridge source")
    endif()
    configure_file("${EDEN_DEFERRED_MAXWELL_SOURCE}"
        "${PORT_BUILD_DIR}/maxwell_dma_deferred.cpp" COPYONLY)

    # M10: select a complete experimental Encore-maintained source.
    set(EDEN_DEFERRED_KEPLER_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/kepler_compute.cpp")
    if(NOT EXISTS "${EDEN_DEFERRED_KEPLER_SOURCE}")
        message(FATAL_ERROR "Missing maintained M10 guest bridge source")
    endif()
    configure_file("${EDEN_DEFERRED_KEPLER_SOURCE}"
        "${PORT_BUILD_DIR}/kepler_compute_deferred.cpp" COPYONLY)

    # An inline memory upload can touch cached guest data BEFORE the next
    # renderer draw/dispatch. Drain ahead of linear and tiled uploads alike.
    # M11: select a complete experimental Encore-maintained source.
    set(EDEN_DEFERRED_UPLOAD_SOURCE
        "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/engine_upload.cpp")
    if(NOT EXISTS "${EDEN_DEFERRED_UPLOAD_SOURCE}")
        message(FATAL_ERROR "Missing maintained M11 guest bridge source")
    endif()
    configure_file("${EDEN_DEFERRED_UPLOAD_SOURCE}"
        "${PORT_BUILD_DIR}/engine_upload_deferred.cpp" COPYONLY)

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
    # Only real RAM stores get pre-store intent; cache maintenance has none.
    set(intent_block [=[            if (!unsafe) {
                HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);
            }
            std::memcpy(ptr, reinterpret_cast<u8 const*>(buffer) + offset, copy_amount);]=])
    set(intent_zero [=[            HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);
            std::memset(ptr, 0, copy_amount);]=])
    set(intent_scalar "HandleRasterizerWrite(addr, sizeof(T));")
    set(intent_exclusive "HandleRasterizerWrite(GetInteger(vaddr), sizeof(T));")
    set(intent_exclusive128 "HandleRasterizerWrite(GetInteger(vaddr), sizeof(u128));")
    foreach(anchor IN ITEMS intent_block intent_zero intent_scalar
                            intent_exclusive intent_exclusive128)
        string(FIND "${bridge_cpu}" "${${anchor}}" found)
        if(found LESS 0)
            message(FATAL_ERROR "Native store-intent anchor changed (${anchor})")
        endif()
    endforeach()
    # Keep StoreFollows active across the actual memcpy, not just the
    # pre-store OnCPUWrite callback. Unsafe/untracked writes remain untagged.
    string(REPLACE "${intent_block}" [=[            if (!unsafe) {
                ::Eden::GpuDeferredWrite::ScopedGuestStoreIntent store_intent;
                HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);
                std::memcpy(ptr, reinterpret_cast<u8 const*>(buffer) + offset, copy_amount);
            } else {
                std::memcpy(ptr, reinterpret_cast<u8 const*>(buffer) + offset, copy_amount);
            }]=]
        bridge_cpu "${bridge_cpu}")
    string(REPLACE "${intent_zero}" [=[            ::Eden::GpuDeferredWrite::ScopedGuestStoreIntent store_intent;
            HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);
            std::memset(ptr, 0, copy_amount);]=]
        bridge_cpu "${bridge_cpu}")
    # Scalar and exclusive stores run AFTER GetPointerImpl's callback:
    # the old marker inside that callback went out of scope too early.
    # Put the marker at function entry so it also covers the memcpy/CAS.
    set(store_fn_scalar "inline void Write(Common::ProcessAddress vaddr, const T data) noexcept requires(std::is_trivially_copyable_v<T>) {")
    set(store_fn_exclusive "bool WriteExclusive(Common::ProcessAddress vaddr, const T data, const T expected) {")
    set(store_fn_exclusive128 "bool WriteExclusive128(Common::ProcessAddress vaddr, const u128 data, const u128 expected) {")
    foreach(entry IN ITEMS store_fn_scalar store_fn_exclusive store_fn_exclusive128)
        string(FIND "${bridge_cpu}" "${${entry}}" found)
        if(found LESS 0)
            message(FATAL_ERROR "Native guest store-function anchor changed (${entry})")
        endif()
        string(REPLACE "${${entry}}"
            "${${entry}}\n        ::Eden::GpuDeferredWrite::ScopedGuestStoreIntent store_intent;"
            bridge_cpu "${bridge_cpu}")
    endforeach()
    # An unmarked maintenance callback can inherit StoreFollows from an
    # enclosing guest write on the same host thread. Explicitly force NoStore
    # while running either dc cvac or dc civac rasterizer callback.
    set(intent_maintenance "HandleRasterizerWrite(GetInteger(current_vaddr), block_size);")
    # Count exact occurrences without CMake-regex backslash interpretation.
    string(REPLACE "${intent_maintenance}" "" maintenance_without "${bridge_cpu}")
    string(LENGTH "${bridge_cpu}" maintenance_before_length)
    string(LENGTH "${maintenance_without}" maintenance_after_length)
    string(LENGTH "${intent_maintenance}" maintenance_token_length)
    math(EXPR maintenance_count
        "(${maintenance_before_length} - ${maintenance_after_length}) / ${maintenance_token_length}")
    if(NOT maintenance_count EQUAL 2)
        message(FATAL_ERROR "Expected exactly two cache-maintenance write callbacks")
    endif()
    string(REPLACE "${intent_maintenance}"
        "::Eden::GpuDeferredWrite::ScopedGuestCacheMaintenanceIntent maintenance_intent; ${intent_maintenance}"
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
        "${EDEN_MAINTAINED_GPU_DMA}"
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
