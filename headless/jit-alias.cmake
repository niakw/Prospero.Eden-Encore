# Keep instruction addresses in the executable view; redirect only byte writes.
set(xbyak_root "${PROJECT_SOURCE_DIR}/.cache/cpm/xbyak/v7.40.1/xbyak")
# Full Xbyak v7.40.1 header is maintained in Encore. Keep sibling
# headers from the pinned CPM dependency; no C++ replacement in CMake.
set(EDEN_MAINTAINED_XBYAK_HEADER
    "${PORT_ROOT}/vendor/encore-active/eden-build/third_party/xbyak/xbyak.h")
if(NOT EXISTS "${EDEN_MAINTAINED_XBYAK_HEADER}")
    message(FATAL_ERROR "Missing maintained Xbyak writable alias header")
endif()
configure_file("${EDEN_MAINTAINED_XBYAK_HEADER}"
    "${PORT_BUILD_DIR}/include/xbyak/xbyak.h" COPYONLY)
# xbyak_util includes its sibling header: keep every consumer on the same layout.
foreach(sibling xbyak_mnemonic.h xbyak_util.h)
    configure_file("${xbyak_root}/${sibling}" "${PORT_BUILD_DIR}/include/xbyak/${sibling}" COPYONLY)
endforeach()
target_include_directories(common BEFORE PUBLIC "${PORT_BUILD_DIR}/include")
# Existing Ninja dependencies may still name the original, now-shadowed header.
# Change consumer commands as well so no old CodeArray layout survives incrementally.
target_compile_definitions(dynarmic PUBLIC EDEN_JIT_ALIAS_LAYOUT=1)

# Writable-alias memset already resides in both maintained BlockOfCode units.
set(EDEN_MAINTAINED_CONSTANT_POOL
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/dynarmic/backend/x64/constant_pool.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_CONSTANT_POOL}")
    message(FATAL_ERROR "Missing maintained JIT constant-pool source")
endif()
get_target_property(alias_sources dynarmic SOURCES)
list(FILTER alias_sources EXCLUDE REGEX "(^|/)constant_pool\\.cpp$")
set_property(TARGET dynarmic PROPERTY SOURCES "${alias_sources}")
target_sources(dynarmic PRIVATE "${EDEN_MAINTAINED_CONSTANT_POOL}")
