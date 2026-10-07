#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-only guard for the shipping CPU/JIT stability configuration."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmake = (root / 'headless/CMakeLists.txt').read_text()
main = (root / 'headless/main.cpp').read_text()
jit_list = (root / 'headless/jit_list.h').read_text()
jit_links = (root / 'headless/dynarmic/jit_links.inc').read_text()

assert 'option(EDEN_SHARED_JIT "Enable the experimental cross-core A64 JIT" OFF)' in cmake
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in cmake
assert 'set(EDEN_SHARED_JIT ON)' not in cmake
assert 'if(bits EQUAL 64 AND EDEN_SHARED_JIT)' in cmake
assert 'if(EDEN_SHARED_JIT OR EDEN_JIT_COMPILE_BATCH)' in cmake
assert 'if(EDEN_JIT_COMPILE_BATCH AND (PS5_NATIVE OR CMAKE_SYSTEM_NAME STREQUAL "Linux"))' in cmake
assert 'EDEN_SHARED_JIT_AVAILABLE=$<BOOL:${EDEN_SHARED_JIT}>' in cmake
assert 'EDEN_JIT_COMPILE_BATCH_AVAILABLE=$<BOOL:${EDEN_JIT_COMPILE_BATCH}>' in cmake
native = (root / 'tools/build-headless-native.sh').read_text()
assert '-DEDEN_SHARED_JIT="${EDEN_SHARED_JIT:-OFF}"' in native
assert '-DEDEN_JIT_COMPILE_BATCH="${EDEN_JIT_COMPILE_BATCH:-OFF}"' in native
host = (root / 'tools/build-headless-host.sh').read_text()
assert '-DEDEN_SHARED_JIT=OFF -DEDEN_JIT_COMPILE_BATCH=OFF' in host
package_build = (root / 'tools/build-package.sh').read_text()
assert 'export EDEN_SHARED_JIT=OFF EDEN_JIT_COMPILE_BATCH=OFF' in package_build
package_script = (root / 'tools/package-headless-native.sh').read_text()
assert "assert 'EDEN_SHARED_JIT:BOOL=OFF' in profile" in package_script
assert "assert 'EDEN_JIT_COMPILE_BATCH:BOOL=OFF' in profile" in package_script
memory_check = (root / 'headless/memory_check.cpp').read_text()
assert '#if EDEN_SHARED_JIT_AVAILABLE\n// Shared compiled code' in memory_check
assert '#if EDEN_SHARED_JIT_AVAILABLE\n// Dispatcher lookups' in memory_check
assert 'target_compile_definitions(eden-memory-check PRIVATE EDEN_SHARED_JIT_AVAILABLE=$<BOOL:${EDEN_SHARED_JIT}>)' in cmake

# Shipping builds cannot accidentally retain link-time references to JitGroup helpers.
assert '#if EDEN_SHARED_JIT_AVAILABLE\nextern "C" bool eden_jit_shared;' in main
assert '#if EDEN_SHARED_JIT_AVAILABLE\n#include "performance.h"' in jit_list
assert 'Production stability mode: saved-block precompilation is structurally unavailable' in jit_list

# Normal profiles always start with saved-block precompilation off.
assert 'Eden::JitList::enabled = false;' in main
assert 'CPU JIT: Dynarmic per-core; Encore cross-core sharing, successor batching and saved-block compile-ahead disabled' in main


# Wall-clock multicore must remain pre-emptible inside direct guest loops. Dynarmic's stock
# LinkBlockFast has no halt check; Encore guards only backward/self links to avoid a global cost.
assert 'wall_clock_back_edge = !e.conf.enable_cycle_counting && next_pc <= from_pc' in jit_links
assert 'wall_clock_back_edge ? EdenLinkCheck::Halt : EdenLinkCheck::None' in jit_links

print('Shipping JIT stability defaults PASS (per-core Dynarmic, no compile-ahead/batching/shared JIT)')
