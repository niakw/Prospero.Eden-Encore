// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
namespace Eden::GuestCodeCache {
// The Dynarmic block cache and the one-page fallback instruction snapshot
// must be invalidated together when an overlapping guest mapping changes.
// Subtraction avoids overflow near the top of the guest virtual address space.
constexpr bool TouchesCachedPage(std::uint64_t start, std::uint64_t length,
                                 std::uint64_t cached_page, std::uint64_t page_bytes) noexcept {
    if (!length || !page_bytes || cached_page == ~std::uint64_t{0})
        return false;
    if (start >= cached_page)
        return start - cached_page < page_bytes;
    return cached_page - start < length;
}
} // namespace Eden::GuestCodeCache
