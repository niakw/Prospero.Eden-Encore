// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Physical commitment is a reservation hint, not a new virtual code write.
// Xbyak retains responsibility for checking actual code emission bounds.
#include <algorithm>
#include <cstddef>

namespace Eden::Jit {
struct SparseCommitTarget {
    bool valid;
    bool clamped;
    std::size_t bytes;
};

constexpr SparseCommitTarget PlanSparseCommit(std::size_t written,
                                              std::size_t requested,
                                              std::size_t capacity) noexcept {
    if (written > capacity)
        return {false, false, 0};
    const std::size_t remaining = capacity - written;
    // Dynarmic's 16 MiB PRELUDE_COMMIT_SIZE is a physical precommit hint.
    // Core 3's virtual arena is also 16 MiB. After its 2 MiB constant pool,
    // requiring written + full hint fails despite all actual code fitting.
    // Commit only the address range that exists. Xbyak rejects later writes
    // beyond the allocated arena independently.
    const std::size_t additional = std::min(requested, remaining);
    return {true, requested > remaining, written + additional};
}

// Return only complete, unneeded 2 MiB direct-memory chunks after a FULL
// halted JIT clear. Keep the executable prelude, two bootstrap chunks and
// one chunk of recompilation headroom. Never move the RX/RW virtual aliases.
// This is a DEV-only policy; the caller must prove no old code is executing.
struct SparseTrimTarget {
    bool valid;
    std::size_t keep;
    std::size_t release;
};

constexpr SparseTrimTarget PlanSparseTrim(std::size_t live_code_end,
                                           std::size_t committed,
                                           std::size_t capacity,
                                           std::size_t chunk) noexcept {
    if (chunk == 0 || (chunk & (chunk - 1)) != 0 ||
        capacity % chunk || committed % chunk ||
        committed > capacity || live_code_end > committed)
        return {false, 0, 0};
    const std::size_t headroom = std::min(chunk, capacity - live_code_end);
    const std::size_t bootstrap = capacity / chunk >= 2 ? 2 * chunk : capacity;
    const std::size_t needed = std::max(live_code_end + headroom, bootstrap);
    // capacity is already chunk-aligned, so alignment cannot exceed it.
    const std::size_t padding = (chunk - needed % chunk) % chunk;
    const std::size_t keep = std::min(committed, needed + padding);
    return {true, keep, committed - keep};
}

static_assert(PlanSparseTrim(3u << 20, 128u << 20, 256u << 20, 2u << 20).keep == (6u << 20));
static_assert(PlanSparseTrim(3u << 20, 128u << 20, 256u << 20, 2u << 20).release == (122u << 20));
static_assert(PlanSparseTrim(15u << 20, 16u << 20, 16u << 20, 2u << 20).release == 0);
static_assert(!PlanSparseTrim(17u << 20, 16u << 20, 16u << 20, 2u << 20).valid);

} // namespace Eden::Jit
