#!/usr/bin/env python3
"""Check Maxwell PRMT Index and bounded Fermi2D software slice support.

Other PRMT modes and unsupported block-linear layers remain unimplemented.
This is a source contract, not a native graphics correctness test.
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
prmt_reg_old = extract("prmt_reg_old")
prmt_reg_new = extract("prmt_reg_new")
prmt_reference = extract("prmt_reference")
fermi_old = extract("fermi_old")
fermi_new = extract("fermi_new")
fermi_layer_old = extract("fermi_layer_old")
fermi_layer_new = extract("fermi_layer_new")
fermi_copy_old = extract("fermi_copy_old")
fermi_copy_new = extract("fermi_copy_new")
assert prmt_old.count("ThrowNotImplemented(Opcode::PRMT_imm);") == 1
assert prmt_new.count("ThrowNotImplemented(Opcode::PRMT_imm);") == 1
assert "u64 insn" in prmt_new
assert "EDEN_GPU_PRMT_IMM raw=%016llx mode=%u sample=%u" in prmt_new
assert "EDEN_GPU_PRMT_IMM_INDEX raw=%016llx selector=%04x sample=%u" in prmt_new
assert "const unsigned mode = static_cast<unsigned>((insn >> 48) & 7ULL);" in prmt_new
assert "if (mode != 0)" in prmt_new
assert "const unsigned selector = static_cast<unsigned>((insn >> 20) & 0xffffULL);" in prmt_new
assert "const IR::U32 a{GetReg8(insn)};" in prmt_new
assert "const IR::U32 b{GetReg39(insn)};" in prmt_new
assert "const unsigned nibble = (selector >> (output_byte * 4)) & 15u;" in prmt_new
assert "const IR::U32 source = (nibble & 4u) ? b : a;" in prmt_new
assert "ir.BitFieldExtract(source, ir.Imm32(src_offset + 7u), ir.Imm32(1), true)" in prmt_new
assert "ir.BitwiseAnd(extracted, ir.Imm32(255))" in prmt_new
assert "ir.ShiftLeftLogical(value, ir.Imm32(output_byte * 8u))" in prmt_new
assert "X(static_cast<IR::Reg>(insn & 255ULL), result);" in prmt_new
assert prmt_new.index("if (mode != 0)") < prmt_new.index("ThrowNotImplemented(Opcode::PRMT_imm);")
assert prmt_new.index("ThrowNotImplemented(Opcode::PRMT_imm);") < prmt_new.index("const unsigned selector")
# Independently model the NVIDIA SM50 Index-mode nibble semantics from Nouveau.
# This model guards sign replication, not merely byte extraction/reordering.
def prmt_index(a: int, b: int, selector: int) -> int:
    result = 0
    for out in range(4):
        nibble = (selector >> (out * 4)) & 0xf
        source = b if nibble & 4 else a
        value = (source >> ((nibble & 3) * 8)) & 0xff
        if nibble & 8:
            value = 0xff if value & 0x80 else 0
        result |= value << (out * 8)
    return result

assert prmt_index(0x11223344, 0x55667788, 0x3210) == 0x11223344
assert prmt_index(0x11223344, 0x55667788, 0x7654) == 0x55667788
assert prmt_index(0x80abcdef, 0, 0xbbbb) == 0xffffffff
assert prmt_index(0x11223344, 0x55667788, 0xffff) == 0
assert prmt_index(0xff000000, 0, 0x000b) == 0xff
assert "constexpr unsigned EdenPrmtIndexReference(" in prmt_reference
assert prmt_reference.count("static_assert(EdenPrmtIndexReference(") >= 4
assert "${gpu_bounded_sample_helper}\\n${prmt_reference}\\n${prmt_source}" in cmake
# A register selector uses identical nibble semantics, but is evaluated
# dynamically in the shader IR rather than once at translation time.
assert prmt_reg_old.count("ThrowNotImplemented(Opcode::PRMT_reg);") == 1
assert prmt_reg_new.count("ThrowNotImplemented(Opcode::PRMT_reg);") == 1
assert "const unsigned mode = static_cast<unsigned>((insn >> 48) & 7ULL);" in prmt_reg_new
assert "if (mode != 0)" in prmt_reg_new
assert "const IR::U32 selector{GetReg20(insn)};" in prmt_reg_new
assert "const IR::U32 a{GetReg8(insn)};" in prmt_reg_new
assert "const IR::U32 b{GetReg39(insn)};" in prmt_reg_new
assert "ir.ShiftRightLogical(selector, ir.Imm32(i * 4u))" in prmt_reg_new
assert "ir.ShiftRightLogical(source, byte_shift)" in prmt_reg_new
assert "ir.BitwiseAnd(selected_byte, ir.Imm32(128))" in prmt_reg_new
assert "ir.Select(signed_replication, replicated, selected_byte)" in prmt_reg_new
assert "X(static_cast<IR::Reg>(insn & 255ULL), result);" in prmt_reg_new
assert "EDEN_GPU_PRMT_REG_INDEX raw=%016llx sample=%u" in prmt_reg_new
assert "EDEN_GPU_PRMT_REG_UNSUPPORTED raw=%016llx mode=%u sample=%u" in prmt_reg_new
assert 'message(FATAL_ERROR "Pinned Maxwell PRMT_reg exception anchor changed")' in cmake
assert prmt_index(0x01234567, 0x89abcdef, 0x1111) == 0x45454545

assert "if (index < 8)" in prmt_new
# Diagnostic counters must saturate at eight instead of performing atomic
# read-modify-write on every repeated shader translation or Fermi blit.
assert "unsigned EdenGpuBoundedSample(std::atomic<unsigned>& samples) noexcept" in cmake
assert "compare_exchange_weak(current, current + 1u," in cmake
assert "while (current < 8u)" in cmake
assert "return 8u;" in cmake
assert cmake.count("${gpu_bounded_sample_helper}") == 2
for part in (prmt_new, prmt_reg_new, fermi_new, fermi_layer_new, fermi_copy_new):
    assert ".fetch_add(1, std::memory_order_relaxed)" not in part
assert prmt_new.count("EdenGpuBoundedSample(") == 2
assert prmt_reg_new.count("EdenGpuBoundedSample(") == 2
assert fermi_new.count("EdenGpuBoundedSample(") == 1
assert fermi_layer_new.count("EdenGpuBoundedSample(") == 1
assert fermi_copy_new.count("EdenGpuBoundedSample(") == 2
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
assert "(regs.src.depth > 1 || regs.dst.depth > 1)" in fermi_new
assert "regs.src.depth >= 1 && regs.dst.depth >= 1" in fermi_new
assert "regs.src.layer == 0 && regs.dst.layer == 0" in fermi_new
assert "regs.operation == Operation::SrcCopy" in fermi_new
assert "regs.clip_enable == 0" in fermi_new
assert "regs.src.depth != 1 && !base_layer_3d_copy && !pitch_layer_copy" in fermi_new
assert "if (!rasterizer->AccelerateSurfaceCopy(src, regs.dst, config))" in fermi_copy_old
assert "if (base_layer_3d_copy || pitch_layer_copy)" in fermi_copy_new
# New software layer paths reject negative/overflowed subrects without
# modifying the historical GPU-accelerated normal-depth path.
assert "const bool rect_valid =" in fermi_copy_new
assert "config.src_x0 >= 0 && config.src_y0 >= 0" in fermi_copy_new
assert "config.dst_x0 >= 0 && config.dst_y0 >= 0" in fermi_copy_new
assert "config.src_x1 > config.src_x0" in fermi_copy_new
assert "config.dst_y1 > config.dst_y0" in fermi_copy_new
assert "static_cast<u64>(config.src_x1) <= src.width" in fermi_copy_new
assert "static_cast<u64>(config.src_y1) <= src.height" in fermi_copy_new
assert "static_cast<u64>(config.dst_x1) <= regs.dst.width" in fermi_copy_new
assert "static_cast<u64>(config.dst_y1) <= regs.dst.height" in fermi_copy_new
assert "EDEN_GPU_FERMI2D_SOFTWARE_BOUNDS_INVALID" in fermi_copy_new
assert "const bool copy_storage_valid =" in fermi_copy_new
assert "src_bpp != 0 && dst_bpp != 0" in fermi_copy_new
assert "static_cast<u64>(surface.pitch) * surface.height <= 0xffffffffULL" in fermi_copy_new
assert "const bool copy_sizes_valid = rect_valid && copy_storage_valid" in fermi_copy_new
assert "const auto valid_byte_count =" in fermi_copy_new
assert "bpp == 0 || bpp > 0xffffffffULL" in fermi_copy_new
assert "width <= max / bpp" in fermi_copy_new
assert "height <= max / (width * bpp)" in fermi_copy_new
assert "valid_byte_count(config.src_x0, config.src_x1," in fermi_copy_new
assert "valid_byte_count(config.dst_x0, config.dst_x1," in fermi_copy_new

# The admissible decoded byte count is bounded without first evaluating
# width*height*bpp. This matters even for intentionally malformed guest regs.
def valid_byte_count(width: int, height: int, bpp: int) -> bool:
    cap = (1 << 32) - 1
    return (width > 0 and height > 0 and 0 < bpp <= cap
            and width <= cap // bpp and height <= cap // (width * bpp))
assert valid_byte_count(1920, 1080, 4)
assert valid_byte_count(65535, 65535, 1)
assert not valid_byte_count(65536, 65536, 1)
assert not valid_byte_count((1 << 31) - 1, (1 << 31) - 1, 16)
assert not valid_byte_count(1920, 1080, 0)
assert not valid_byte_count(1, 1, (1 << 32))
assert fermi_copy_new.index("if (!copy_sizes_valid)") < fermi_copy_new.index("sw_blitter->Blit(src, dst, config);")

# Nonzero layers are only copied using simple pitch-linear planes.
# The layer stride is pitch*height; 3D swizzled z>0 remains unsupported.
assert "regs.src.layer != 0" in fermi_layer_old
assert "regs.dst.layer != 0" in fermi_layer_old
assert "const bool pitch_layer_copy =" in fermi_layer_new
assert "regs.src.linear == MemoryLayout::Pitch" in fermi_layer_new
assert "regs.dst.linear == MemoryLayout::Pitch" in fermi_layer_new
assert "regs.src.layer < regs.src.depth && regs.dst.layer < regs.dst.depth" in fermi_layer_new
assert "regs.src.format == regs.dst.format" in fermi_layer_new
assert "BytesPerBlock(PixelFormatFromRenderTargetFormat(regs.src.format))" in fermi_layer_new
assert "BytesPerBlock(PixelFormatFromRenderTargetFormat(regs.dst.format))" in fermi_layer_new
assert "if ((regs.src.layer != 0 || regs.dst.layer != 0) && !pitch_layer_copy)" in fermi_layer_new
assert "EDEN_GPU_FERMI2D_UNSUPPORTED_LAYER" in fermi_layer_new
assert "if (count < 8)" in fermi_layer_new
assert fermi_layer_new.count("AssertFailSoftImpl();") == 1
assert fermi_layer_new.index("AssertFailSoftImpl();") < fermi_layer_new.index("return;")
assert fermi_new.count("AssertFailSoftImpl();") == 1
assert fermi_new.index("AssertFailSoftImpl();") < fermi_new.index("return;")
assert "const u64 plane_bytes = static_cast<u64>(surface.pitch) * surface.height;" in fermi_copy_new
assert "const u64 offset = plane_bytes * surface.layer;" in fermi_copy_new
assert "offset / surface.layer != plane_bytes" in fermi_copy_new
assert "offset > last - surface.Address()" in fermi_copy_new
assert "surface.layer = 0;" in fermi_copy_new
assert "if (!select_pitch_layer(src) || !select_pitch_layer(dst))" in fermi_copy_new
assert "EDEN_GPU_FERMI2D_PITCH_LAYER_INVALID" in fermi_copy_new
# Independent arithmetic model of the linear image-layer address.
def pitch_layer_address(base: int, pitch: int, height: int, layer: int,
                        depth: int) -> int | None:
    max_u64 = (1 << 64) - 1
    if pitch <= 0 or height <= 0 or layer < 0 or layer >= depth:
        return None
    plane_bytes = pitch * height
    offset = plane_bytes * layer
    if offset > max_u64 or base > max_u64 - offset:
        return None
    return base + offset

assert pitch_layer_address(0x1000, 2048, 1080, 0, 4) == 0x1000
assert pitch_layer_address(0x1000, 2048, 1080, 2, 4) == 0x1000 + 2 * 2048 * 1080
assert pitch_layer_address(0x1000, 2048, 1080, 4, 4) is None
assert pitch_layer_address((1 << 64) - 2, 2048, 1080, 1, 2) is None
assert pitch_layer_address(0x1000, 0, 1080, 1, 2) is None

assert "return;" in fermi_copy_new
assert 'message(FATAL_ERROR "Pinned Fermi2D source/destination layer exception anchors changed")' in cmake
assert "src.depth = 1;" in fermi_copy_new
assert "Surface dst = regs.dst;" in fermi_copy_new
assert "dst.depth = 1;" in fermi_copy_new
assert "EDEN_GPU_FERMI2D_SOFTWARE" in fermi_copy_new
assert "sw_blitter->Blit(src, dst, config);" in fermi_copy_new
assert "else if (!rasterizer->AccelerateSurfaceCopy(src, regs.dst, config))" in fermi_copy_new
assert "regs.src.depth = 1;" not in fermi_copy_new
assert "regs.dst.depth = 1;" not in fermi_copy_new
assert "sw_source_depth_at LESS 0 OR sw_dest_depth_at LESS 0 OR" in cmake
assert "sw_pitch_arithmetic_at LESS 0 OR sw_src_copy_arithmetic_at LESS 0 OR" in cmake
assert "sw_dst_copy_arithmetic_at LESS 0 OR sw_z0_at LESS 0" in cmake
assert '"static_cast<size_t>(surface.pitch) * surface.height"' in cmake
assert '"const size_t src_copy_size = static_cast<size_t>(src_extent_x) * src_extent_y * src_bytes_per_pixel;"' in cmake
assert '"const size_t dst_copy_size = static_cast<size_t>(dst_extent_x) * dst_extent_y * dst_bytes_per_pixel;"' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/sw_blitter_sized.cpp"' in cmake
assert 'list(FILTER sw_blitter_sources EXCLUDE REGEX "engines/sw_blitter/blitter[.]cpp$")' in cmake
assert 'target_sources(video_core PRIVATE "${PORT_BUILD_DIR}/sw_blitter_sized.cpp")' in cmake

# Regressions that were once silent truncation in the pinned software blitter.
# The widened intermediate must match arbitrary-precision math for these cases.
def safe_product(*values):
    result = 1
    for value in values:
        result *= value
    return result
assert safe_product(65536, 65536) == 1 << 32  # pitch x height
assert safe_product(8192, 8192, 16) == 1 << 30  # source/destination rect
assert safe_product(65536, 65536, 4) == 1 << 34  # not 32-bit-wrapped
assert safe_product(65536, 65536, 4) != (safe_product(65536, 65536, 4) & 0xffffffff)


# Three generated translation units: Maxwell PRMT, widened software blitter,
# and Fermi2D. The extra blitter is intentional, not a duplicate generated
# file or a lost GPU compatibility path.
assert "file(READ" in cmake and cmake.count("write_derived(") == 3
for output in ("maxwell_prmt_observed.cpp", "sw_blitter_sized.cpp", "fermi_2d_observed.cpp"):
    assert 'write_derived("${PORT_BUILD_DIR}/' + output + '"' in cmake
assert 'target_sources(shader_recompiler PRIVATE' in cmake
assert 'target_sources(video_core PRIVATE' in cmake
print("GPU SOURCE CONTRACT: PRMT immediate/register Index implemented, Fermi2D z=0 plus pitch-linear layers; unsupported cases preserved")
print("NOTE graphics correctness and PS5 native CMake build remain to be qualified")
