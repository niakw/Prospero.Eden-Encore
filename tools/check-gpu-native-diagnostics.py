#!/usr/bin/env python3
"""Check pinned Maxwell diagnostics and the bounded Fermi2D z=0 copy path.

Maxwell PRMT and nonzero Fermi2D layers remain unsupported.
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
fermi_copy_old = extract("fermi_copy_old")
fermi_copy_new = extract("fermi_copy_new")
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
assert "LOG_CRITICAL(Debug" in fermi_new
assert fermi_new.count("AssertFailSoftImpl();") == 1
assert fermi_new.index("AssertFailSoftImpl();") > fermi_new.index("if (count < 8)")
# Only layer-0, source depth>1 SrcCopy can use the software blitter.
# Existing decoding routines preserve block-depth layout and hardcode z=0;
# all other cases retain the original soft-assert semantics.
assert "base_layer_3d_copy = regs.src.depth > 1" in fermi_new
assert "regs.src.layer == 0 && regs.dst.layer == 0" in fermi_new
assert "regs.operation == Operation::SrcCopy" in fermi_new
assert "regs.clip_enable == 0" in fermi_new
assert "regs.src.depth != 1 && !base_layer_3d_copy" in fermi_new
assert "if (!rasterizer->AccelerateSurfaceCopy(src, regs.dst, config))" in fermi_copy_old
assert "if (base_layer_3d_copy)" in fermi_copy_new
assert "src.depth = 1;" in fermi_copy_new
assert "Surface dst = regs.dst;" in fermi_copy_new
assert "dst.depth = 1;" in fermi_copy_new
assert "EDEN_GPU_FERMI2D_Z0_SOFTWARE" in fermi_copy_new
assert "sw_blitter->Blit(src, dst, config);" in fermi_copy_new
assert "else if (!rasterizer->AccelerateSurfaceCopy(src, regs.dst, config))" in fermi_copy_new
assert "regs.src.depth = 1;" not in fermi_copy_new
assert "regs.dst.depth = 1;" not in fermi_copy_new
assert "sw_source_depth_at LESS 0 OR sw_dest_depth_at LESS 0 OR sw_z0_at LESS 0" in cmake

assert "file(READ" in cmake and cmake.count("write_derived(") == 2
assert 'target_sources(shader_recompiler PRIVATE' in cmake
assert 'target_sources(video_core PRIVATE' in cmake
print("GPU SOURCE CONTRACT: PRMT still throws; Fermi2D z=0 depth>1 uses software only; unsupported layers retain soft assert")
print("NOTE graphics correctness and PS5 native CMake build remain to be qualified")
