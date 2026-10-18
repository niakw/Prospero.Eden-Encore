#!/usr/bin/env python3
"""Confirm source-only Dynarmic BlockOfCode variants and native/host CMake selection.

Staging checks use the actual CMake selection block; behavioral fault tests
remain in check-jit-protection.py and check-jit-allocator.py.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64"
cmake = (root / "headless/CMakeLists.txt").read_text()
alias = (root / "headless/jit-alias.cmake").read_text()
assert not (root / "headless/jit-permissions.inc").exists()
assert "string(REPLACE" not in alias and "code_source" not in alias
assert 'write_derived("${PORT_BUILD_DIR}/block_of_code.cpp"' not in cmake
assert 'write_derived("${PORT_BUILD_DIR}/include/${code_relative}.h"' not in cmake
assert 'configure_file("${EDEN_BOC_UNIT}" "${PORT_BUILD_DIR}/block_of_code.cpp" COPYONLY)' in cmake
header = (active / "block_of_code.h").read_text()
assert "size_t protection_end = 0;" in header
assert "size_t executable_end = 0;" in header
assert "std::vector<size_t> patch_pages;" in header
for filename in ("block_of_code_host.cpp", "block_of_code_native.cpp"):
    contents = (active / filename).read_text()
    for needle in (
        "memset(writableAddress(ret), 0, alloc_size);",
        "void BlockOfCode::EnableWriting()",
        "void BlockOfCode::DisableWriting()",
        "void BlockOfCode::ClearCache()",
        "ASSERT(size <= 23);",
        "if (mprotect(reinterpret_cast<void*>(roundAddr), span, mode) != 0) std::abort();",
        "EdenJitAllocator()",
    ):
        assert needle in contents, (filename, needle)
native = (active / "block_of_code_native.cpp").read_text()
host = (active / "block_of_code_host.cpp").read_text()
assert "#define EDEN_JIT_ALIAS_NATIVE 1" in native
assert "EDEN_JIT_SPARSE_COMMIT_FAILED" in native
assert "EDEN_JIT_SPARSE_COMMIT_FAILED" not in host
begin = cmake.index("set(EDEN_MAINTAINED_BOC_ROOT ")
end = cmake.index("target_include_directories(dynarmic BEFORE PUBLIC", begin)
selection = cmake[begin:end]
with tempfile.TemporaryDirectory(prefix="eden-maintained-boc-") as tmp:
    directory = Path(tmp)
    for profile in ("native", "host"):
        build = directory / profile
        build.mkdir()
        script = directory / f"{profile}.cmake"
        script.write_text(
            "cmake_minimum_required(VERSION 3.25)\n"
            + f'set(PORT_ROOT "{root.as_posix()}")\n'
            + f'set(PORT_BUILD_DIR "{build.as_posix()}")\n'
            + f'set(PS5_NATIVE {"ON" if profile == "native" else "OFF"})\n'
            + selection
        )
        subprocess.run(["cmake", "-P", str(script)], check=True, timeout=40)
        expected = active / ("block_of_code_native.cpp" if profile == "native" else "block_of_code_host.cpp")
        assert (build / "block_of_code.cpp").read_bytes() == expected.read_bytes()
        assert (build / "include/dynarmic/backend/x64/block_of_code.h").read_bytes() == (active / "block_of_code.h").read_bytes()
print("MAINTAINED_BLOCK_OF_CODE_SELECTION_PASS host/native=2 W^X/alias complete sources")
