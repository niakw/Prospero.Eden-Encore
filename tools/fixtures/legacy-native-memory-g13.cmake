# TEST-ONLY historic G13/X05 parity oracle, NEVER included by a shipping target.
    file(READ "${eden_cpu_memory_tu}" eden_cpu_memory)
    set(unmapped_log "LOG_ERROR(HW_Memory, \"Unmapped ")
    string(FIND "${eden_cpu_memory}" "${unmapped_log}" unmapped_at)
    if(unmapped_at LESS 0)
        message(FATAL_ERROR "Pinned unmapped memory error diagnostics changed")
    endif()
    string(REPLACE "${unmapped_log}"
        "if (::Eden::Performance::ShouldLogUnmappedAccess()) LOG_ERROR(HW_Memory, \"Unmapped "
        eden_cpu_memory "${eden_cpu_memory}")
    # There are 11 error sites in the pinned memory.cpp; fail closed if upstream
    # changes the count instead of silently leaving one path unbounded.
    string(REGEX MATCHALL "ShouldLogUnmappedAccess\\(\\)" unmapped_calls "${eden_cpu_memory}")
    list(LENGTH unmapped_calls unmapped_count)
    if(NOT unmapped_count EQUAL 11)
        message(FATAL_ERROR "Pinned unmapped memory error sites changed: ${unmapped_count} != 11")
    endif()
    # Native guest CPU reads can also be requested from auxiliary host threads.
    # Their TLS host ID is outside the four guest-core array slots. Never
    # use that ID to index rasterizer_read_areas or share mapping scratch
    # with the GPU-owner/system-core write paths. Avoid a lock over a GPU
    # read fence: keep the normal guest-core read-area cache unchanged.
    set(eden_read_original [=[
        const size_t core = system.GetCurrentHostThreadID();
        auto& current_area = rasterizer_read_areas[core];
        gpu_device_memory->ApplyOpOnPointer(p, scratch_buffers[core], [&](DAddr address) {]=])
    set(eden_read_native [=[
        const size_t host_core = system.GetCurrentHostThreadID();
        thread_local Common::ScratchBuffer<u32> read_scratch;
        VideoCore::RasterizerDownloadArea auxiliary_read_area{};
        auto& current_area = host_core < Core::Hardware::NUM_CPU_CORES
            ? rasterizer_read_areas[host_core] : auxiliary_read_area;
        gpu_device_memory->ApplyOpOnPointer(p, read_scratch, [&](DAddr address) {]=])
    string(FIND "${eden_cpu_memory}" "${eden_read_original}" eden_read_position)
    if(eden_read_position LESS 0)
        message(FATAL_ERROR "Pinned native guest CPU read scratch/slot contract changed")
    endif()
    string(REPLACE "${eden_read_original}" "${eden_read_native}"
        eden_cpu_memory "${eden_cpu_memory}")
    # GPUDirtyMemoryManager::BuildTransform has a 32-bit mask of 64-byte
    # cells (2 KiB). HandleRasterizerWrite may pass a whole 4 KiB page.
    # Split before Collect, keeping the vendored code unchanged.
    set(eden_dirty_raw "            gpu_dirty_managers[core].Collect(address, size);")
    string(FIND "${eden_cpu_memory}" "${eden_dirty_raw}" eden_dirty_at)
    if(eden_dirty_at LESS 0)
        message(FATAL_ERROR "Pinned native GPUDirty Collect call changed")
    endif()
    string(REPLACE "${eden_dirty_raw}" [=[
            ::Eden::GpuDirty::ForEachRegion(address, size,
                [&](std::uint64_t subaddress, std::uint64_t span) {
                    gpu_dirty_managers[core].Collect(subaddress, span);
                });]=] eden_cpu_memory "${eden_cpu_memory}")
    string(PREPEND eden_cpu_memory "#include \"${EDEN_PORT_DIR}/gpu_dirty_region_split.h\"\n")
    # Guest spans end at addr + size - 1, not at addr + size.
    # The pinned expression reads one page too far on exact boundaries,
    # including one-past-end of the guest page table. Apply only to the
    # already-derived native memory translation unit.
    set(eden_span_original [=[        return (current_page_table->entries[addr >> YUZU_PAGEBITS].Block() == current_page_table->entries[(addr + size) >> YUZU_PAGEBITS].Block()) ? GetPointerSilent(addr) : nullptr;]=])
    # Exclude the terminal C++ semicolon: under CMP0007 NEW it also acts
    # as a CMake list separator and doubles the reported match count.
    string(REGEX MATCHALL "GetPointerSilent\\(addr\\) : nullptr" eden_span_calls "${eden_cpu_memory}")
    list(LENGTH eden_span_calls eden_span_count)
    if(NOT eden_span_count EQUAL 2)
        message(FATAL_ERROR "Pinned native guest span page-boundary contract changed")
    endif()
    string(REPLACE "${eden_span_original}" [=[        if (size == 0 || addr + (size - 1) < addr) {
            return nullptr;
        }
        const auto start_page = addr >> YUZU_PAGEBITS;
        const auto end_page = (addr + size - 1) >> YUZU_PAGEBITS;
        const auto& entries = current_page_table->entries;
        if (start_page >= entries.size() || end_page >= entries.size()) {
            return nullptr;
        }
        return entries[start_page].Block() == entries[end_page].Block()
            ? GetPointerSilent(addr) : nullptr;]=] eden_cpu_memory "${eden_cpu_memory}")
    # Bound guest range arithmetic in the already-generated native memory TU.
    # A wrapped end can otherwise let an invalid address range pass unchecked.
    include("${PORT_ROOT}/tools/fixtures/legacy-native-guest-range-overflow.cmake")
    set(eden_native_memory_tu "${PORT_BUILD_DIR}/memory-ps5.cpp")
    write_derived("${eden_native_memory_tu}"
        "#include \"${EDEN_PORT_DIR}/performance.h\"\n${eden_cpu_memory}")
