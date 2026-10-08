// SPDX-License-Identifier: GPL-3.0-or-later
// Low-overhead, developer-only evidence for suspected *in-game* GPU stalls.
// Sampling is from the existing one-second boot watchdog thread, not the
// guest/JIT/GPU hot path. Never kill or restart a guest based on these hints.
// Counter absence, pause screens and deliberate suspend can look alike.
#pragma once
#include <cstdint>

namespace Eden::GameLiveness {
struct Counters {
    std::uint64_t dispatches = 0;
    std::uint64_t draws = 0;
};
struct Result {
    bool suspected = false;
    std::uint64_t seconds_without_progress = 0;
    bool established_gpu_progress = false;
};
class Probe {
    Counters prior_{};
    std::uint64_t last_progress_second_ = 0;
    bool initialized_ = false;
    bool witnessed_gpu_progress_ = false;
    unsigned reports_ = 0;
public:
    void Reset() noexcept { *this = Probe{}; }
    Result Observe(Counters now, std::uint64_t second) noexcept {
        if (!initialized_) {
            prior_ = now;
            last_progress_second_ = second;
            initialized_ = true;
            return {};
        }
        if (second < last_progress_second_) {
            // Clock reset / impossible timestamp; never signal a freeze.
            last_progress_second_ = second;
            prior_ = now;
            witnessed_gpu_progress_ = false;
            return {};
        }
        if (prior_.dispatches != now.dispatches || prior_.draws != now.draws) {
            witnessed_gpu_progress_ = true;
            last_progress_second_ = second;
            prior_ = now;
        }
        Result result{};
        result.established_gpu_progress = witnessed_gpu_progress_;
        if (!witnessed_gpu_progress_) return result;
        result.seconds_without_progress = second - last_progress_second_;
        // Max FOUR reports over the entire guest session. A temporary
        // pause may resume; do not flood kernel/SD logs with repeated events.
        if (reports_ < 4 &&
            result.seconds_without_progress >= (std::uint64_t{reports_} + 1) * 30) {
            ++reports_;
            result.suspected = true;
        }
        return result;
    }
};
} // namespace Eden::GameLiveness
