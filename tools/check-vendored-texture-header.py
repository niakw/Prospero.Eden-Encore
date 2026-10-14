#!/usr/bin/env python3
"""Verify exact original texture-cache helper with only Boost version include.

Byte-equivalence guards migrating one former derived header to the tracked
active source tree. This changes no runtime algorithm or cache ownership.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
original = (root/"vendor/sources/eden/src/video_core/texture_cache/util.h").read_text()
active = (root/"vendor/encore-active/eden-core/src/video_core/texture_cache/util.h").read_text()
cmake = (root/"headless/CMakeLists.txt").read_text()
anchor = "#include <boost/container/small_vector.hpp>"
assert original.count(anchor) == 1
assert "#include <boost/version.hpp>" not in original
assert active == original.replace(anchor, anchor + "\n#include <boost/version.hpp>")
assert 'set(EDEN_SMALL_VECTOR_ROOT "${PORT_ROOT}/vendor/encore-active/eden-core/src")' in cmake
assert 'target_include_directories(video_core BEFORE PRIVATE "${EDEN_SMALL_VECTOR_ROOT}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/small-vector/video_core/texture_cache/util.h"' not in cmake
assert "#include <boost/version.hpp>" in active
print("PASS: tracked GPU texture-cache header matches exact historic derived header")
