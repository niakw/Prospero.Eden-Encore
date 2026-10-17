# SPDX-License-Identifier: GPL-3.0-or-later
# Native-only A32/A64 Dynarmic callback guard. The pinned guest read
# callbacks ignored CheckMemoryAccess' false result, unlike guest writes.
# Keep the same successful path; do not read guest RAM after a requested abort.
if(NOT PS5_NATIVE)
    return()
endif()
if(NOT bits EQUAL 32 AND NOT bits EQUAL 64)
    message(FATAL_ERROR "Unknown Dynarmic guest ISA for read guard")
endif()
foreach(width IN ITEMS 8 16 32 64)
    math(EXPR bytes "${width} / 8")
    set(read_original "    CheckMemoryAccess(vaddr, ${bytes}, Kernel::DebugWatchpointType::Read);\n    return m_memory.Read${width}(vaddr);")
    string(FIND "${wrapper}" "${read_original}" read_site)
    if(read_site LESS 0)
        message(FATAL_ERROR "Pinned A${bits} MemoryRead${width} abort check changed")
    endif()
    set(read_checked
        "    if (!CheckMemoryAccess(vaddr, ${bytes}, Kernel::DebugWatchpointType::Read)) {\n        return 0;\n    }\n    return m_memory.Read${width}(vaddr);")
    string(REPLACE "${read_original}" "${read_checked}" wrapper "${wrapper}")
endforeach()
if(bits EQUAL 64)
    set(read128_original
        "    CheckMemoryAccess(vaddr, 16, Kernel::DebugWatchpointType::Read);\n    return {m_memory.Read64(vaddr), m_memory.Read64(vaddr + 8)};")
    string(FIND "${wrapper}" "${read128_original}" read128_site)
    if(read128_site LESS 0)
        message(FATAL_ERROR "Pinned A64 MemoryRead128 abort check changed")
    endif()
    set(read128_checked
        "    if (!CheckMemoryAccess(vaddr, 16, Kernel::DebugWatchpointType::Read)) {\n        return {};\n    }\n    return {m_memory.Read64(vaddr), m_memory.Read64(vaddr + 8)};")
    string(REPLACE "${read128_original}" "${read128_checked}" wrapper "${wrapper}")
endif()
