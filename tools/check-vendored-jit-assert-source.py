#!/usr/bin/env python3
"""Verify the selected maintained Dynarmic assertion header and retired injection.

The former JIT fragment's Git blob digest is retained as an oracle, not as
a second C++ implementation outside vendor/encore-active.
"""
from pathlib import Path
import hashlib

root = Path(__file__).resolve().parents[1]
upstream = (root / "vendor/sources/eden/src/common/assert.h").read_bytes()
active = (root / "vendor/encore-active/eden-core/src/common/assert.h").read_bytes()
cmake = (root / "headless/CMakeLists.txt").read_text()
prefix = upstream + b"\n"
assert active.startswith(prefix), "maintained assertion header diverged from pinned base"
assert not (root / "headless/jit_assert.inc").exists(), "retired JIT assert fragment was reintroduced"
inline_override = active[len(prefix):]
assert inline_override.startswith(b"// SPDX-License-Identifier: GPL-3.0-or-later\n")
assert inline_override.count(b"#undef ASSERT_MSG") == 1
assert inline_override.count(b"#define ASSERT_MSG") == 1
# Git blob identity of the historical headless/jit_assert.inc before removal.
git_blob = b"blob " + str(len(inline_override)).encode("ascii") + b"\0" + inline_override
assert hashlib.sha1(git_blob).hexdigest() == "123f596ace3c09e589a8d7650013d83e5739a67b", (
    "maintained JIT assertion body drifted from the reviewed original"
)
assert active.count(b"#undef ASSERT_MSG") == 1
assert 'target_include_directories(dynarmic BEFORE PRIVATE "${EDEN_JIT_ASSERT_ROOT}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/jit-checks/common/assert.h"' not in cmake
assert 'set(EDEN_JIT_ASSERT_ROOT "${PORT_ROOT}/vendor/encore-active/eden-core/src")' in cmake
print("VENDORED_JIT_ASSERT_PARITY_OK single maintained header, historical Git blob matched")
