#!/usr/bin/env python3
"""Check exact pinned GPU instrumentation contracts before native CMake.

This is not an implementation of Maxwell PRMT or layered Fermi blits.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cmake = (ROOT / "headless/gpu_native_observability.cmake").read_text()
launcher = (ROOT / "headless/CMakeLists.txt").read_text()
assert 'include("${CMAKE_CURRENT_LIST_DIR}/gpu_native_observability.cmake")' in launcher
assert cmake.count('if(NOT PS5_NATIVE)') == 1
def extract(name: str):
    m = re.search(r"set\(" + name + r" \[=\[(.*?)\]=\]\)", cmake, re.S)
    assert m, name
    return m.group(1)
prmt_old = extract("prmt_old")
prmt_new = extract("prmt_new")
fermi_old = extract("fermi_old")
fermi_new = extract("fermi_new")
assert prmt_old.count("ThrowNotImplemented(Opcode::PRMT_imm);") == 1
assert prmt_new.count("ThrowNotImplemented(Opcode::PRMT_imm);") == 1
assert "u64 insn" in prmt_new
assert "EDEN_GPU_PRMT_IMM raw=%016llx sample=%u" in prmt_new
assert "if (index < 8)" in prmt_new
assert "fetch_add(1, std::memory_order_relaxed)" in prmt_new
assert 'UNIMPLEMENTED_IF_MSG(regs.src.depth != 1, "Source depth is not one")' in fermi_old
assert "regs.src.depth != 1" in fermi_new
assert "EDEN_GPU_FERMI2D_UNSUPPORTED" in fermi_new
assert "if (count < 8)" in fermi_new
for field in ("regs.src.depth", "regs.dst.depth", "regs.src.layer",
              "regs.dst.layer", "regs.src.block_depth", "regs.dst.block_depth",
              "regs.src.Address()", "regs.dst.Address()"):
    assert field in fermi_new, field
assert "regs.src.depth = 1" not in fermi_new
assert "regs.dst.depth = 1" not in fermi_new
assert "src.size.depth = 1" not in fermi_new
assert "LOG_WARNING(HW_GPU" in fermi_new
assert "file(READ" in cmake and cmake.count("write_derived(") == 2
assert 'target_sources(shader_recompiler PRIVATE' in cmake
assert 'target_sources(video_core PRIVATE' in cmake
print("PASS pinned GPU diagnostic patch: raw PRMT preserved throw, layered Fermi unchanged, eight bounded samples per opcode/source")
print("NOTE graphics correctness and PS5 native CMake build remain to be qualified")
