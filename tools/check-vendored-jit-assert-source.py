#!/usr/bin/env python3
"""Verify maintained Dynarmic assertion header equals old derived content."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
upstream=(root/"vendor/sources/eden/src/common/assert.h").read_text()
override=(root/"headless/jit_assert.inc").read_text()
active=(root/"vendor/encore-active/eden-core/src/common/assert.h").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
assert active==upstream+"\n"+override
assert active.count("#undef ASSERT_MSG")==1
assert 'target_include_directories(dynarmic BEFORE PRIVATE "${EDEN_JIT_ASSERT_ROOT}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/jit-checks/common/assert.h"' not in cmake
assert 'set(EDEN_JIT_ASSERT_ROOT "${PORT_ROOT}/vendor/encore-active/eden-core/src")' in cmake
print("PASS: tracked JIT assertion header preserves exact failure/formatting override")
