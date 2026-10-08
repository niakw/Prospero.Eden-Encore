# SPDX-License-Identifier: GPL-3.0-or-later
# Native-only pinned Eden shader/GPU compatibility. Maxwell PRMT immediate
# Index mode (0) translates the NVIDIA byte selector; other modes still throw.
# The Fermi2D software swizzler handles only z=0 on depth>1 surfaces; other
# layers retain their original unsupported soft-assert semantics.
# Successful and unsupported cases produce bounded diagnostics.
if(NOT PS5_NATIVE)
    return()
endif()

set(prmt_relative "frontend/maxwell/translate/impl/not_implemented.cpp")
file(READ "${PROJECT_SOURCE_DIR}/src/shader_recompiler/${prmt_relative}" prmt_source)
set(prmt_old [=[
void TranslatorVisitor::PRMT_imm(u64) {
    ThrowNotImplemented(Opcode::PRMT_imm);
}
]=])
set(prmt_new [=[
void TranslatorVisitor::PRMT_imm(u64 insn) {
    // Maxwell SASS PRMT immediate (0x36c0) uses:
    // A = R[8:15], B = R[39:46], selector = bits[20:35],
    // mode = bits[48:50], D = R[0:7].
    // Only mode 0 (index byte permutation) is translated here.
    // Each nibble selects one of eight source bytes and its high bit
    // requests *sign replication* of that byte, not its raw value.
    const unsigned mode = static_cast<unsigned>((insn >> 48) & 7ULL);
    if (mode != 0) {
        static std::atomic<unsigned> unsupported_samples{0};
        const unsigned index = unsupported_samples.fetch_add(1, std::memory_order_relaxed);
        if (index < 8)
            std::fprintf(stderr, "EDEN_GPU_PRMT_IMM raw=%016llx mode=%u sample=%u\n",
                         static_cast<unsigned long long>(insn), mode, index + 1);
        ThrowNotImplemented(Opcode::PRMT_imm);
    }

    const unsigned selector = static_cast<unsigned>((insn >> 20) & 0xffffULL);
    const IR::U32 a{GetReg8(insn)};
    const IR::U32 b{GetReg39(insn)};
    IR::U32 result{ir.Imm32(0)};
    for (unsigned output_byte = 0; output_byte < 4; ++output_byte) {
        const unsigned nibble = (selector >> (output_byte * 4)) & 15u;
        const IR::U32 source = (nibble & 4u) ? b : a;
        const unsigned src_offset = (nibble & 3u) * 8u;
        // When nibble[3] is set, the NVIDIA byte sign bit
        // becomes either 0x00 or 0xff in the output.
        const IR::U32 extracted = (nibble & 8u)
            ? ir.BitFieldExtract(source, ir.Imm32(src_offset + 7u), ir.Imm32(1), true)
            : ir.BitFieldExtract(source, ir.Imm32(src_offset), ir.Imm32(8), false);
        const IR::U32 value = ir.BitwiseAnd(extracted, ir.Imm32(255));
        const IR::U32 shifted = output_byte == 0 ? value :
            ir.ShiftLeftLogical(value, ir.Imm32(output_byte * 8u));
        result = ir.BitwiseOr(result, shifted);
    }
    X(static_cast<IR::Reg>(insn & 255ULL), result);

    static std::atomic<unsigned> implemented_samples{0};
    const unsigned implemented = implemented_samples.fetch_add(1, std::memory_order_relaxed);
    if (implemented < 8)
        std::fprintf(stderr, "EDEN_GPU_PRMT_IMM_INDEX raw=%016llx selector=%04x sample=%u\n",
                     static_cast<unsigned long long>(insn), selector, implemented + 1);
}
]=])
string(FIND "${prmt_source}" "${prmt_old}" prmt_at)
if(prmt_at LESS 0)
    message(FATAL_ERROR "Pinned Maxwell PRMT_imm exception anchor changed")
endif()
string(REPLACE "${prmt_old}" "${prmt_new}" prmt_source "${prmt_source}")
write_derived("${PORT_BUILD_DIR}/maxwell_prmt_observed.cpp"
    "#include <atomic>\n#include <cstdio>\n${prmt_source}")
get_target_property(shader_sources shader_recompiler SOURCES)
list(FILTER shader_sources EXCLUDE REGEX "frontend/maxwell/translate/impl/not_implemented[.]cpp$")
set_property(TARGET shader_recompiler PROPERTY SOURCES "${shader_sources}")
target_sources(shader_recompiler PRIVATE "${PORT_BUILD_DIR}/maxwell_prmt_observed.cpp")

set(fermi_relative "engines/fermi_2d.cpp")
file(READ "${PROJECT_SOURCE_DIR}/src/video_core/${fermi_relative}" fermi_source)
set(fermi_old [=[
    UNIMPLEMENTED_IF_MSG(regs.src.depth != 1, "Source depth is not one");
]=])
set(fermi_new [=[
    // The software swizzler already handles the z=0 subrectangle of
    // a 3D block-linear/pitch image, provided the source/destination
    // layers are both zero. Keep nonzero layers explicitly unsupported:
    // the current UnswizzleSubrect API hardcodes origin_z = 0.
    const bool base_layer_3d_copy = regs.src.depth > 1 &&
        regs.src.layer == 0 && regs.dst.layer == 0 &&
        regs.dst.depth >= 1 && regs.operation == Operation::SrcCopy &&
        regs.clip_enable == 0;
    if (regs.src.depth != 1 && !base_layer_3d_copy) {
        static std::atomic<unsigned> depth_reports{0};
        const unsigned count = depth_reports.fetch_add(1, std::memory_order_relaxed);
        // Previously this logged the same generic warning for every
        // Fermi2D blit. Do not normalize depth to one: the texture-cache
        // source currently cannot represent arbitrary 3D slices.
        if (count < 8) {
            LOG_CRITICAL(Debug,
                "EDEN_GPU_FERMI2D_UNSUPPORTED src_depth={} dst_depth={} src_layer={} dst_layer={} "
                "src_block_depth={} dst_block_depth={} src_addr={:#x} dst_addr={:#x} sample={}",
                regs.src.depth, regs.dst.depth, regs.src.layer, regs.dst.layer,
                regs.src.block_depth, regs.dst.block_depth, regs.src.Address(),
                regs.dst.Address(), count + 1);
        }
        // Preserve UNIMPLEMENTED_IF_MSG soft-assert / debug-break semantics
        // even after the diagnostic log's bounded eight samples.
        AssertFailSoftImpl();
    }
]=])
string(FIND "${fermi_source}" "${fermi_old}" fermi_at)
if(fermi_at LESS 0)
    message(FATAL_ERROR "Pinned Fermi2D source-depth exception anchor changed")
endif()
string(REPLACE "${fermi_old}" "${fermi_new}" fermi_source "${fermi_source}")

# The pinned software blitter must really honor 3D block-depth layout and
# read only the z=0 rectangle. Refuse this compatibility implementation if
# upstream changes those semantics; never silently copy the wrong slice.
file(READ "${PROJECT_SOURCE_DIR}/src/video_core/engines/sw_blitter/blitter.cpp" sw_blit_source)
file(READ "${PROJECT_SOURCE_DIR}/src/video_core/textures/decoders.cpp" swizzle_source)
string(FIND "${sw_blit_source}" "src.depth, config.src_x0" sw_source_depth_at)
string(FIND "${sw_blit_source}" "dst.depth, config.dst_x0" sw_dest_depth_at)
string(FIND "${swizzle_source}" "static constexpr u32 origin_z = 0;" sw_z0_at)
if(sw_source_depth_at LESS 0 OR sw_dest_depth_at LESS 0 OR sw_z0_at LESS 0)
    message(FATAL_ERROR "Pinned Fermi2D software base-layer copy contract changed")
endif()

set(fermi_copy_old [=[
    if (!rasterizer->AccelerateSurfaceCopy(src, regs.dst, config)) {
        sw_blitter->Blit(src, regs.dst, config);
    }
]=])
set(fermi_copy_new [=[
    if (base_layer_3d_copy) {
        // GPU acceleration is not proven for 3D source copies. Software
        // decoders handle z=0 using the original block_depth for address
        // swizzling. Expose depth=1 only to the temporary software
        // surface descriptors to avoid loading all untouched 3D slices.
        src.depth = 1;
        Surface dst = regs.dst;
        dst.depth = 1;
        static std::atomic<unsigned> z0_reports{0};
        const unsigned report = z0_reports.fetch_add(1, std::memory_order_relaxed);
        if (report < 8) {
            LOG_INFO(HW_GPU,
                "EDEN_GPU_FERMI2D_Z0_SOFTWARE src_depth={} dst_depth={} "
                "src_addr={:#x} dst_addr={:#x} sample={}",
                regs.src.depth, regs.dst.depth, regs.src.Address(),
                regs.dst.Address(), report + 1);
        }
        sw_blitter->Blit(src, dst, config);
    } else if (!rasterizer->AccelerateSurfaceCopy(src, regs.dst, config)) {
        sw_blitter->Blit(src, regs.dst, config);
    }
]=])
string(FIND "${fermi_source}" "${fermi_copy_old}" fermi_copy_at)
if(fermi_copy_at LESS 0)
    message(FATAL_ERROR "Pinned Fermi2D copy-acceleration anchor changed")
endif()
string(REPLACE "${fermi_copy_old}" "${fermi_copy_new}" fermi_source "${fermi_source}")

write_derived("${PORT_BUILD_DIR}/fermi_2d_observed.cpp"
    "#include <atomic>\n${fermi_source}")
get_target_property(video_sources video_core SOURCES)
list(FILTER video_sources EXCLUDE REGEX "engines/fermi_2d[.]cpp$")
set_property(TARGET video_core PROPERTY SOURCES "${video_sources}")
target_sources(video_core PRIVATE "${PORT_BUILD_DIR}/fermi_2d_observed.cpp")
