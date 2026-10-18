# Archived G15 CMake oracle: TEST ONLY, never included in the native build.
# Executes against the pinned source in a temporary directory.
function(write_derived path content)
    file(WRITE "${path}" "${content}")
endfunction()
# The PS5 heap is bounded: avoid allocating/decompressing an executable merely
# to calculate its layout, and avoid vector growth duplicating a large BSS image.
if(PS5_NATIVE)
    file(READ "${PROJECT_SOURCE_DIR}/src/core/loader/nso.cpp" nso_source)
    set(old_nso_image "    Kernel::CodeSet codeset;\n    codeset.memory.resize(module_start + last_segment_it->location + last_segment_it->size);")
    set(new_nso_image [=[    const u64 initialized_size = module_start + u64(last_segment_it->location) + u64(last_segment_it->size);
    const u64 argument_size = should_pass_arguments && !Settings::values.program_args.GetValue().empty()
        ? NSO_ARGUMENT_DATA_ALLOCATION_SIZE : 0;
    const u64 final_size = (initialized_size + argument_size + u64(last_segment_it->bss_size) + 0xFFF) & ~u64(0xFFF);
    if (!final_size || final_size > UINT32_MAX) return std::nullopt;
    for (size_t i = 0; i < nso_header.segments.size(); ++i) {
        const auto& segment = nso_header.segments[i];
        const u64 stored_size = nso_header.IsSegmentCompressed(i)
            ? u64(nso_header.segments_compressed_size[i]) : u64(segment.size);
        if ((nso_header.IsSegmentCompressed(i) && (stored_size > INT32_MAX || u64(segment.size) > INT32_MAX)) ||
            u64(segment.offset) + stored_size > nso_file.GetSize() ||
            module_start + u64(segment.location) + u64(segment.size) > initialized_size)
            return std::nullopt;
    }
    // PS5 uses Dynarmic, not NCE: a layout query needs no executable bytes.
#ifdef HAS_NCE
#error Review PS5 NSO layout-only loading before enabling NCE
#endif
    if (!load_into_process) return load_base + final_size;
    std::fprintf(stderr, "[ProsperoEden] NSO %s image_bytes=%llu bss_bytes=%u\n",
                 nso_file.GetName().c_str(), static_cast<unsigned long long>(final_size),
                 static_cast<unsigned>(last_segment_it->bss_size));
    Kernel::CodeSet codeset;
    const auto name = nso_file.GetName();
    // A mod's patch changes code and data, which are here whole; only a dump wants the BSS too.
    const bool patched = pm && pm->HasNSOPatch(nso_header.build_id, name);
    const bool full_image = pm && Settings::values.dump_nso;
    // BSS belongs in guest memory, not a second almost-2-GiB heap buffer.
    codeset.memory.reserve(full_image ? final_size : initialized_size + argument_size);
    codeset.memory.resize(initialized_size);]=])
    string(FIND "${nso_source}" "${old_nso_image}" nso_offset)
    if(nso_offset LESS 0)
        message(FATAL_ERROR "Pinned NSO loader changed")
    endif()
    string(REPLACE "${old_nso_image}" "${new_nso_image}" nso_source "${nso_source}")
    string(REPLACE "    codeset.memory.resize(image_size);" "    if (full_image) codeset.memory.resize(image_size);" nso_source "${nso_source}")
    string(REPLACE "    const auto name = nso_file.GetName();\n    if (pm && (pm->HasNSOPatch(nso_header.build_id, name) || Settings::values.dump_nso)) {"
        "    if (patched || full_image) {" nso_source "${nso_source}")
    string(REPLACE "    // Load codeset for current process"
        "    // Initialize BSS and page padding directly, including reused guest pages.\n    if (codeset.memory.size() < image_size &&\n        !process.GetMemory().ZeroBlock(load_base + codeset.memory.size(), image_size - codeset.memory.size()))\n        return std::nullopt;\n\n    // Load codeset for current process" nso_source "${nso_source}")
    set(old_nso_decode [=[        std::vector<u8> decompressed_size(std::ranges::max_element(nso_header.segments, [](auto const& a, auto const& b) {
            return a.size < b.size;
        })->size);]=])
    string(REPLACE "${old_nso_decode}" "" nso_source "${nso_source}")
    string(REPLACE "            nso_file.Read(compressed_data.data(), nso_header.segments_compressed_size[i], nso_header.segments[i].offset);"
        "            auto* destination = codeset.memory.data() + module_start + nso_header.segments[i].location;\n            if (!nso_header.IsSegmentCompressed(i)) {\n                if (nso_file.Read(destination, nso_header.segments[i].size, nso_header.segments[i].offset) != nso_header.segments[i].size) return std::nullopt;\n            } else if (nso_file.Read(compressed_data.data(), nso_header.segments_compressed_size[i], nso_header.segments[i].offset) != nso_header.segments_compressed_size[i]) return std::nullopt;"
        nso_source "${nso_source}")
    set(old_nso_decompress [=[                int r = Common::Compression::DecompressDataLZ4(decompressed_size.data(), nso_header.segments[i].size, compressed_data.data(), nso_header.segments_compressed_size[i]);
                ASSERT(r == int(nso_header.segments[i].size));]=])
    set(new_nso_decompress [=[                int r = -1;
                if ((nso_header.flags >> 7) & 1) {
                    r = Common::Compression::DecompressDataZBIC(
                        std::span<u8>{destination, nso_header.segments[i].size},
                        std::span<const u8>{compressed_data.data(), nso_header.segments_compressed_size[i]});
                } else {
                    r = Common::Compression::DecompressDataLZ4(
                        destination, nso_header.segments[i].size,
                        compressed_data.data(), nso_header.segments_compressed_size[i]);
                }
                if (r != int(nso_header.segments[i].size)) return std::nullopt;]=])
    string(FIND "${nso_source}" "${old_nso_decompress}" nso_decompress_offset)
    if(nso_decompress_offset LESS 0)
        message(FATAL_ERROR "Pinned NSO decompression block changed")
    endif()
    string(REPLACE "${old_nso_decompress}" "${new_nso_decompress}" nso_source "${nso_source}")
    string(REPLACE "                std::memcpy(codeset.memory.data() + module_start + nso_header.segments[i].location, decompressed_size.data(), nso_header.segments[i].size);" "" nso_source "${nso_source}")
    string(REPLACE "            } else {\n                std::memcpy(codeset.memory.data() + module_start + nso_header.segments[i].location, compressed_data.data(), nso_header.segments[i].size);" "" nso_source "${nso_source}")
    string(PREPEND nso_source "#include <cstdio>\n#include <span>\n#include \"zbic_compression.h\"\n")
    write_derived("${PORT_BUILD_DIR}/nso.cpp" "${nso_source}")
    list(REMOVE_ITEM core_sources loader/nso.cpp)
    list(APPEND core_sources "${PORT_BUILD_DIR}/nso.cpp")
endif()
