// SPDX-License-Identifier: GPL-3.0-or-later
#include "common/sparse_large_vector.h"
#include <cstdint>
#include <cstdlib>

namespace Common {
void* ReserveMemoryRange(std::size_t size) noexcept;
bool CommitMemoryRange(void* address, std::size_t size, std::int64_t* physical_out) noexcept;
void AbandonInitialHeapReservation(void* base, std::size_t reserved,
                                   std::int64_t first_physical, std::size_t committed) noexcept;
} // namespace Common

// Reuse the qualified, owned direct-memory backend for the C mspace heap.
extern "C" void* eden_heap_pages(std::size_t size) {
    return Common::AllocateMemoryPages(size);
}
extern "C" void eden_heap_pages_free(void* base, std::size_t size) {
    Common::FreeMemoryPages(base, size);
}
// The heap that grows (headless/heap_arenas.inc): address space first, memory piece by piece.
extern "C" void* eden_heap_reserve(std::size_t size) {
    return Common::ReserveMemoryRange(size);
}
// Written only during the one-thread startup state 1; after state 2, this
// record is immutable and is never consulted on the allocation hot path.
static void* first_committed_va;
static std::size_t first_committed_size;
static std::int64_t first_committed_pa = -1;
extern "C" int eden_heap_commit(void* address, std::size_t size) {
    std::int64_t physical = -1;
    if (!Common::CommitMemoryRange(address, size, &physical)) return -1;
    if (!first_committed_va) {
        first_committed_va = address;
        first_committed_size = size;
        first_committed_pa = physical;
    }
    return 0;
}
extern "C" void eden_heap_abandon_initial(void* base, std::size_t reserved) {
    // The initial mspace creation is the sole rollback caller. It must own
    // the first direct mapping, not an arbitrary later growth piece.
    if (first_committed_va != base || !first_committed_size) std::abort();
    Common::AbandonInitialHeapReservation(base, reserved, first_committed_pa, first_committed_size);
    first_committed_va = nullptr;
    first_committed_size = 0;
    first_committed_pa = -1;
}
