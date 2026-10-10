// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>

namespace Eden::DirectPool {
// Conservative lower bound on occupied kernel direct-memory intervals.
// The kernel may stop enumeration before the end of the extent. Validated
// records remain a LOWER bound of occupied memory; total-taken is only
// an UPPER bound on free memory, NEVER allocatable or a JIT/GPU budget.
struct RegionScan {
    std::int64_t extent;
    std::int64_t cursor{0};
    std::int64_t taken_lower{0};
    unsigned regions{0};
    bool valid{true};

    constexpr bool Include(std::int64_t start, std::int64_t end) noexcept {
        if (!valid || extent <= 0 || start < 0 || start < cursor ||
            end <= start || end > extent) {
            valid = false;
            return false;
        }
        const std::int64_t span = end - start;
        if (taken_lower > extent - span) {
            valid = false;
            return false;
        }
        taken_lower += span;
        cursor = end;
        ++regions;
        return true;
    }
    constexpr std::int64_t FreeUpperBound() const noexcept {
        return valid && extent > 0 ? extent - taken_lower : -1;
    }
    // Only an ordered walk that actually reaches the end of the address
    // extent can be called end-reached; kernel query failure/EOF before
    // this point must be logged separately (it is NOT a 'scan complete').
    constexpr bool ReachedExtent() const noexcept {
        return valid && extent > 0 && cursor == extent;
    }
};
constexpr auto kScanFixture = [] {
    RegionScan scan{12288LL << 20};
    return scan.Include(128LL << 20, 256LL << 20) &&
           scan.Include(512LL << 20, 640LL << 20) &&
           scan.regions == 2 && scan.FreeUpperBound() == (12032LL << 20) &&
           !scan.ReachedExtent();
}();
static_assert(kScanFixture);
} // namespace Eden::DirectPool
