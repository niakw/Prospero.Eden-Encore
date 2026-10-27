# TEST-ONLY original X05 replay oracle, NEVER used for production.
# SPDX-License-Identifier: GPL-3.0-or-later
# The native CPU memory source is already derived for page-span safety.
# Reject overflowing guest VA ranges before the page-alignment loop.
# Original vendor source remains unchanged; drift fails generation.
if(NOT DEFINED eden_cpu_memory)
    message(FATAL_ERROR "Native guest range guard requires derived memory source")
endif()
set(eden_va_range_original "    Common::ProcessAddress end = base + size;")
string(FIND "${eden_cpu_memory}" "bool Memory::IsValidVirtualAddressRange(Common::ProcessAddress base, u64 size) const {\n${eden_va_range_original}" eden_va_range_start)
if(eden_va_range_start LESS 0)
    message(FATAL_ERROR "Pinned native guest VA range implementation changed")
endif()
# Do not include the trailing semicolon in a REGEX MATCHALL list entry:
# CMP0007 NEW counts the empty entries introduced by that delimiter.
string(REGEX MATCHALL "Common::ProcessAddress end = base \\+ size" eden_va_range_matches "${eden_cpu_memory}")
list(LENGTH eden_va_range_matches eden_va_range_count)
if(NOT eden_va_range_count EQUAL 1)
    message(FATAL_ERROR "Expected exactly one guest VA range endpoint")
endif()
set(eden_va_range_checked
    "    if (size > std::numeric_limits<u64>::max() - GetInteger(base)) {\n        return false;\n    }\n${eden_va_range_original}")
string(REPLACE "${eden_va_range_original}" "${eden_va_range_checked}"
    eden_cpu_memory "${eden_cpu_memory}")
string(PREPEND eden_cpu_memory "#include <limits>\n")
