// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// R01: session-scoped, opt-in CPU-observed Vulkan frame accounting.
//
// These counters are NOT proof of physical scan-out, input-to-photon latency,
// game simulation speed, guest HIPC progress, or GPU timestamps. The guest
// VI clock is a requested cadence, not measured game FPS.
//
// Enabled only by existing detailed_logging, which itself disables normal
// low-overhead performance runs. No heap, time, syscalls or output in hot
// paths when disabled. Reset only after previous title renderer joins.
#include <atomic>
#include <cstdint>

namespace Eden::FrameMetrics {
inline std::atomic<bool> enabled{false};
inline std::atomic<std::uint64_t> source_composites{0};
inline std::atomic<std::uint64_t> real_frames_queued{0};
inline std::atomic<std::uint64_t> generated_frames_queued{0};
inline std::atomic<std::uint64_t> skipped_source_frames{0};
inline std::atomic<std::uint64_t> loading_frames_queued{0};
inline std::atomic<std::uint64_t> present_calls_returned{0};
inline std::atomic<std::uint64_t> last_report_ns{0};

struct Window {
    std::uint64_t interval_ns{};
    std::uint64_t source_composites{};
    std::uint64_t real_frames_queued{};
    std::uint64_t generated_frames_queued{};
    std::uint64_t skipped_source_frames{};
    std::uint64_t loading_frames_queued{};
    std::uint64_t present_calls_returned{};
    bool valid{};
};

// Main thread: call once per title only after the prior renderer has stopped.
// Never call while another title is drawing; no frame should be mixed across
// sessions. The detailed profile may be toggled between title sessions.
inline void ResetForTitle(bool opt_in, std::uint64_t mono_ns) noexcept {
    enabled.store(false, std::memory_order_release);
    source_composites.store(0, std::memory_order_relaxed);
    real_frames_queued.store(0, std::memory_order_relaxed);
    generated_frames_queued.store(0, std::memory_order_relaxed);
    skipped_source_frames.store(0, std::memory_order_relaxed);
    loading_frames_queued.store(0, std::memory_order_relaxed);
    present_calls_returned.store(0, std::memory_order_relaxed);
    last_report_ns.store(mono_ns, std::memory_order_relaxed);
    enabled.store(opt_in, std::memory_order_release);
}

inline bool Enabled() noexcept {
    return enabled.load(std::memory_order_relaxed);
}
inline void OnSourceComposite() noexcept {
    if (Enabled()) source_composites.fetch_add(1, std::memory_order_relaxed);
}
inline void OnRealQueued() noexcept {
    if (Enabled()) real_frames_queued.fetch_add(1, std::memory_order_relaxed);
}
inline void OnGeneratedQueued() noexcept {
    if (Enabled()) generated_frames_queued.fetch_add(1, std::memory_order_relaxed);
}
inline void OnSourceSkipped() noexcept {
    if (Enabled()) skipped_source_frames.fetch_add(1, std::memory_order_relaxed);
}
inline void OnLoadingQueued() noexcept {
    if (Enabled()) loading_frames_queued.fetch_add(1, std::memory_order_relaxed);
}
inline void OnSwapchainPresentReturned() noexcept {
    if (Enabled()) present_calls_returned.fetch_add(1, std::memory_order_relaxed);
}

// Called on the existing five-second GPU report path only, never per frame.
// The separate presenter may still be consuming its queue: values are
// approximate per-window CPU-observed rates, not frame-perfect matched pairs.
inline Window Sample(std::uint64_t mono_ns) noexcept {
    if (!Enabled()) return {};
    const auto before = last_report_ns.load(std::memory_order_relaxed);
    if (!before || mono_ns <= before) return {};
    last_report_ns.store(mono_ns, std::memory_order_relaxed);
    Window out{};
    out.valid = true;
    out.interval_ns = mono_ns - before;
    out.source_composites = source_composites.exchange(0, std::memory_order_relaxed);
    out.real_frames_queued = real_frames_queued.exchange(0, std::memory_order_relaxed);
    out.generated_frames_queued = generated_frames_queued.exchange(0, std::memory_order_relaxed);
    out.skipped_source_frames = skipped_source_frames.exchange(0, std::memory_order_relaxed);
    out.loading_frames_queued = loading_frames_queued.exchange(0, std::memory_order_relaxed);
    out.present_calls_returned = present_calls_returned.exchange(0, std::memory_order_relaxed);
    return out;
}
inline double Rate(std::uint64_t frames, std::uint64_t interval_ns) noexcept {
    return interval_ns ? static_cast<double>(frames) * 1'000'000'000.0 /
                             static_cast<double>(interval_ns) : 0.0;
}
} // namespace Eden::FrameMetrics
