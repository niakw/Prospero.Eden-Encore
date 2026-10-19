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

    # M12 consolidated: select a full experimental source matching the G13
    # native profile, without transforming guest C++ in this module.
    set(bridge_cpu_source "${EDEN_NATIVE_GUEST_SOURCE}")
    if(NOT bridge_cpu_source OR NOT EXISTS "${bridge_cpu_source}")
        message(FATAL_ERROR "Missing canonical Encore-native guest memory source")
    endif()
    if(EDEN_A32_FASTMEM)
        set(EDEN_DEFERRED_CPU_SOURCE
            "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/memory_ps5_a32.cpp")
    else()
        set(EDEN_DEFERRED_CPU_SOURCE
            "${PORT_ROOT}/vendor/encore-active/eden-core/guest-bridge/memory_ps5_standard.cpp")
    endif()
    if(NOT EXISTS "${EDEN_DEFERRED_CPU_SOURCE}")
        message(FATAL_ERROR "Missing maintained M12 guest bridge source")
    endif()
    get_target_property(bridge_core_sources core SOURCES)
    list(FIND bridge_core_sources "${bridge_cpu_source}" core_memory_index)
    if(core_memory_index EQUAL -1)
        message(FATAL_ERROR "Canonical native guest memory TU missing from core target")
    endif()
    list(REMOVE_ITEM bridge_core_sources "${bridge_cpu_source}")
    list(APPEND bridge_core_sources "${EDEN_DEFERRED_CPU_SOURCE}")
    set_property(TARGET core PROPERTY SOURCES "${bridge_core_sources}")
    # Preserve the native guest memory translation-unit-scoped ABI guards.
    set_property(SOURCE "${EDEN_DEFERRED_CPU_SOURCE}" TARGET_DIRECTORY core
        APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1")

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
