# SPDX-License-Identifier: GPL-3.0-or-later
# Native-only pinned Eden shader/GPU compatibility. Maxwell PRMT immediate
# Index mode (0), including dynamic register selectors, translates the NVIDIA
# byte selector; other modes still throw.
# Fermi2D software handles 3D z=0 and explicitly pitched linear layers;
# other layered/block-linear cases retain unsupported soft asserts.
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

set(prmt_reg_old [=[
void TranslatorVisitor::PRMT_reg(u64) {
    ThrowNotImplemented(Opcode::PRMT_reg);
}
]=])
set(prmt_reg_new [=[
void TranslatorVisitor::PRMT_reg(u64 insn) {
    // Maxwell SASS PRMT register selector opcode (0x5bc0).
    // Dynamic selector is R[20:27]; A=R8, B=R39, mode[48:50].
    const unsigned mode = static_cast<unsigned>((insn >> 48) & 7ULL);
    if (mode != 0) {
        static std::atomic<unsigned> unsupported_samples{0};
        const unsigned sample = unsupported_samples.fetch_add(1, std::memory_order_relaxed);
        if (sample < 8)
            std::fprintf(stderr, "EDEN_GPU_PRMT_REG_UNSUPPORTED raw=%016llx mode=%u sample=%u\n",
                         static_cast<unsigned long long>(insn), mode, sample + 1);
        ThrowNotImplemented(Opcode::PRMT_reg);
    }

    const IR::U32 a{GetReg8(insn)};
    const IR::U32 b{GetReg39(insn)};
    const IR::U32 selector{GetReg20(insn)};
    IR::U32 result{ir.Imm32(0)};
    for (unsigned i = 0; i < 4; ++i) {
        const IR::U32 nibble{ir.BitwiseAnd(
            ir.ShiftRightLogical(selector, ir.Imm32(i * 4u)), ir.Imm32(15))};
        const IR::U1 from_b{ir.INotEqual(
            ir.BitwiseAnd(nibble, ir.Imm32(4)), ir.Imm32(0))};
        const IR::U32 source{ir.Select(from_b, b, a)};
        const IR::U32 byte_shift{ir.ShiftLeftLogical(
            ir.BitwiseAnd(nibble, ir.Imm32(3)), ir.Imm32(3))};
        const IR::U32 selected_byte{ir.BitwiseAnd(
            ir.ShiftRightLogical(source, byte_shift), ir.Imm32(255))};
        const IR::U1 signed_replication{ir.INotEqual(
            ir.BitwiseAnd(nibble, ir.Imm32(8)), ir.Imm32(0))};
        const IR::U1 negative{ir.INotEqual(
            ir.BitwiseAnd(selected_byte, ir.Imm32(128)), ir.Imm32(0))};
        const IR::U32 replicated{ir.Select(negative, ir.Imm32(255), ir.Imm32(0))};
        const IR::U32 byte{ir.Select(signed_replication, replicated, selected_byte)};
        const IR::U32 shifted{i == 0 ? byte :
            ir.ShiftLeftLogical(byte, ir.Imm32(i * 8u))};
        result = ir.BitwiseOr(result, shifted);
    }
    X(static_cast<IR::Reg>(insn & 255ULL), result);
    static std::atomic<unsigned> successes{0};
    const unsigned sample = successes.fetch_add(1, std::memory_order_relaxed);
    if (sample < 8)
        std::fprintf(stderr, "EDEN_GPU_PRMT_REG_INDEX raw=%016llx sample=%u\n",
                     static_cast<unsigned long long>(insn), sample + 1);
}
]=])
string(FIND "${prmt_source}" "${prmt_reg_old}" prmt_reg_at)
if(prmt_reg_at LESS 0)
    message(FATAL_ERROR "Pinned Maxwell PRMT_reg exception anchor changed")
endif()
string(REPLACE "${prmt_reg_old}" "${prmt_reg_new}" prmt_source "${prmt_source}")
# Embed executable-at-compile-time NVIDIA PRMT Index golden vectors
# into the pinned shader translation TU. This catches byte-order/sign nibble
# regressions on the next authorized native build (no runtime overhead).
set(prmt_reference [=[
namespace {
constexpr unsigned EdenPrmtIndexReference(unsigned a, unsigned b, unsigned selector) {
    unsigned result = 0;
    for (unsigned output = 0; output < 4; ++output) {
        const unsigned nibble = (selector >> (4u * output)) & 15u;
        const unsigned source = (nibble & 4u) ? b : a;
        unsigned byte = (source >> (8u * (nibble & 3u))) & 255u;
        if (nibble & 8u)
            byte = (byte & 128u) ? 255u : 0u;
        result |= byte << (8u * output);
    }
    return result;
}
static_assert(EdenPrmtIndexReference(0x11223344u, 0x55667788u, 0x3210u) == 0x11223344u);
static_assert(EdenPrmtIndexReference(0x11223344u, 0x55667788u, 0x7654u) == 0x55667788u);
static_assert(EdenPrmtIndexReference(0x80abcdefu, 0u, 0xbbbbu) == 0xffffffffu);
static_assert(EdenPrmtIndexReference(0x11223344u, 0x55667788u, 0xffffu) == 0u);
}
]=])
write_derived("${PORT_BUILD_DIR}/maxwell_prmt_observed.cpp"
    "#include <atomic>\n#include <cstdio>\n${prmt_reference}\n${prmt_source}")
get_target_property(shader_sources shader_recompiler SOURCES)
list(FILTER shader_sources EXCLUDE REGEX "frontend/maxwell/translate/impl/not_implemented[.]cpp$")
set_property(TARGET shader_recompiler PROPERTY SOURCES "${shader_sources}")
target_sources(shader_recompiler PRIVATE "${PORT_BUILD_DIR}/maxwell_prmt_observed.cpp")

set(fermi_relative "engines/fermi_2d.cpp")
file(READ "${PROJECT_SOURCE_DIR}/src/video_core/${fermi_relative}" fermi_source)
set(fermi_old [=[
    UNIMPLEMENTED_IF_MSG(regs.src.depth != 1, "Source depth is not one");
]=])
set(fermi_layer_old [=[
    UNIMPLEMENTED_IF_MSG(regs.src.layer != 0, "Source layer is not zero");
    UNIMPLEMENTED_IF_MSG(regs.dst.layer != 0, "Destination layer is not zero");
]=])
set(fermi_layer_new [=[
    // For pitch-linear images, one layer starts exactly pitch*height
    // bytes after the preceding one. Keep nonzero layers of block-linear
    // 3D images unsupported until origin_z has a verified implementation.
    const bool pitch_layer_copy =
        (regs.src.layer != 0 || regs.dst.layer != 0) &&
        regs.src.linear == MemoryLayout::Pitch &&
        regs.dst.linear == MemoryLayout::Pitch &&
        regs.src.layer < regs.src.depth && regs.dst.layer < regs.dst.depth &&
        regs.src.pitch != 0 && regs.dst.pitch != 0 &&
        regs.src.width != 0 && regs.src.height != 0 &&
        regs.dst.width != 0 && regs.dst.height != 0 &&
        regs.src.format == regs.dst.format &&
        static_cast<u64>(regs.src.pitch) >=
            static_cast<u64>(regs.src.width) *
                BytesPerBlock(PixelFormatFromRenderTargetFormat(regs.src.format)) &&
        static_cast<u64>(regs.dst.pitch) >=
            static_cast<u64>(regs.dst.width) *
                BytesPerBlock(PixelFormatFromRenderTargetFormat(regs.dst.format)) &&
        regs.operation == Operation::SrcCopy && regs.clip_enable == 0;
    UNIMPLEMENTED_IF_MSG(regs.src.layer != 0 && !pitch_layer_copy,
                         "Source layer is not zero");
    UNIMPLEMENTED_IF_MSG(regs.dst.layer != 0 && !pitch_layer_copy,
                         "Destination layer is not zero");
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
    if (regs.src.depth != 1 && !base_layer_3d_copy && !pitch_layer_copy) {
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
string(FIND "${fermi_source}" "${fermi_layer_old}" fermi_layer_at)
if(fermi_layer_at LESS 0)
    message(FATAL_ERROR "Pinned Fermi2D source/destination layer exception anchors changed")
endif()
string(REPLACE "${fermi_layer_old}" "${fermi_layer_new}" fermi_source "${fermi_source}")

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
    if (base_layer_3d_copy || pitch_layer_copy) {
        // 3D z=0 uses the original block-depth swizzle. Nonzero layers
        // are supported ONLY in pitch-linear images, with explicit
        // overflow-checked pitch*height*layer addressing. Both routes
        // use the software decoder and avoid unknown GPU acceleration.
        Surface dst = regs.dst;
        if (pitch_layer_copy) {
            const auto select_pitch_layer = [](Surface& surface) {
                const u64 plane_bytes = static_cast<u64>(surface.pitch) * surface.height;
                const u64 last = ~static_cast<u64>(0);
                const u64 offset = plane_bytes * surface.layer;
                if (plane_bytes == 0 || surface.layer >= surface.depth ||
                    (surface.layer != 0 && offset / surface.layer != plane_bytes) ||
                    offset > last - surface.Address()) {
                    return false;
                }
                const u64 address = surface.Address() + offset;
                surface.addr_upper = static_cast<u32>(address >> 32);
                surface.addr_lower = static_cast<u32>(address);
                surface.layer = 0;
                return true;
            };
            if (!select_pitch_layer(src) || !select_pitch_layer(dst)) {
                LOG_CRITICAL(Debug, "EDEN_GPU_FERMI2D_PITCH_LAYER_INVALID");
                AssertFailSoftImpl();
                return;
            }
        }
        // Temporary descriptors only: guest originals are untouched.
        // depth=1 means one subrectangle is copied; block_depth remains
        // unchanged for the block-linear z=0 path.
        src.depth = 1;
        dst.depth = 1;
        static std::atomic<unsigned> software_reports{0};
        const unsigned report = software_reports.fetch_add(1, std::memory_order_relaxed);
        if (report < 8) {
            LOG_INFO(HW_GPU,
                "EDEN_GPU_FERMI2D_SOFTWARE mode={} src_depth={} dst_depth={} "
                "src_layer={} dst_layer={} src_addr={:#x} dst_addr={:#x} sample={}",
                pitch_layer_copy ? "pitch_layer" : "z0", regs.src.depth, regs.dst.depth,
                regs.src.layer, regs.dst.layer, src.Address(), dst.Address(), report + 1);
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
