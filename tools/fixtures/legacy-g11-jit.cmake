foreach(bits 32 64)
    set(relative "arm/dynarmic/arm_dynarmic_${bits}.cpp")
    file(READ "${PROJECT_SOURCE_DIR}/src/core/${relative}" wrapper)
    string(REPLACE "Common::PageTable::SIGN_BIT" "std::countl_zero(Common::PageTable::ATTRIBUTE_MASK)" wrapper "${wrapper}")
    # Without fastmem every LDREX/STREX left JIT code through a callback under the
    # global monitor lock (~7,000 pairs/frame in a measured racing game). The exclusive
    # emitter patch below supports page-table addresses; eden-memory-check covers
    # it for A64 and A32 (atomic loops, 1-4 cores).
    # Stability-first release default. The forced page-table exclusive path is faster, but a
    # hardware-only soft hang can leave the guest stopped while presentation/input remain alive.
    # Keep the callback/monitor path until inline exclusives are requalified on PS5 hardware.
    option(EDEN_INLINE_EXCLUSIVES "Inline page-table exclusive accesses" OFF)
    if(EDEN_INLINE_EXCLUSIVES)
        foreach(spacing "  " " ")
            string(REPLACE "config.fastmem_exclusive_access = config.fastmem_pointer${spacing}!= std::nullopt;"
                "config.fastmem_exclusive_access = true;" wrapper "${wrapper}")
        endforeach()
        string(FIND "${wrapper}" "config.fastmem_exclusive_access = true;" inline_exclusive_at)
        if(inline_exclusive_at LESS 0)
            message(FATAL_ERROR "Pinned exclusive-access configuration changed")
        endif()
    endif()
      string(REPLACE "std::uint32_t(512_MiB)" "std::uint32_t(16_MiB)" wrapper "${wrapper}")
      # The same dynamic physical headroom policy applies to every A64/A32
      # title. Guest code capacity is chosen once, before core construction.
      # Core 3/host keep 16 MiB. Both guest ISAs are not active together.
      if(PS5_NATIVE)
          if(bits EQUAL 64)
              set(jit_cache_sizes "::Eden::Experimental::A64CacheBytes(m_core_index, m_core_index == 0 ? 256_MiB : m_core_index < 3 ? 192_MiB : 16_MiB)")
          else()
              set(jit_cache_sizes "::Eden::Experimental::A32CacheBytes(m_core_index, m_core_index == 0 ? 512_MiB : m_core_index < 3 ? 64_MiB : 16_MiB)")
          endif()
          string(REPLACE "std::uint32_t(16_MiB)" "std::uint32_t(${jit_cache_sizes})" wrapper "${wrapper}")
          string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/experimental_performance.h\"\n")
      endif()
    set(derived "${PORT_BUILD_DIR}/arm_dynarmic_${bits}.cpp")
    # JIT entry/exit sampling is diagnostic instrumentation, not a shipping feature.
    # Keep all atomics, clocks and profiler calls out of the release hot path.
    if(EDEN_DEV_PROFILE)
        string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/performance.h\"\n")
        if(bits EQUAL 64)
            set(sample_pc "m_jit->GetPC()")
            set(sample_fp "m_jit->GetFpcr()")
        else()
            set(sample_pc "m_jit->Regs()[15]")
            set(sample_fp "m_jit->Fpscr()")
        endif()
        string(REPLACE "    return TranslateHaltReason(m_jit->Run());"
            "    const bool eden_detailed_cpu_sample = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed);\n    if (eden_detailed_cpu_sample && ::Eden::Performance::CpuSampleDue(m_core_index)) ::Eden::Performance::SampleCpu(m_core_index, Kernel::GetCurrentThread(m_system.Kernel()).GetThreadId(), ${sample_pc}, GetSvcNumber(), ${sample_fp});\n    ::Eden::Performance::cpu_state[m_core_index].phase.store(::Eden::Performance::CpuPhase::Guest, std::memory_order_release);\n    const auto halt = m_jit->Run();\n    ::Eden::Performance::cpu_state[m_core_index].phase.store(::Eden::Performance::CpuPhase::Kernel, std::memory_order_release);\n    if (eden_detailed_cpu_sample && ::Eden::Performance::CpuSampleDue(m_core_index)) ::Eden::Performance::SampleCpu(m_core_index, Kernel::GetCurrentThread(m_system.Kernel()).GetThreadId(), ${sample_pc}, GetSvcNumber(), ${sample_fp});\n    return TranslateHaltReason(halt);"
            wrapper "${wrapper}")
    endif()
    if(EDEN_DEV_PROFILE)
        if(bits EQUAL 32)
            string(REPLACE "u8 DynarmicCallbacks32::MemoryRead8(u32 vaddr) {"
                "u8 DynarmicCallbacks32::MemoryRead8(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "u16 DynarmicCallbacks32::MemoryRead16(u32 vaddr) {"
                "u16 DynarmicCallbacks32::MemoryRead16(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "u32 DynarmicCallbacks32::MemoryRead32(u32 vaddr) {"
                "u32 DynarmicCallbacks32::MemoryRead32(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "u64 DynarmicCallbacks32::MemoryRead64(u32 vaddr) {"
                "u64 DynarmicCallbacks32::MemoryRead64(u32 vaddr) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].reads);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite8(u32 vaddr, u8 value) {"
                "void DynarmicCallbacks32::MemoryWrite8(u32 vaddr, u8 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite16(u32 vaddr, u16 value) {"
                "void DynarmicCallbacks32::MemoryWrite16(u32 vaddr, u16 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite32(u32 vaddr, u32 value) {"
                "void DynarmicCallbacks32::MemoryWrite32(u32 vaddr, u32 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "void DynarmicCallbacks32::MemoryWrite64(u32 vaddr, u64 value) {"
                "void DynarmicCallbacks32::MemoryWrite64(u32 vaddr, u64 value) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive8(u32 vaddr, u8 value, u8 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive8(u32 vaddr, u8 value, u8 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive16(u32 vaddr, u16 value, u16 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive16(u32 vaddr, u16 value, u16 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive32(u32 vaddr, u32 value, u32 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive32(u32 vaddr, u32 value, u32 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
            string(REPLACE "bool DynarmicCallbacks32::MemoryWriteExclusive64(u32 vaddr, u64 value, u64 expected) {"
                "bool DynarmicCallbacks32::MemoryWriteExclusive64(u32 vaddr, u64 value, u64 expected) {\n    ::Eden::Performance::CountJit(::Eden::Performance::jit_callbacks[m_parent.m_core_index].exclusive_writes);"
                wrapper "${wrapper}")
        endif()
        string(REPLACE "    m_jit.emplace(config);"
            "    std::printf(\"EDEN_DEV_JIT bits=${bits} core=%zu cache=%u\\n\", m_core_index, config.code_cache_size);\n    m_jit.emplace(config);"
            wrapper "${wrapper}")
        if(bits EQUAL 64)
            # Guest calls through null pointers (seen in a boot race):
            # dump the guest code around the return chain for offline disassembly.
            set(no_execute "        LOG_CRITICAL(Core_ARM, \"Cannot execute instruction at unmapped address {:#016x}\", pc);\n")
            string(FIND "${wrapper}" "${no_execute}" no_execute_at)
            if(no_execute_at LESS 0)
                message(FATAL_ERROR "Pinned no-execute fault handler changed")
            endif()
            string(REPLACE "${no_execute}" "${no_execute}        ::Eden::CrashSite::Dump(m_memory, *m_parent.m_jit);\n        ::Eden::CrashSite::DumpThreads(\"fault\", *m_process);\n"
                wrapper "${wrapper}")
            string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/crash_site.h\"\n")
            # dev-settings watch=: writes into the watched range reach these callbacks (its
            # pages are marked debug) and are reported with the guest thread (watch.h).
            set(watch_context "m_memory, *m_parent.m_jit, Kernel::GetCurrentThread(m_parent.m_system.Kernel()), m_parent.m_core_index")
            foreach(write IN ITEMS "MemoryWrite8(u64 vaddr, u8 value)|1|value" "MemoryWrite16(u64 vaddr, u16 value)|2|value"
                    "MemoryWrite32(u64 vaddr, u32 value)|4|value" "MemoryWrite64(u64 vaddr, u64 value)|8|value"
                    "MemoryWrite128(u64 vaddr, Dynarmic::A64::Vector value)|16|value[0]"
                    "MemoryWriteExclusive8(u64 vaddr, std::uint8_t value, std::uint8_t expected)|1|value"
                    "MemoryWriteExclusive16(u64 vaddr, std::uint16_t value, std::uint16_t expected)|2|value"
                    "MemoryWriteExclusive32(u64 vaddr, std::uint32_t value, std::uint32_t expected)|4|value"
                    "MemoryWriteExclusive64(u64 vaddr, std::uint64_t value, std::uint64_t expected)|8|value"
                    "MemoryWriteExclusive128(u64 vaddr, Dynarmic::A64::Vector value, Dynarmic::A64::Vector expected)|16|value[0]")
                string(REPLACE "|" ";" write_parts "${write}")
                list(GET write_parts 0 write_signature)
                list(GET write_parts 1 write_size)
                list(GET write_parts 2 write_value)
                set(write_head "DynarmicCallbacks64::${write_signature} {\n")
                string(FIND "${wrapper}" "${write_head}" write_at)
                if(write_at LESS 0)
                    message(FATAL_ERROR "Pinned A64 write callback changed: ${write_signature}")
                endif()
                string(REPLACE "${write_head}"
                    "${write_head}    if (::Eden::Watch::Hit(vaddr, ${write_size})) ::Eden::Watch::Report(vaddr, ${write_size}, u64(${write_value}), ${watch_context});\n"
                    wrapper "${wrapper}")
            endforeach()
            string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/watch.h\"\n#include \"core/hle/kernel/k_thread.h\"\n#include \"core/hle/kernel/kernel.h\"\n")
        endif()
    endif()
    if(PS5_NATIVE)
        # Do not silently lose a game when a dynamically sized code arena
        # cannot be allocated contiguously. Retry only allocator errors at
        # smaller capacities down to the old qualified per-core baseline.
        # The 8 MiB null-JIT path is intentionally left untouched.
        set(jit_init_site "    m_jit.emplace(config);")
        string(FIND "${wrapper}" "${jit_init_site}" jit_init_at)
        if(jit_init_at LESS 0)
            message(FATAL_ERROR "Pinned Dynarmic guest JIT construction changed")
        endif()
        if(bits EQUAL 64)
            set(jit_legacy_baseline "::Eden::Experimental::kA64Baseline[m_core_index]")
        else()
            set(jit_legacy_baseline "::Eden::Experimental::kA32Baseline[m_core_index]")
        endif()
        string(REPLACE "${jit_init_site}"
            "    ::Eden::JitStartup::ConstructWithCapacityFallback(\n        config.code_cache_size, ${jit_legacy_baseline}, ${bits}, m_core_index,\n        [&]() { m_jit.emplace(config); });"
            wrapper "${wrapper}")
        string(PREPEND wrapper "#include \"${EDEN_PORT_DIR}/jit-startup-retry.h\"\n")
    endif()
    # Native guest callbacks must not read RAM after abort/watchpoint refusal.
    if(PS5_NATIVE)
        include("${PORT_ROOT}/tools/fixtures/legacy-x06-native-jit-memory-read-guard.cmake")
    endif()
    write_derived("${derived}" "#include <bit>\n${wrapper}")
    list(REMOVE_ITEM core_sources "${relative}")
    list(APPEND core_sources "${derived}")
endforeach()
