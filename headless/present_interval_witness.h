// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <array>
#include <cstddef>

namespace Eden::FrameDiagnostics {

// Passive interval witness: all counters are cumulative worker totals sampled
// at two *presentation* callbacks, not work attributable to a single guest frame.
// No clocks, locks, dynamic allocation, I/O, or guest memory access here.
// Instantiate only in native development builds and call only when profiling.
template <std::size_t N>
struct PresentIntervalWitness {
    using Counts = std::array<unsigned long long, N>;
    Counts previous{};
    Counts peak_delta{};
    double peak_ms{};
    unsigned peak_frame{};
    bool seeded{};
    bool captured{};

    void Reset() noexcept {
        seeded = false;
        captured = false;
        peak_ms = 0.0;
        peak_frame = 0;
    }

    void Observe(const Counts& current, double interval_ms, unsigned frame) noexcept {
        if (seeded && interval_ms >= 100.0 && (!captured || interval_ms > peak_ms)) {
            Counts difference{};
            bool monotonic = true;
            for (std::size_t i = 0; i < N; ++i) {
                if (current[i] < previous[i]) {
                    monotonic = false;
                    break;
                }
                difference[i] = current[i] - previous[i];
            }
            if (monotonic) {
                peak_delta = difference;
                peak_ms = interval_ms;
                peak_frame = frame;
                captured = true;
            }
        }
        previous = current;
        seeded = true;
    }

    void NextWindow() noexcept {
        captured = false;
        peak_ms = 0.0;
        peak_frame = 0;
        // Keep the previous presentation baseline across 5-s reports.
    }
};

} // namespace Eden::FrameDiagnostics
