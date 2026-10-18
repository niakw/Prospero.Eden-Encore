# SPDX-License-Identifier: GPL-3.0-or-later
# A native-only SELECTOR. Neither Fermi implementation is rebuilt by CMake.
# The conservative shipping semantics remain the default.
if(NOT PS5_NATIVE)
    return()
endif()

# Shader translator: maintained PRMT implementation, selected exclusively.
set(EDEN_MAINTAINED_NATIVE_PRMT
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/shader_recompiler/frontend/maxwell/translate/impl/not_implemented.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_PRMT}")
    message(FATAL_ERROR "Missing maintained PRMT shader source")
endif()
get_target_property(shader_sources shader_recompiler SOURCES)
list(FILTER shader_sources EXCLUDE REGEX "frontend/maxwell/translate/impl/not_implemented[.]cpp$")
set_property(TARGET shader_recompiler PROPERTY SOURCES "${shader_sources}")
target_sources(shader_recompiler PRIVATE "${EDEN_MAINTAINED_NATIVE_PRMT}")

# Native software blitter: preserve production backport and widened sizes.
set(EDEN_MAINTAINED_NATIVE_BLITTER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/engines/sw_blitter/blitter.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_BLITTER}")
    message(FATAL_ERROR "Missing maintained native software blitter")
endif()
get_target_property(sw_blitter_sources video_core SOURCES)
list(FILTER sw_blitter_sources EXCLUDE REGEX "engines/sw_blitter/blitter[.]cpp$")
set_property(TARGET video_core PROPERTY SOURCES "${sw_blitter_sources}")
target_sources(video_core PRIVATE "${EDEN_MAINTAINED_NATIVE_BLITTER}")

option(EDEN_UNQUALIFIED_FERMI2D_COPY "3D software blit experiments" OFF)
set(EDEN_MAINTAINED_FERMI_ROOT
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/engines")
if(EDEN_UNQUALIFIED_FERMI2D_COPY)
    set(EDEN_MAINTAINED_FERMI_FILE
        "${EDEN_MAINTAINED_FERMI_ROOT}/fermi_2d_experimental.cpp")
else()
    set(EDEN_MAINTAINED_FERMI_FILE
        "${EDEN_MAINTAINED_FERMI_ROOT}/fermi_2d_observed.cpp")
endif()
if(NOT EXISTS "${EDEN_MAINTAINED_FERMI_FILE}")
    message(FATAL_ERROR "Missing maintained native Fermi2D variant")
endif()
get_target_property(video_sources video_core SOURCES)
list(FILTER video_sources EXCLUDE REGEX "engines/fermi_2d[.]cpp$")
set_property(TARGET video_core PROPERTY SOURCES "${video_sources}")
target_sources(video_core PRIVATE "${EDEN_MAINTAINED_FERMI_FILE}")
