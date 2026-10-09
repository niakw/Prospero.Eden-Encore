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
} // namespace Eden::Jit
