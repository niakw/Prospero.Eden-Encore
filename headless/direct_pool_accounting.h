// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <limits>

namespace Eden::DirectPool {

// These are DISJOINT physical backing owners tracked by Encore, NOT all GPU
// and guest allocations in the Sony direct-memory pool. A 3-GiB reserved
// VIRTUAL heap range is not physical usage; only committed mspace roots count.
// The kernel's directly addressable extent is authoritative, not the PS5's
// 16-GiB installed GDDR6 capacity.
struct Owners {
    std::uint64_t heap_roots{};
    std::uint64_t heap_large{};
    std::uint64_t sparse_tables{};
    std::uint64_t jit_sparse{};
    std::uint64_t jit_dense{};
};
struct Account {
    std::uint64_t extent_bytes{};
    std::uint64_t tracked_bytes{};
    std::uint64_t not_tracked_bytes{};
    bool extent_known{};
    bool within_extent{};
};
constexpr std::uint64_t SaturatingAdd(std::uint64_t left, std::uint64_t right) noexcept {
    return right > std::numeric_limits<std::uint64_t>::max() - left
        ? std::numeric_limits<std::uint64_t>::max() : left + right;
}
constexpr Account Summarize(std::int64_t kernel_direct_extent, Owners owners) noexcept {
    const auto used = SaturatingAdd(
        SaturatingAdd(
            SaturatingAdd(
                SaturatingAdd(owners.heap_roots, owners.heap_large),
                owners.sparse_tables),
            owners.jit_sparse),
        owners.jit_dense);
    if (kernel_direct_extent <= 0)
        return {0, used, 0, false, false};
    const auto extent = static_cast<std::uint64_t>(kernel_direct_extent);
    if (used > extent)
        // Counter snapshots may overlap an in-flight teardown. Do NOT
        // interpret an inconsistent total as a valid memory budget.
        return {extent, used, 0, true, false};
    // Not a free-memory measurement: this remainder also contains GPU/
    // guest allocations outside Encore's tracked owners and possible
    // other native process reservations.
    return {extent, used, extent - used, true, true};
}
static_assert(Summarize(12288LL << 20, {.heap_roots = 1280ULL << 20}).tracked_bytes
              == (1280ULL << 20));
static_assert(Summarize(12288LL << 20, {.heap_roots = 1280ULL << 20}).not_tracked_bytes
              == (11008ULL << 20));
static_assert(!Summarize(-1, {}).extent_known);
static_assert(!Summarize(1024, {.heap_roots = 1025}).within_extent);

} // namespace Eden::DirectPool
