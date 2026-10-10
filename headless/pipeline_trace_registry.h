// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Debug-only Vulkan first-use attribution; never touched when pipeline
// tracing is disabled. Shader workers may build/use pipelines concurrently.
// The former function-static unordered_set was mutated without a mutex,
// which is undefined behavior on the multithreaded PS5 shader pool.
#include <cstddef>
#include <cstdint>
#include <limits>
#include <mutex>
#include <unordered_set>

namespace Eden::PipelineTrace {

class FirstUseRegistry final {
public:
    // A game can compile tens of thousands of unique pipelines. Put a firm
    // bound on long-lived diagnostic allocations and the number of log lines.
    static constexpr std::size_t kMaxPipelinesPerTitle = 65536;

    // Return ordinal for a newly observed pointer, 0 for duplicates/overflow.
    // Only the set mutation happens under the lock: caller formats and logs
    // OUTSIDE it, preventing kernel I/O from blocking other shader workers.
    std::size_t Record(std::uint64_t title_epoch, const void* pipeline) {
        if (!pipeline) return 0;
        const std::lock_guard lock(mutex_);
        if (epoch_ != title_epoch) {
            seen_.clear();
            epoch_ = title_epoch;
        }
        if (seen_.size() >= kMaxPipelinesPerTitle)
            return 0;
        const auto [_, inserted] = seen_.insert(pipeline);
        return inserted ? seen_.size() : 0;
    }

    std::size_t CountForTest() {
        const std::lock_guard lock(mutex_);
        return seen_.size();
    }

private:
    std::mutex mutex_;
    std::unordered_set<const void*> seen_;
    std::uint64_t epoch_ = std::numeric_limits<std::uint64_t>::max();
};

// Separate graphics/compute IDs and unique lists. The atomically bumped
// gpu_time_session epoch is shared with the existing per-title Vulkan device
// lifetime and is advanced only after old game workers have joined.
inline FirstUseRegistry graphics_first_use;
inline FirstUseRegistry compute_first_use;

} // namespace Eden::PipelineTrace
