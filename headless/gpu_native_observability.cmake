# SPDX-License-Identifier: GPL-3.0-or-later
# A native-only SELECTOR. Neither Fermi implementation is rebuilt by CMake.
# The conservative shipping semantics remain the default.
if(NOT PS5_NATIVE)
    return()
endif()

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
