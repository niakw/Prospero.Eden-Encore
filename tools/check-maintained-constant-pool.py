#!/usr/bin/env python3
"""Pin maintained JIT constant-pool source parity and native selection."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
pinned = (root/"vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/constant_pool.cpp").read_text()
maintained = (root/"vendor/encore-active/eden-core/src/dynarmic/backend/x64/constant_pool.cpp").read_text()
selector = (root/"headless/jit-alias.cmake").read_text()
before = "        target_constant = constant;"
after = "        *reinterpret_cast<ConstantT*>(code.writableAddress(&target_constant)) = constant;"
assert pinned.count(before) == 1
assert maintained == pinned.replace(before, after)
assert selector.count('set(EDEN_MAINTAINED_CONSTANT_POOL') == 1
assert 'target_sources(dynarmic PRIVATE "${EDEN_MAINTAINED_CONSTANT_POOL}")' in selector
assert 'list(FILTER alias_sources EXCLUDE REGEX' in selector
assert 'constant_pool\\\\.cpp$' in selector
assert 'write_derived("${PORT_BUILD_DIR}/constant_pool.cpp"' not in selector
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/dynarmic/src/dynarmic/backend/x64/constant_pool.cpp"' not in selector
# Xbyak is now a complete Encore-maintained header. Preserve the
# actual COPYONLY selection rather than requiring the retired generator.
assert 'configure_file("${EDEN_MAINTAINED_XBYAK_HEADER}"' in selector
assert 'write_derived("${PORT_BUILD_DIR}/include/xbyak/xbyak.h"' not in selector
assert (root / "vendor/encore-active/eden-build/third_party/xbyak/xbyak.h").is_file()
print("VENDOR_MAINTAINED_CONSTANT_POOL_PARITY_PASS: exact edit and compiled target")
