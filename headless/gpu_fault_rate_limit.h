// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Count every invalid GPU access; format only the first eight and powers of two.
// Unmapped read-zero/write-discard semantics remain unchanged.
#include <atomic>
#include <cstdint>
namespace Eden::GpuFault {
inline std::atomic<std::uint64_t> reads{0}, writes{0};
inline std::atomic<std::uint64_t> guest_map_zero{0}, guest_null_mapped{0};
inline std::atomic<std::uint64_t> guest_alias_mapped{0}, guest_alias_access{0};
inline std::atomic<std::uint64_t> remap_replaced{0}, remap_mismatch{0};
inline std::atomic<std::uint64_t> bad_map_range{0}, bad_unmap_range{0};
inline std::atomic<std::uint64_t> bad_physical{0};
inline bool ShouldReport(std::atomic<std::uint64_t>& counter) noexcept {
    const std::uint64_t n = counter.fetch_add(1, std::memory_order_relaxed) + 1;
    return n <= 8 || (n & (n - 1)) == 0;
}
inline void ResetTitleCounters() noexcept {
    reads.store(0, std::memory_order_relaxed);
    writes.store(0, std::memory_order_relaxed);
    guest_map_zero.store(0, std::memory_order_relaxed);
    guest_null_mapped.store(0, std::memory_order_relaxed);
    guest_alias_mapped.store(0, std::memory_order_relaxed);
    guest_alias_access.store(0, std::memory_order_relaxed);
    remap_replaced.store(0, std::memory_order_relaxed);
    remap_mismatch.store(0, std::memory_order_relaxed);
    bad_map_range.store(0, std::memory_order_relaxed);
    bad_unmap_range.store(0, std::memory_order_relaxed);
    bad_physical.store(0, std::memory_order_relaxed);
}
inline bool ShouldReportRead() noexcept { return ShouldReport(reads); }
inline bool ShouldReportWrite() noexcept { return ShouldReport(writes); }
inline bool ShouldReportGuestMapZero() noexcept { return ShouldReport(guest_map_zero); }
inline bool ShouldReportGuestNullMapped() noexcept { return ShouldReport(guest_null_mapped); }
inline bool ShouldReportRemapMismatch() noexcept { return ShouldReport(remap_mismatch); }
inline bool ShouldReportBadMapRange() noexcept { return ShouldReport(bad_map_range); }
inline bool ShouldReportBadUnmapRange() noexcept { return ShouldReport(bad_unmap_range); }
inline bool ShouldReportBadPhysical() noexcept { return ShouldReport(bad_physical); }
}
