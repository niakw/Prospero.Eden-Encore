#!/usr/bin/env python3
"""Prove the migrated PS5 fiber handoff compiles the exact previously derived code.

This byte-exact check prevents ABI/runtime drift when replacing CMake
string(REPLACE) generation with vendor/encore-active source.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pinned = (root/"vendor/sources/eden/src/common/fiber.cpp").read_text()
active = (root/"vendor/encore-active/eden-core/src/common/fiber.cpp").read_text()
cmake = (root/"headless/CMakeLists.txt").read_text()
first = "    to.impl->previous_fiber = weak_from.lock();"
old = '    // "from" might no longer be valid if the thread was killed\n    if (auto from = weak_from.lock()) {'
new = '    if (auto* from = static_cast<Fiber*>(transfer.data)) {'
assert pinned.count(first) == 1
assert pinned.count(old) == 1
expected = pinned.replace(first, first + "\n    ASSERT(to.impl->previous_fiber);\n    weak_from.reset();")
expected = expected.replace(old, new)
assert active == expected, "tracked fiber source is not exact historical native derived source"
assert 'set(EDEN_FIBER_ACTIVE "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/fiber.cpp")' in cmake
assert 'list(APPEND common_sources "${EDEN_FIBER_ACTIVE}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/fiber.cpp"' not in cmake
assert 'list(APPEND common_sources "${PORT_BUILD_DIR}/fiber.cpp")' not in cmake
print("PASS: exact fiber transition and weak-ref cleanup moved from CMake generation to tracked C++")
