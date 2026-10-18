#!/usr/bin/env python3
"""Verify G06/G07 Encore-owned source bodies and CMake selection (not guest execution)."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
owned = root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64"
scalar = root / "vendor/encore-active/eden-core/dynarmic/scalar"
cm = (root / "headless/CMakeLists.txt").read_text()
shared = (root / "headless/dynarmic/shared-jit.cmake").read_text()
selector = (root / "headless/scalar-memory.cmake").read_text()
header = (owned / "emit_x64_memory.h").read_text()
normal = (owned / "emit_x64_memory_standard.cpp.inc").read_text()
checked = (owned / "emit_x64_memory_checked.cpp.inc").read_text()
assert not (root / "headless/checked-fastmem.cmake").exists()
assert "macro(eden_shared_jit_memory_inc)" not in shared
assert "macro(eden_shared_jit_memory_header)" not in shared
assert "set(memory_source" not in selector and "string(REPLACE" not in selector
assert 'write_derived("${PORT_BUILD_DIR}/include/${memory_inc}"' not in cm
assert 'write_derived("${PORT_BUILD_DIR}/include/${memory_relative}"' not in cm
assert 'target_compile_definitions(dynarmic PRIVATE EDEN_A32_CHECKED_FASTMEM=1)' in cm
for body in (normal, checked):
    for direction in ("read", "write"):
        oracle = (scalar / f"scalar-memory-{direction}.inc").read_text()
        assert oracle in body, ("missing scalar access", direction)
    assert body.count("EmitExclusiveVAddrLookup(code, ctx, bitsize, *abort, vaddr, tmp2, tmp)") == 2
    assert body.count("if (fastmem_marker) fastmem_patch_info.emplace(") == 2
    assert body.count("#if defined(EDEN_SHARED_JIT_LAYOUT)") >= 4
    assert "ASSERT(conf.global_monitor && (conf.fastmem_pointer || conf.page_table));" in body
assert "constexpr bool checked_fastmem = std::is_same_v<AxxEmitContext, A32EmitContext>;" in checked
assert "constexpr bool checked_fastmem" not in normal
assert checked.count("EmitCheckedFastmemTest(code, vaddr") >= 2
assert "EmitCheckedFallbackLookup(code, ctx" in checked
assert header.count("ctx.conf.page_table_log2_stride <= 3") >= 2
assert header.count("if (*ctx.conf.page_table_marked_bit == 0)") == 2
assert "EmitExclusiveVAddrLookup(BlockOfCode& code" in header
assert "#if defined(EDEN_A32_CHECKED_FASTMEM)" in header
assert "#if defined(EDEN_SHARED_JIT_LAYOUT)" in header
assert "if constexpr (!requires(const UserConfig& c) { c.tpidr_el0; })" in header

h_start = cm.index('set(EDEN_MAINTAINED_MEMORY_HEADER\n')
h_end = cm.index('if(EDEN_A32_FASTMEM)\n    target_compile_definitions', h_start)
c_start = cm.index('set(EDEN_MAINTAINED_MEMORY_IMPL_ROOT\n')
c_end = cm.index('# New include overlays do not invalidate objects', c_start)
selection = cm[h_start:h_end] + cm[c_start:c_end]
assert shutil.which("cmake"), "CMake required to check selected staging paths"
with tempfile.TemporaryDirectory(prefix="encore-memory-g06-g07-") as d:
    tmp = Path(d)
    for checked_mode in (False, True):
        for shared_mode in (False, True):
            for native_mode in (False, True):
                label = f"{int(checked_mode)}-{int(shared_mode)}-{int(native_mode)}"
                output = tmp / label
                output.mkdir()
                script = tmp / (label + ".cmake")
                script.write_text(
                    "cmake_minimum_required(VERSION 3.25)\n"
                    + f'set(PORT_ROOT "{root.as_posix()}")\n'
                    + f'set(PORT_BUILD_DIR "{output.as_posix()}")\n'
                    + f'set(EDEN_A32_FASTMEM {"ON" if checked_mode else "OFF"})\n'
                    + f'set(EDEN_SHARED_JIT {"ON" if shared_mode else "OFF"})\n'
                    + f'set(PS5_NATIVE {"ON" if native_mode else "OFF"})\n'
                    + selection
                )
                subprocess.run(["cmake", "-P", str(script)], check=True, timeout=30)
                h_file = output / "include/dynarmic/backend/x64/emit_x64_memory.h"
                c_file = output / "include/dynarmic/backend/x64/emit_x64_memory.cpp.inc"
                assert h_file.read_bytes() == (owned / "emit_x64_memory.h").read_bytes()
                expected = owned / ("emit_x64_memory_checked.cpp.inc" if checked_mode else "emit_x64_memory_standard.cpp.inc")
                assert c_file.read_bytes() == expected.read_bytes()
print("ENCORE_MEMORY_G06_G07_PASS profiles=8 scalar=2 exclusive=2")
