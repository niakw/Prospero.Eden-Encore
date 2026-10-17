#!/usr/bin/env python3
"""Exercise maintained HLE source selection through real CMake configure.

No executable or package is built; this tests the source list in four
combinations of native and blocking-thread options.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
module = root / "vendor/encore-active/eden-threading/native-hle-overrides.cmake"
assert module.is_file()
cmake = shutil.which("cmake")
assert cmake, "CMake must be installed on the host CI runner"

pinned = (
    "hle/kernel/k_thread.cpp",
    "hle/kernel/k_scheduler.cpp",
    "hle/kernel/k_condition_variable.cpp",
    "hle/kernel/k_address_arbiter.cpp",
    "hle/kernel/svc/svc_condition_variable.cpp",
    "hle/kernel/svc/svc_address_arbiter.cpp",
    "hle/kernel/svc/svc_synchronization.cpp",
    "hle/kernel/svc/svc_thread.cpp",
)

fixture = r"""
cmake_minimum_required(VERSION 3.20)
project(HleSelection LANGUAGES CXX)
set(PORT_ROOT "@ROOT@")
set(PORT_BUILD_DIR "${CMAKE_BINARY_DIR}/headless")
add_library(core STATIC
@PINNED@
)
include("${PORT_ROOT}/vendor/encore-active/eden-threading/native-hle-overrides.cmake")
get_target_property(selected core SOURCES)

foreach(file IN ITEMS k_thread.cpp k_scheduler.cpp k_condition_variable.cpp
                     k_address_arbiter.cpp svc_condition_variable.cpp
                     svc_address_arbiter.cpp svc_synchronization.cpp svc_thread.cpp)
    if(file STREQUAL "k_thread.cpp")
        set(rel "hle/kernel/${file}")
        set(relative "core/hle/kernel/${file}")
        set(native_file ON)
    elseif(file STREQUAL "k_scheduler.cpp")
        set(rel "hle/kernel/${file}")
        set(relative "core/hle/kernel/${file}")
        set(native_file ${EDEN_BLOCKING_GUEST_CONTEXT_LOCKS})
    elseif(file MATCHES "^svc_")
        set(rel "hle/kernel/svc/${file}")
        set(relative "core/hle/kernel/svc/${file}")
        set(native_file ${PS5_NATIVE})
    else()
        set(rel "hle/kernel/${file}")
        set(relative "core/hle/kernel/${file}")
        set(native_file ${PS5_NATIVE})
    endif()
    list(FIND selected "${rel}" pinned_pos)
    list(FIND selected "${PORT_ROOT}/vendor/encore-active/eden-threading/src/${relative}" active_pos)
    if(native_file)
        if(NOT pinned_pos EQUAL -1 OR active_pos EQUAL -1)
            message(FATAL_ERROR "Native source wrong: ${file} pinned=${pinned_pos} active=${active_pos}")
        endif()
    else()
        if(pinned_pos EQUAL -1 OR NOT active_pos EQUAL -1)
            message(FATAL_ERROR "Pinned source wrong: ${file} pinned=${pinned_pos} active=${active_pos}")
        endif()
    endif()
endforeach()

get_target_property(include_dirs core INCLUDE_DIRECTORIES)
if(PS5_NATIVE)
    list(FIND include_dirs
       "${PORT_ROOT}/vendor/encore-active/eden-sync/src" sync_pos)
    if(sync_pos EQUAL -1)
        message(FATAL_ERROR "Native synchronization header root missing")
    endif()
endif()
message(STATUS "ENCORE_HLE_CMAKE_SELECTION_PASS native=${PS5_NATIVE} blocking=${EDEN_BLOCKING_GUEST_CONTEXT_LOCKS}")
"""

with tempfile.TemporaryDirectory(prefix="encore-hle-cmake-") as td:
    project = Path(td)
    for file in pinned:
        dest = project / file
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("int encore_stub() { return 0; }\n")
    members = "\n".join(f"    {relative}" for relative in pinned)
    (project / "CMakeLists.txt").write_text(
        fixture.replace("@ROOT@", root.as_posix()).replace("@PINNED@", members)
    )
    for native in ("OFF", "ON"):
        for blocking in ("OFF", "ON"):
            out = project / ("build-" + native + "-" + blocking)
            args = [cmake, "-S", str(project), "-B", str(out),
                    "-DPS5_NATIVE=" + native,
                    "-DEDEN_BLOCKING_GUEST_CONTEXT_LOCKS=" + blocking]
            check = subprocess.run(args, capture_output=True, text=True, timeout=45)
            assert check.returncode == 0, (native, blocking, check.stdout, check.stderr)
            assert "ENCORE_HLE_CMAKE_SELECTION_PASS" in check.stdout, check.stdout
            for helper in ("slab_helpers.h", "k_worker_task_manager.h"):
                generated = out / "headless/include/core/hle/kernel" / helper
                source = root / "vendor/encore-active/eden-threading/src/core/hle/kernel" / helper
                assert generated.is_file(), ("missing copied helper", native, blocking, helper)
                assert generated.read_bytes() == source.read_bytes(), (
                    "staged helper differs from maintained source", helper)
            print("ENCORE_HLE_CMAKE_SELECTION_PASS native=" + native + " blocking=" + blocking)
print("ENCORE_HLE_CMAKE_CONFIGURATION_ONLY_NO_NATIVE_BINARY_BUILT")
