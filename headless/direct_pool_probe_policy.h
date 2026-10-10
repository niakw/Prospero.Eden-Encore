// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>

namespace Eden::DirectPool {
// The PS5's free-direct-memory probe is synchronous on the GPU owner thread.
// Do not reduce monitoring while the pool is constrained, during startup,
// or after a failed query. Above 4 GiB contiguous *kernel-confirmed* free
// direct RAM, use a longer cadence to avoid unnecessary frame-path syscalls.
// This is a query policy, NOT proof that the OS reserved part of 16 GiB is free.
inline constexpr std::int64_t kProbeFastNs = 100'000'000;
inline constexpr std::int64_t kProbeHighHeadroomNs = 250'000'000;
inline constexpr std::uint64_t kProbeHighHeadroomBytes = 4ULL << 30;
constexpr std::int64_t ProbeIntervalNs(bool has_valid_sample,
                                       unsigned failed_queries,
                                       std::uint64_t largest_confirmed_free) noexcept {
    return has_valid_sample && failed_queries == 0 &&
                   largest_confirmed_free >= kProbeHighHeadroomBytes
               ? kProbeHighHeadroomNs : kProbeFastNs;
}
static_assert(ProbeIntervalNs(false, 0, 8ULL << 30) == kProbeFastNs);
static_assert(ProbeIntervalNs(true, 1, 8ULL << 30) == kProbeFastNs);
static_assert(ProbeIntervalNs(true, 0, 2ULL << 30) == kProbeFastNs);
static_assert(ProbeIntervalNs(true, 0, 4ULL << 30) == kProbeHighHeadroomNs);
} // namespace Eden::DirectPool
