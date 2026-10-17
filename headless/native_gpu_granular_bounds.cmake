# SPDX-License-Identifier: GPL-3.0-or-later
# Native-derived GPU address manager only. Invalid addresses must never
# index page vectors; a continuous big page checks its byte offset, not
# its big-page index. Reject arithmetic overflow without wrapping.
if(NOT DEFINED eden_gpu_span_src)
    message(FATAL_ERROR "Granular range fix requires native-derived GPU memory source")
endif()
set(granular_head "bool MemoryManager::IsGranularRange(GPUVAddr gpu_addr, std::size_t size) const {\n")
set(granular_guard "    if (gpu_addr >= address_space_size || size == 0 || size > address_space_size - gpu_addr) {\n        return false;\n    }\n")
string(FIND "${eden_gpu_span_src}" "${granular_head}" granular_at)
if(granular_at LESS 0)
    message(FATAL_ERROR "Pinned IsGranularRange declaration changed")
endif()
string(REGEX MATCHALL "bool MemoryManager::IsGranularRange\\(" granular_matches "${eden_gpu_span_src}")
list(LENGTH granular_matches granular_count)
if(NOT granular_count EQUAL 1)
    message(FATAL_ERROR "Expected exactly one GPU granular range method")
endif()
string(REPLACE "${granular_head}" "${granular_head}${granular_guard}"
    eden_gpu_span_src "${eden_gpu_span_src}")

set(granular_big_old "            const std::size_t page{(page_index & big_page_mask) + size};\n            return page <= big_page_size;")
set(granular_big_new "            return size <= big_page_size - (gpu_addr & big_page_mask);")
string(FIND "${eden_gpu_span_src}" "${granular_big_old}" big_old_at)
if(big_old_at LESS 0)
    message(FATAL_ERROR "Pinned GPU big-page span calculation changed")
endif()
string(REPLACE "${granular_big_old}" "${granular_big_new}"
    eden_gpu_span_src "${eden_gpu_span_src}")

set(granular_short_old "const std::size_t page{(gpu_addr & Core::DEVICE_PAGEMASK) + size};\n")
# Match without the trailing semicolon: CMake lists otherwise split
# each regex result into two elements under modern list policies.
string(REGEX MATCHALL "const std::size_t page\\{\\(gpu_addr & Core::DEVICE_PAGEMASK\\) \\+ size\\}" short_matches "${eden_gpu_span_src}")
list(LENGTH short_matches short_count)
if(NOT short_count EQUAL 2)
    message(FATAL_ERROR "Pinned GPU short-page span calculations changed")
endif()
string(REPLACE "${granular_short_old}" "" eden_gpu_span_src "${eden_gpu_span_src}")
string(REPLACE "return page <= Core::DEVICE_PAGESIZE;"
    "return size <= Core::DEVICE_PAGESIZE - (gpu_addr & Core::DEVICE_PAGEMASK);"
    eden_gpu_span_src "${eden_gpu_span_src}")
