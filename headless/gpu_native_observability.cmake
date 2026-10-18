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

# After the first eight diagnostics, stop dirtying a shared atomic cache
# line for every PRMT translation or unsupported Fermi copy. Preserve the
# eight real samples, but never let the telemetry counter wrap or grow
# without bound in long shader-heavy game sessions.
set(gpu_bounded_sample_helper [=[
namespace {
unsigned EdenGpuBoundedSample(std::atomic<unsigned>& samples) noexcept {
    unsigned current = samples.load(std::memory_order_relaxed);
    while (current < 8u) {
        if (samples.compare_exchange_weak(current, current + 1u,
                                          std::memory_order_relaxed))
            return current;
    }
    return 8u;
}
}
]=])

# Native Maxwell PRMT mode-0 translation is a complete tracked source.
# Diagnostic sample helper remains temporarily for the separate Fermi2D
# generator below; never regenerate this shader unit in CMake.
set(EDEN_MAINTAINED_NATIVE_PRMT
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/shader_recompiler/frontend/maxwell/translate/impl/not_implemented.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_PRMT}")
    message(FATAL_ERROR "Missing maintained PRMT shader source")
endif()
get_target_property(shader_sources shader_recompiler SOURCES)
list(FILTER shader_sources EXCLUDE REGEX "frontend/maxwell/translate/impl/not_implemented[.]cpp$")
set_property(TARGET shader_recompiler PROPERTY SOURCES "${shader_sources}")
target_sources(shader_recompiler PRIVATE "${EDEN_MAINTAINED_NATIVE_PRMT}")

set(fermi_relative "engines/fermi_2d.cpp")
file(READ "${PROJECT_SOURCE_DIR}/src/video_core/${fermi_relative}" fermi_source)
option(EDEN_UNQUALIFIED_FERMI2D_COPY "3D software blit experiments" OFF)
if(EDEN_UNQUALIFIED_FERMI2D_COPY)
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
    if ((regs.src.layer != 0 || regs.dst.layer != 0) && !pitch_layer_copy) {
        static std::atomic<unsigned> unsupported_layer_reports{0};
        const unsigned count = EdenGpuBoundedSample(unsupported_layer_reports);
        if (count < 8)
            LOG_CRITICAL(Debug,
                "EDEN_GPU_FERMI2D_UNSUPPORTED_LAYER src_layer={} dst_layer={} "
                "src_depth={} dst_depth={} src_linear={} dst_linear={} sample={}",
                regs.src.layer, regs.dst.layer, regs.src.depth, regs.dst.depth,
                static_cast<unsigned>(regs.src.linear), static_cast<unsigned>(regs.dst.linear),
                count + 1);
        AssertFailSoftImpl();
        return; // unsupported layers must not silently copy the wrong slice
    }
]=])
set(fermi_new [=[
    // The software swizzler already handles the z=0 subrectangle when
    // EITHER the source OR destination has 3D depth, provided both
    // layers are zero. Keep nonzero layers explicitly unsupported:
    // the current UnswizzleSubrect API hardcodes origin_z = 0.
    const bool base_layer_3d_copy =
        (regs.src.depth > 1 || regs.dst.depth > 1) &&
        regs.src.depth >= 1 && regs.dst.depth >= 1 &&
        regs.src.layer == 0 && regs.dst.layer == 0 &&
        regs.operation == Operation::SrcCopy && regs.clip_enable == 0;
    if (regs.src.depth != 1 && !base_layer_3d_copy && !pitch_layer_copy) {
        static std::atomic<unsigned> depth_reports{0};
        const unsigned count = EdenGpuBoundedSample(depth_reports);
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
        return; // unsupported depth is not a valid copy operation
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
endif()

# The pinned software blitter must really honor 3D block-depth layout and
# read only the z=0 rectangle. Refuse this compatibility implementation if
# upstream changes those semantics; never silently copy the wrong slice.
# Blitter arithmetic is maintained as one complete source, derived from
# the SHIPPING backport (not from the older pristine Eden baseline).
# Keep the native-only module gate and the exact target replacement.
set(EDEN_MAINTAINED_NATIVE_BLITTER
    "${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/engines/sw_blitter/blitter.cpp")
if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_BLITTER}")
    message(FATAL_ERROR "Missing maintained native software blitter")
endif()
get_target_property(sw_blitter_sources video_core SOURCES)
list(FILTER sw_blitter_sources EXCLUDE REGEX "engines/sw_blitter/blitter[.]cpp$")
set_property(TARGET video_core PROPERTY SOURCES "${sw_blitter_sources}")
target_sources(video_core PRIVATE "${EDEN_MAINTAINED_NATIVE_BLITTER}")

if(EDEN_UNQUALIFIED_FERMI2D_COPY)
set(fermi_copy_old [=[
    if (!rasterizer->AccelerateSurfaceCopy(src, regs.dst, config)) {
        sw_blitter->Blit(src, regs.dst, config);
    }
]=])
set(fermi_copy_new [=[
    if (base_layer_3d_copy || pitch_layer_copy) {
        // These new software-only paths must not turn negative or
        // out-of-bounds subrectangles into oversized unsigned copies.
        // The existing general Fermi copy path is unchanged.
        const u64 src_bpp = BytesPerBlock(
            PixelFormatFromRenderTargetFormat(src.format));
        const u64 dst_bpp = BytesPerBlock(
            PixelFormatFromRenderTargetFormat(regs.dst.format));
        // The pinned blitter evaluates pitch*height and x_extent*y_extent
        // in u32 before promotion to size_t. Never feed it operands that
        // overflow those intermediate products, nor zero-byte formats.
        const auto safe_plane = [](const Surface& surface) {
            return surface.linear != MemoryLayout::Pitch ||
                (surface.pitch != 0 && surface.height != 0 &&
                 static_cast<u64>(surface.pitch) * surface.height <= 0xffffffffULL);
        };
        const bool copy_storage_valid =
            src_bpp != 0 && dst_bpp != 0 &&
            safe_plane(src) && safe_plane(regs.dst);
        const bool rect_valid =
            config.src_x0 >= 0 && config.src_y0 >= 0 &&
            config.dst_x0 >= 0 && config.dst_y0 >= 0 &&
            config.src_x1 > config.src_x0 && config.src_y1 > config.src_y0 &&
            config.dst_x1 > config.dst_x0 && config.dst_y1 > config.dst_y0 &&
            static_cast<u64>(config.src_x1) <= src.width &&
            static_cast<u64>(config.src_y1) <= src.height &&
            static_cast<u64>(config.dst_x1) <= regs.dst.width &&
            static_cast<u64>(config.dst_y1) <= regs.dst.height;
        // Multiply-free 32-bit allocation boundary: (width * height * bpp)
        // may itself overflow u64 for malicious guest surface dimensions.
        // The pinned sw_blitter allocates exactly this many decoded bytes.
        const auto valid_byte_count = [](s32 x0, s32 x1, s32 y0, s32 y1, u64 bpp) {
            if (x0 < 0 || y0 < 0 || x1 <= x0 || y1 <= y0 ||
                bpp == 0 || bpp > 0xffffffffULL)
                return false;
            const u64 width = static_cast<u64>(x1) - static_cast<u64>(x0);
            const u64 height = static_cast<u64>(y1) - static_cast<u64>(y0);
            const u64 max = 0xffffffffULL;
            return width <= max / bpp &&
                height <= max / (width * bpp);
        };
        const bool copy_sizes_valid = rect_valid && copy_storage_valid &&
            valid_byte_count(config.src_x0, config.src_x1,
                             config.src_y0, config.src_y1, src_bpp) &&
            valid_byte_count(config.dst_x0, config.dst_x1,
                             config.dst_y0, config.dst_y1, dst_bpp);
        if (!copy_sizes_valid) {
            static std::atomic<unsigned> rect_reports{0};
            const unsigned count = EdenGpuBoundedSample(rect_reports);
            if (count < 8)
                LOG_CRITICAL(Debug,
                    "EDEN_GPU_FERMI2D_SOFTWARE_BOUNDS_INVALID src={}..{},{}..{} "
                    "dst={}..{},{}..{} sample={}",
                    config.src_x0, config.src_x1, config.src_y0, config.src_y1,
                    config.dst_x0, config.dst_x1, config.dst_y0, config.dst_y1,
                    count + 1);
            AssertFailSoftImpl();
            return;
        }
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
        const unsigned report = EdenGpuBoundedSample(software_reports);
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
endif()

write_derived("${PORT_BUILD_DIR}/fermi_2d_observed.cpp"
    "#include <atomic>\n${gpu_bounded_sample_helper}\n${fermi_source}")
get_target_property(video_sources video_core SOURCES)
list(FILTER video_sources EXCLUDE REGEX "engines/fermi_2d[.]cpp$")
set_property(TARGET video_core PROPERTY SOURCES "${video_sources}")
target_sources(video_core PRIVATE "${PORT_BUILD_DIR}/fermi_2d_observed.cpp")
