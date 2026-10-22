#!/usr/bin/env python3
"""Enforce one compiled Dynarmic block-range owner with unchanged source blobs.

This checks file identity, CMake selection and the public 4-KiB contract.
It does not claim native JIT timing, console compatibility or FPS gains.
"""
from pathlib import Path
import hashlib

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active/eden-core/src/dynarmic/backend"
selector = (root / "headless/CMakeLists.txt").read_text()

def blob_id(path):
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

expected = {
    "block_range_information.cpp": "5d99bdb5a5b9e1d8a00a084467633cf058a0b670",
    "block_range_information.h": "d31186747a07cfacc0d374aefd7d8579b59b89c8",
}
for unit, signature in expected.items():
    assert blob_id(active / unit) == signature, ("unexpected Dynarmic source drift", unit)
    assert not (root / "headless/dynarmic" / unit).exists(), ("duplicate legacy owner", unit)
header = (active / "block_range_information.h").read_text()
cpp = (active / "block_range_information.cpp").read_text()
for symbol in ("AddRange", "ClearCache", "InvalidateRanges"):
    assert symbol in header and symbol in cpp, symbol
assert "static constexpr unsigned page_bits = 12;" in header
assert "if (static_cast<u64>(last_page - first_page) < pages.size())" in cpp
assert 'configure_file(\n    "${EDEN_MAINTAINED_BLOCK_RANGE_DIR}/block_range_information.h"' in selector
assert 'target_sources(dynarmic PRIVATE\n    "${EDEN_MAINTAINED_BLOCK_RANGE_DIR}/block_range_information.cpp")' in selector
assert 'target_compile_definitions(dynarmic PRIVATE EDEN_BLOCK_RANGE_PAGES=1)' in selector
assert 'write_derived("${PORT_BUILD_DIR}/include/dynarmic/backend/block_range_information.h"' not in selector
print("ENCORE_BLOCK_RANGE_UNIQUE_OWNER_PASS: two complete units, copied header, old owners absent")
