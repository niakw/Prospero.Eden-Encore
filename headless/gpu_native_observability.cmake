# SPDX-License-Identifier: GPL-3.0-or-later
# Native-only pinned Eden shader/GPU diagnostics. Missing Maxwell PRMT and
# multi-layer Fermi2D copies must remain UNIMPLEMENTED: never manufacture
# incorrect pixels or quietly ignore the error. Capture at most eight real
# instruction/register sets per process for a hardware-grounded repair.
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
    static std::atomic<unsigned> samples{0};
    const unsigned index = samples.fetch_add(1, std::memory_order_relaxed);
    if (index < 8)
        std::fprintf(stderr, "EDEN_GPU_PRMT_IMM raw=%016llx sample=%u\n",
                     static_cast<unsigned long long>(insn), index + 1);
    // Do NOT pretend the NVIDIA Maxwell permutation was implemented.
    ThrowNotImplemented(Opcode::PRMT_imm);
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
    if (regs.src.depth != 1) {
        static std::atomic<unsigned> depth_reports{0};
        const unsigned count = depth_reports.fetch_add(1, std::memory_order_relaxed);
        // Previously this logged the same generic warning for every
        // Fermi2D blit. Do not normalize depth to one: the texture-cache
        // source currently cannot represent arbitrary 3D slices.
        if (count < 8) {
            LOG_WARNING(HW_GPU,
                "EDEN_GPU_FERMI2D_UNSUPPORTED src_depth={} dst_depth={} src_layer={} dst_layer={} "
                "src_block_depth={} dst_block_depth={} src_addr={:#x} dst_addr={:#x} sample={}",
                regs.src.depth, regs.dst.depth, regs.src.layer, regs.dst.layer,
                regs.src.block_depth, regs.dst.block_depth, regs.src.Address(),
                regs.dst.Address(), count + 1);
        }
    }
]=])
string(FIND "${fermi_source}" "${fermi_old}" fermi_at)
if(fermi_at LESS 0)
    message(FATAL_ERROR "Pinned Fermi2D source-depth exception anchor changed")
endif()
string(REPLACE "${fermi_old}" "${fermi_new}" fermi_source "${fermi_source}")
write_derived("${PORT_BUILD_DIR}/fermi_2d_observed.cpp"
    "#include <atomic>\n${fermi_source}")
get_target_property(video_sources video_core SOURCES)
list(FILTER video_sources EXCLUDE REGEX "engines/fermi_2d[.]cpp$")
set_property(TARGET video_core PROPERTY SOURCES "${video_sources}")
target_sources(video_core PRIVATE "${PORT_BUILD_DIR}/fermi_2d_observed.cpp")
