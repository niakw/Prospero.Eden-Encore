# SPDX-License-Identifier: GPL-3.0-or-later
# Add our frontend after the pinned project's real core targets exist.
set(EDEN_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
function(add_eden_headless)
    include("${EDEN_PORT_DIR}/CMakeLists.txt")
endfunction()
cmake_language(DEFER CALL add_eden_headless)
# One header is replaced for every target: common/sparse_large_vector.h, whose inline functions
# decide how Eden's large tables take their memory (headless/CMakeLists.txt writes the derived
# copy). This runs before any target exists, so the folder leads every include path: a source
# file that saw the original would mix two ways of committing the same table.
include_directories(BEFORE "${CMAKE_BINARY_DIR}/headless/sparse")
# The program names its sources in log lines and assertions. In a console build they are written
# relative to the trees they come from (src/..., build/..., headless/...), not with the folders of
# the machine that built it: a package must not carry those. Before any target exists, so it holds
# for every one.
if(PS5_NATIVE)
    # Native integration: the complete, maintained CMake source lives under
    # vendor/encore-active, rather than CMake string(REPLACE) rewrites.
    # Check precise upstream parity before applying the one compiler-flag fix.
    get_filename_component(EDEN_PORT_ROOT "${EDEN_PORT_DIR}/.." ABSOLUTE)
    set(EDEN_UPSTREAM_BUILD_CMAKE "${EDEN_PORT_ROOT}/vendor/sources/eden/src/CMakeLists.txt")
    set(EDEN_ACTIVE_BUILD_CMAKE "${EDEN_PORT_ROOT}/vendor/encore-active/eden-build/src/CMakeLists.txt")
    set(EDEN_SNAPSHOT_BUILD_CMAKE "${CMAKE_SOURCE_DIR}/src/CMakeLists.txt")
    foreach(path IN ITEMS "${EDEN_UPSTREAM_BUILD_CMAKE}" "${EDEN_ACTIVE_BUILD_CMAKE}"
                          "${EDEN_SNAPSHOT_BUILD_CMAKE}")
        if(NOT EXISTS "${path}")
            message(FATAL_ERROR "Missing native build source: ${path}")
        endif()
    endforeach()
    file(READ "${EDEN_UPSTREAM_BUILD_CMAKE}" eden_build_original)
    file(READ "${EDEN_ACTIVE_BUILD_CMAKE}" eden_build_active)
    file(READ "${EDEN_SNAPSHOT_BUILD_CMAKE}" eden_build_snapshot)
    string(REPLACE "-Wno-error=all" "-Wno-error-all"
           eden_build_reconstructed "${eden_build_active}")
    if(NOT eden_build_reconstructed STREQUAL eden_build_original)
        message(FATAL_ERROR "Maintained build CMake does not match pinned original + compiler fix")
    endif()
    if(NOT eden_build_snapshot STREQUAL eden_build_original
       AND NOT eden_build_snapshot STREQUAL eden_build_active)
        message(FATAL_ERROR "Pinned source CMake drifted; refusing to overwrite native build rules")
    endif()
    configure_file("${EDEN_ACTIVE_BUILD_CMAKE}" "${EDEN_SNAPSHOT_BUILD_CMAKE}" COPYONLY)
    # Original source remains available verbatim in vendor/sources/eden.
    unset(eden_build_original)
    unset(eden_build_active)
    unset(eden_build_snapshot)
    unset(eden_build_reconstructed)
    get_filename_component(EDEN_PORT_ROOT "${EDEN_PORT_DIR}/.." ABSOLUTE)
    add_compile_options("-ffile-prefix-map=${CMAKE_SOURCE_DIR}/="
                        "-ffile-prefix-map=${CMAKE_BINARY_DIR}/=build/"
                        "-ffile-prefix-map=${EDEN_PORT_ROOT}/=")
endif()
