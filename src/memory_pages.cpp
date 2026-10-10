// SPDX-License-Identifier: GPL-3.0-or-later
#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <mutex>
#include <new>
#include <unordered_map>
#include <utility>
#include <vector>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#ifdef PS5_NATIVE
// Keep CPU heaps/tables and JIT views out of RADV's high-word-2 GPU window.
// This is a non-fixed hint: the kernel retains ownership of collision handling.
constexpr std::uintptr_t cpu_mapping_hint = 0x1000000000ull;
static bool cpu_mapping_address(void* base) {
    return reinterpret_cast<std::uintptr_t>(base) >= 0x300000000ull && base != MAP_FAILED;
}
// A reserved range must also end below the driver's device memory at 0x40_0000_0000.
static bool cpu_mapping_range(void* base, std::size_t size) {
    const auto start = reinterpret_cast<std::uintptr_t>(base);
    return cpu_mapping_address(base) && size <= 0x4000000000ull && start <= 0x4000000000ull - size;
}
extern "C" {
std::int64_t sceKernelGetDirectMemorySize();
std::int32_t sceKernelAllocateDirectMemory(std::int64_t, std::int64_t, std::size_t,
                                         std::size_t, int, std::int64_t*);
std::int32_t sceKernelMapDirectMemory(void**, std::size_t, int, int, std::int64_t, std::size_t);
std::int32_t sceKernelReleaseDirectMemory(std::int64_t, std::size_t);
std::int32_t sceKernelReserveVirtualRange(void**, std::size_t, int, std::size_t);
std::int32_t sceKernelEnableDmemAliasing();
int sceKernelDebugOutText(int, const char*);
}
#endif

#ifdef PS5_NATIVE
namespace {
// This is the fixed addressable direct-memory EXTENT, not available RAM.
// Demand-backed sparse JIT previously asked the kernel for it for EVERY
// newly committed 2 MiB page; CPU heap and zero-table allocations did too.
// Cache only a positive successful answer, so transient early errors retry.
std::atomic<std::int64_t> cached_direct_memory_extent{0};
std::int64_t DirectMemoryExtent() noexcept {
    const auto cached = cached_direct_memory_extent.load(std::memory_order_acquire);
    if (cached > 0) return cached;
    const auto current = sceKernelGetDirectMemorySize();
    if (current > 0)
        cached_direct_memory_extent.store(current, std::memory_order_release);
    return current > 0 ? current : 0;
}
std::int32_t AllocateDirectOwned(std::size_t bytes, std::size_t align,
                                  std::int64_t* physical) noexcept {
    const auto extent = DirectMemoryExtent();
    // No allocator can recover by passing a negative/zero extent to Sony.
    return extent > 0 ? sceKernelAllocateDirectMemory(0, extent, bytes, align, 12, physical) : -1;
}
// One ownership contract for sparse JIT, sparse page tables and growing
// native heap reservations. Refuse any mapping outside the full CPU window.
// A failed syscall that mutated the output VA might still own a reservation;
// do not silently lose track of it and proceed to reserve another region.
void* ReserveCpuVirtualRange(std::size_t bytes, std::size_t alignment) noexcept {
    if (!bytes || !alignment) return nullptr;
    void* address = reinterpret_cast<void*>(cpu_mapping_hint);
    const auto rc = sceKernelReserveVirtualRange(&address, bytes, 0, alignment);
    if (rc != 0) {
        if (address != reinterpret_cast<void*>(cpu_mapping_hint)) std::abort();
        return nullptr;
    }
    if (!cpu_mapping_range(address, bytes)) {
        if (!address || address == MAP_FAILED || munmap(address, bytes) != 0)
            std::abort();
        return nullptr;
    }
    return address;
}
} // namespace
#endif

namespace Common {
namespace {
// The header sits in the page before the data. Blocks of at least LargePage start their data
// one LargePage in, with the address and direct memory LargePage-aligned, so the kernel can map
// them with 2 MiB pages: the guest backing, JIT caches and page tables are walked on every
// guest memory access, and 16 KiB pages cover only a few MiB of TLB reach.
struct Header { std::int64_t physical; std::size_t total; std::size_t lead; };
constexpr std::size_t LargePage = 0x200000;
// Development A/B: dev-settings large_pages=off keeps every block 16 KiB-aligned. The heap takes
// its blocks before the frontend parses the file, so read it here with plain system calls.
bool DevSetting(const char* entry) {
    char text[4096];
    const int fd = open("/app0/dev-settings.txt", O_RDONLY);
    if (fd < 0) return false;
    const auto count = read(fd, text, sizeof(text) - 1);
    close(fd);
    text[count > 0 ? count : 0] = '\0';
    return std::strstr(text, entry) != nullptr;
}
// A line for the log from inside the allocator: no stdio (it may allocate). On the console the
// app's stderr is a stream of the C library and not descriptor 2, so the line goes to the kernel
// log.
void Note(const char* line) noexcept {
#ifdef PS5_NATIVE
    sceKernelDebugOutText(0, line);
#else
    (void)!write(2, line, std::strlen(line));
#endif
}
// The same for a line written outside the allocator: on the console it is in the app's log too.
void Report(const char* line) noexcept {
    Note(line);
#ifdef PS5_NATIVE
    std::fputs(line, stderr);
#endif
}
bool LargePagesEnabled() {
    static std::atomic<int> state{0}; // 0 unknown, 1 on, 2 off
    int value = state.load(std::memory_order_acquire);
    if (value == 0) {
        value = DevSetting("large_pages=off") ? 2 : 1;
        state.store(value, std::memory_order_release);
    }
    return value == 1;
}
std::size_t lead_size(std::size_t size, std::size_t page) {
    return size >= LargePage && LargePagesEnabled() ? LargePage : page;
}
std::size_t allocation_size(std::size_t size, std::size_t page, std::size_t lead) {
    if (!size || page < sizeof(Header) || size > std::numeric_limits<std::size_t>::max() - 2 * lead)
        return 0;
    return (size + lead - 1) / lead * lead + lead;
}
const Header& header_of(const void* pointer, std::size_t page) {
    return *reinterpret_cast<const Header*>(static_cast<const std::uint8_t*>(pointer) - page);
}
}

// PS5 direct memory is real memory from the first byte: there is no page the system fills in
// when it is first touched. A block from here is dense and zeroed. What must not be dense (the
// guest page tables, the heap) uses the two families below.
void* AllocateMemoryPages(std::size_t size) noexcept {
    const long page = sysconf(_SC_PAGESIZE);
    const std::size_t lead = page > 0 ? lead_size(size, static_cast<std::size_t>(page)) : 0;
    const auto total = page > 0 ? allocation_size(size, page, lead) : 0;
    if (!total) { errno = EINVAL; return nullptr; }
    void* base = nullptr;
    std::int64_t physical = -1;
#ifdef PS5_NATIVE
    base = reinterpret_cast<void*>(cpu_mapping_hint);
    const auto limit = DirectMemoryExtent();
    auto rc = limit > 0 ? sceKernelAllocateDirectMemory(0, limit, total, lead, 12, &physical) : -1;
    if (rc != 0) {
        std::fprintf(stderr, "Direct allocation failed: rc=%08x bytes=%zu limit=%lld\n",
                     unsigned(rc), total, static_cast<long long>(limit));
        errno = ENOMEM;
        return nullptr;
    }
    rc = sceKernelMapDirectMemory(&base, total, PROT_READ | PROT_WRITE, 0, physical, lead);
    // Reject a kernel-chosen CPU mapping whose START is legal but whose
    // final page crosses into RADV's protected high VA/device-memory window.
    if (rc != 0 || !cpu_mapping_range(base, total)) {
        std::fprintf(stderr, "Direct mapping failed: rc=%08x bytes=%zu\n", unsigned(rc), total);
        // A failed non-fixed mapping must not change its output pointer:
        // the kernel may have created an alias before returning an error.
        // Ownership is then ambiguous; returning physical RAM is unsafe.
        if (rc != 0 && base != reinterpret_cast<void*>(cpu_mapping_hint))
            std::abort();
        if (rc == 0 && base && base != MAP_FAILED && munmap(base, total) != 0) std::abort();
        if (sceKernelReleaseDirectMemory(physical, total) != 0) std::abort();
        errno = ENOMEM;
        return nullptr;
    }
    if (lead == LargePage) {
        // The heap allocates through here: no stdio (it may allocate).
        char line[96];
        const int length = std::snprintf(line, sizeof(line), "EDEN_LARGE_ALLOC bytes=%zu va=%p pa=%llx\n",
                                         total, base, static_cast<unsigned long long>(physical));
        if (length > 0) Note(line);
    }
    std::memset(base, 0, total);
#else
    base = mmap(nullptr, total, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (base == MAP_FAILED) return nullptr;
#endif
    auto* data = static_cast<std::uint8_t*>(base) + lead;
    new (data - page) Header{physical, total, lead};
    return data;
}

// Exact direct allocation span including metadata and large-page rounding.
// The caller's payload size is not a physical ownership measurement.
std::size_t AllocatedMemoryPagesSpan(const void* pointer) noexcept {
    if (!pointer) return 0;
    const long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) std::abort();
    return header_of(pointer, static_cast<std::size_t>(page)).total;
}

#ifdef PS5_NATIVE
// Direct-memory start of an AllocateMemoryPages block's first data byte.
std::int64_t DirectMemoryStart(const void* pointer) noexcept {
    const long page = sysconf(_SC_PAGESIZE);
    if (!pointer || page <= 0) std::abort();
    const auto& header = header_of(pointer, page);
    return header.physical + static_cast<std::int64_t>(header.lead);
}

// Report *physical direct bytes*, including allocator alignment/header slack,
// for actual dense Dynarmic regions. Increments happen only on JIT
// construction/destruction, never per emulated frame.
static std::atomic<std::size_t> dense_jit_direct_bytes{0};
void CountDenseJitDirect(void* writable, bool acquire) noexcept {
    if (!writable) return;
    const long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) std::abort();
    const std::size_t bytes = header_of(writable, page).total;
    if (acquire) {
        dense_jit_direct_bytes.fetch_add(bytes, std::memory_order_relaxed);
    } else {
        const std::size_t old = dense_jit_direct_bytes.fetch_sub(bytes, std::memory_order_relaxed);
        if (old < bytes) std::abort();
    }
}
std::size_t DenseJitDirectBytes() noexcept {
    return dense_jit_direct_bytes.load(std::memory_order_relaxed);
}

// Return the actual RX virtual-mapping length, not just Xbyak's requested
// size: large-page direct allocations can round, for example, 3 MiB to 4 MiB.
// Free must unmap the WHOLE executable view before releasing direct RAM.
std::size_t ExecutableAliasSpan(void* writable) noexcept {
    const long page = sysconf(_SC_PAGESIZE);
    if (!writable || page <= 0) std::abort();
    const auto header = header_of(writable, page);
    return header.total - header.lead;
}

// A second view of our own direct allocation; ownership stays with pointer.
void* MapExecutableAlias(void* pointer, std::size_t size) noexcept {
    const long page = sysconf(_SC_PAGESIZE);
    if (!pointer || page <= 0) return nullptr;
    const auto header = header_of(pointer, page);
    if (header.total != allocation_size(size, page, header.lead)) std::abort();
    // This wrapper reports zero unconditionally; the mapping is the actual check.
    static const auto enabled = sceKernelEnableDmemAliasing();
    (void)enabled;
    const auto span = header.total - header.lead;
    void* alias = reinterpret_cast<void*>(cpu_mapping_hint);
    const auto rc = sceKernelMapDirectMemory(&alias, span, PROT_READ, 0,
                                              header.physical + static_cast<std::int64_t>(header.lead),
                                              header.lead);
    // The RX alias must fit entirely inside the host CPU VA window;
    // validating only its first byte could admit a cross-window mapping.
    if (rc != 0 || !cpu_mapping_range(alias, span)) {
        std::printf("EDEN_JIT_ALIAS_MAP rc=%08x bytes=%zu\n", unsigned(rc), span);
        // If a non-fixed syscall returned an error but changed its output
        // address, we cannot prove whether it retained a mapping. The owner
        // must not release physical backing through the allocator fallback.
        if (rc != 0 && alias != reinterpret_cast<void*>(cpu_mapping_hint))
            std::abort();
        if (rc == 0 && alias && alias != MAP_FAILED && munmap(alias, span) != 0) std::abort();
        errno = rc ? unsigned(rc) & 0xffff : ENOMEM;
        return nullptr;
    }
    // Direct mapping wrappers reject EXEC on some versions. Use the same
    // checked mprotect contract already qualified for this owned memory type.
    if (mprotect(alias, span, PROT_READ | PROT_EXEC) != 0) {
        const auto error = errno;
        if (munmap(alias, span) != 0) std::abort();
        errno = error;
        return nullptr;
    }
    return alias;
}
#endif

#ifdef PS5_NATIVE
namespace {
// Unlike AllocateMemoryPages, the JIT stores code in two stable, separately
// reserved virtual views. Their *physical* backing is committed in 2 MiB
// chunks, once, before the compiler writes or executes that chunk.
struct SparseJitRegion {
    void* writable = nullptr;
    std::size_t capacity = 0;
    std::size_t committed = 0;
    std::vector<std::int64_t> physical;
};
std::mutex sparse_jit_mutex;
std::unordered_map<void*, SparseJitRegion> sparse_jit_regions;
std::size_t sparse_jit_committed = 0;
// The GPU frame reporter MUST NOT take sparse_jit_mutex while Dynarmic
// commits 2 MiB code chunks. Keep cheap snapshots atomically alongside the
// owner-locked exact counters. Both are updated only after ownership changes.
std::atomic<std::size_t> sparse_jit_reserved_live{0};
std::atomic<std::size_t> sparse_jit_committed_live{0};
// JIT executable aliases are immutable during an active title. The epoch
// invalidates per-thread "already committed" hints whenever a region is
// created or released, preventing an old pointer/VA from being mistaken for
// a new code cache in a subsequent title.
std::atomic<std::uint64_t> sparse_jit_generation{1};
}

// Validate the firmware's fixed-address alias contract *before* selecting
// sparse JIT for a guest. This uses a disposable 2 MiB mapping, performs no
// execution, and never modifies an active JIT. Failure keeps the dense path.
bool ProbeSparseJitAlias() noexcept {
    void* writable = reinterpret_cast<void*>(cpu_mapping_hint);
    void* executable = reinterpret_cast<void*>(cpu_mapping_hint);
    bool rw_reserved = false, rx_reserved = false, direct_owned = false;
    // MAP_FIXED should never return another address. If it does, retain
    // that successful mapping's ownership until it has been unmapped, rather
    // than releasing its physical backing with an orphaned virtual alias.
    void* unexpected_rw = nullptr;
    void* unexpected_rx = nullptr;
    std::int64_t physical = -1;
    bool success = false;
    do {
        (void)sceKernelEnableDmemAliasing();
        writable = ReserveCpuVirtualRange(LargePage, LargePage);
        if (!writable) break;
        rw_reserved = true;
        executable = ReserveCpuVirtualRange(LargePage, LargePage);
        if (!executable) break;
        rx_reserved = true;
        if (executable == writable) std::abort();
        if (AllocateDirectOwned(LargePage, LargePage, &physical) != 0)
            break;
        direct_owned = true;
        void* actual_rw = writable;
        void* actual_rx = executable;
        const auto rw_rc = sceKernelMapDirectMemory(&actual_rw, LargePage,
                                                     PROT_READ | PROT_WRITE,
                                                     MAP_FIXED, physical, LargePage);
        if (actual_rw != writable) {
            // A failed syscall with a mutated output has unknowable mapping
            // ownership. Also reject aliases over our other reserved view.
            if (rw_rc != 0 || !actual_rw || actual_rw == MAP_FAILED ||
                actual_rw == executable) std::abort();
            unexpected_rw = actual_rw;
            break;
        }
        if (rw_rc != 0) break;
        const auto rx_rc = sceKernelMapDirectMemory(&actual_rx, LargePage,
                                                    PROT_READ, MAP_FIXED,
                                                    physical, LargePage);
        if (actual_rx != executable) {
            if (rx_rc != 0 || !actual_rx || actual_rx == MAP_FAILED ||
                actual_rx == writable) std::abort();
            unexpected_rx = actual_rx;
            break;
        }
        if (rx_rc != 0 || mprotect(executable, LargePage, PROT_READ | PROT_EXEC) != 0)
            break;
        auto* rw = static_cast<volatile std::uint8_t*>(writable);
        auto* rx = static_cast<volatile std::uint8_t*>(executable);
        rw[0] = 0xa5;
        rw[LargePage - 1] = 0x5a;
        std::atomic_thread_fence(std::memory_order_seq_cst);
        success = rx[0] == 0xa5 && rx[LargePage - 1] == 0x5a;
    } while (false);

    // Release unexpected successful fixed-map aliases FIRST, then both
    // reserved views and their direct backing. Never leave a live foreign VA
    // referencing physical memory handed back to the kernel.
    if (unexpected_rx && munmap(unexpected_rx, LargePage) != 0) std::abort();
    if (unexpected_rw && munmap(unexpected_rw, LargePage) != 0) std::abort();
    // Release the disposable virtual mappings before returning their physical
    // backing to the system. A failed cleanup is not recoverable ownership.
    if (rx_reserved && executable != writable &&
        munmap(executable, LargePage) != 0)
        std::abort();
    if (rw_reserved && munmap(writable, LargePage) != 0)
        std::abort();
    if (direct_owned && sceKernelReleaseDirectMemory(physical, LargePage) != 0)
        std::abort();

    std::printf("EDEN_JIT_SPARSE_PROBE available=%u alias_rw_rx=%u\n",
                unsigned(success), unsigned(rx_reserved && rw_reserved));
    return success;
}

// Forward declarations: reservation bootstrap may release its own ownership.
void ReleaseSparseJitCode(void* executable) noexcept;

// The console has unified memory, so report separately the space promised
// to the JIT and the physical direct pages it actually holds. Only snapshots
// call this, never the frame or code-emission hot paths.
void SparseJitUsage(std::size_t* virtual_bytes, std::size_t* committed_bytes) noexcept {
    if (!virtual_bytes || !committed_bytes) return;
    const std::lock_guard lock{sparse_jit_mutex};
    std::size_t reserved = 0;
    for (const auto& [_, region] : sparse_jit_regions) {
        reserved += region.capacity;
    }
    *virtual_bytes = reserved;
    *committed_bytes = sparse_jit_committed;
}

// No mutex, no physical query, no allocator traversal: safe for the five-second
// native graphics frame reporter. Values may span an in-progress reservation
// update, so use lifecycle SparseJitUsage() for exact stopped-title receipts.
void SparseJitUsageFast(std::size_t* virtual_bytes, std::size_t* committed_bytes) noexcept {
    if (!virtual_bytes || !committed_bytes) return;
    *virtual_bytes = sparse_jit_reserved_live.load(std::memory_order_relaxed);
    *committed_bytes = sparse_jit_committed_live.load(std::memory_order_relaxed);
}

// The upstream ConstantPool constructor writes ~2 MiB (plus alignment) before
// BlockOfCode's constructor body calls EnsureMemoryCommitted. Provision 4 MiB
// before returning RX/RW pointers; later code commits stay demand-driven.
bool CommitSparseJitCode(void* executable, std::size_t required) noexcept;

// Reserve two VA ranges, but no direct memory. The RX base never changes,
// so Dynarmic's generated PC-relative branches and published pointers survive
// incremental commits. This differs from AllocateMemoryPages's dense path.
void* ReserveSparseJitCode(std::size_t size, void** writable_out) noexcept {
    if (!writable_out || !size || size % LargePage || !cpu_mapping_range(
            reinterpret_cast<void*>(cpu_mapping_hint), size)) {
        errno = EINVAL;
        return nullptr;
    }
    *writable_out = nullptr;
    void* rw = ReserveCpuVirtualRange(size, LargePage);
    if (!rw) return nullptr;
    void* rx = ReserveCpuVirtualRange(size, LargePage);
    if (!rx) {
        if (munmap(rw, size) != 0) std::abort();
        return nullptr;
    }
    if (rx == rw) std::abort(); // Kernel returned overlapping reservations.
    try {
        SparseJitRegion region;
        region.writable = rw;
        region.capacity = size;
        region.physical.reserve(size / LargePage);
        const std::lock_guard lock{sparse_jit_mutex};
        if (!sparse_jit_regions.emplace(rx, std::move(region)).second)
            std::abort();
        sparse_jit_reserved_live.fetch_add(size, std::memory_order_relaxed);
        sparse_jit_generation.fetch_add(1, std::memory_order_acq_rel);
    } catch (...) {
        if (munmap(rx, size) != 0 || munmap(rw, size) != 0) std::abort();
        errno = ENOMEM;
        return nullptr;
    }
    // This firmware wrapper reports zero even if it is unsupported; actual
    // per-chunk MapDirectMemory/mprotect calls below are the qualification.
    (void)sceKernelEnableDmemAliasing();
    // The 2 MiB constant pool writes during member construction, so simply
    // reserving zero-backed virtual addresses would immediately fault.
    // If even the required first 4 MiB are unavailable, drop the reservation.
    // In explicitly selected sparse mode the allocator MUST NOT silently
    // fall back to a full physically committed dense JIT: its caller retries
    // a smaller stable virtual arena, or fails startup without overcommitting.
    const std::size_t bootstrap = std::min<std::size_t>(size, 2 * LargePage);
    if (!CommitSparseJitCode(rx, bootstrap)) {
        ReleaseSparseJitCode(rx);
        errno = ENOMEM;
        return nullptr;
    }
    *writable_out = rw;
    std::printf("EDEN_JIT_SPARSE_RESERVE rx=%p rw=%p capacity=%zu bootstrap=%zu\n",
                rx, rw, size, bootstrap);
    return rx;
}

// Sparse reservation may fail when virtual address space is fragmented.
// If Xbyak fell back to a dense alias, never try to commit into that mapping.
bool IsSparseJitCode(const void* executable) noexcept {
    const std::lock_guard lock{sparse_jit_mutex};
    return sparse_jit_regions.find(const_cast<void*>(executable)) != sparse_jit_regions.end();
}

// Called only by BlockOfCode::EnsureMemoryCommitted before emission.
// Never commit at an asynchronous page fault in executing JIT code.
bool CommitSparseJitCode(void* executable, std::size_t required) noexcept {
    // Dynarmic calls EnsureMemoryCommitted on EVERY compiled guest block,
    // but a physical 2 MiB direct-memory page is committed only occasionally.
    // Avoid 3 guest JIT workers contending on one global mutex for pages
    // already known to be committed by this same worker. Cache only positive
    // answers, qualified by reservation epoch; a larger required span takes
    // the original locked ownership+allocation path.
    struct CachedCommit {
        void* executable{};
        std::size_t committed{};
        std::uint64_t generation{};
    };
    static thread_local CachedCommit local;
    const std::uint64_t generation = sparse_jit_generation.load(std::memory_order_acquire);
    if (local.generation == generation && local.executable == executable &&
        required <= local.committed)
        return true;
    const std::lock_guard lock{sparse_jit_mutex};
    const auto it = sparse_jit_regions.find(executable);
    if (it == sparse_jit_regions.end() || required > it->second.capacity) return false;
    auto& region = it->second;
    const std::size_t target = (required + LargePage - 1) / LargePage * LargePage;
    while (region.committed < target) {
        std::int64_t physical = -1;
        if (AllocateDirectOwned(LargePage, LargePage, &physical) != 0) {
            std::fprintf(stderr, "EDEN_JIT_SPARSE_OOM capacity=%zu committed=%zu required=%zu\n",
                         region.capacity, region.committed, required);
            return false;
        }
        auto* rw = static_cast<std::uint8_t*>(region.writable) + region.committed;
        auto* rx = static_cast<std::uint8_t*>(executable) + region.committed;
        void* actual_rw = rw;
        void* actual_rx = rx;
        // The fixed RX/RW views are stable for already-published guest code.
        // A kernel mapping can fail after the RW view has succeeded; do not
        // abort the whole game while the new (unpublished) page is recoverable.
        // Restore *only this new page* to inaccessible guards in BOTH views,
        // release its physical backing and leave committed bytes unchanged.
        // If the firmware cannot restore the fixed reservation, fail closed:
        // reusing a partially mapped code page could execute stale data.
        const auto restore_guard = [](void* address) noexcept {
            void* restored = mmap(address, LargePage, PROT_NONE,
                                  MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (restored != address) std::abort();
        };
        const auto rollback = [&](const char* stage, int error) noexcept {
            std::fprintf(stderr,
                         "EDEN_JIT_SPARSE_MAP_FAILED stage=%s committed=%zu errno=%d rollback=guard\n",
                         stage, region.committed, error);
            restore_guard(rx);
            restore_guard(rw);
            if (sceKernelReleaseDirectMemory(physical, LargePage) != 0)
                std::abort();
            errno = error ? error : ENOMEM;
            return false;
        };
        const auto rw_rc = sceKernelMapDirectMemory(&actual_rw, LargePage,
                                                    PROT_READ | PROT_WRITE,
                                                    MAP_FIXED, physical, LargePage);
        if (actual_rw != rw) std::abort(); // Unexpected mapping address: ownership unknown.
        if (rw_rc != 0) return rollback("rw", ENOMEM);
        std::memset(rw, 0, LargePage);
        const auto rx_rc = sceKernelMapDirectMemory(&actual_rx, LargePage,
                                                    PROT_READ, MAP_FIXED,
                                                    physical, LargePage);
        if (actual_rx != rx) std::abort();
        if (rx_rc != 0) return rollback("rx", ENOMEM);
        if (mprotect(rx, LargePage, PROT_READ | PROT_EXEC) != 0)
            return rollback("rx_exec", errno);
        region.physical.push_back(physical); // capacity reserved at region creation
        region.committed += LargePage;
        sparse_jit_committed += LargePage;
        sparse_jit_committed_live.fetch_add(LargePage, std::memory_order_relaxed);
    }
    // The page protection/mapping writes above happen before publishing a
    // positive hint. No unvalidated amount is ever returned from fastpath.
    local.executable = executable;
    local.committed = region.committed;
    local.generation = sparse_jit_generation.load(std::memory_order_relaxed);
    return true;
}

// The VA reservation and every physical chunk have one owner. Do not release
// partial chunks on ClearCache: the region may contain still-executing code.
void ReleaseSparseJitCode(void* executable) noexcept {
    SparseJitRegion region;
    std::size_t remaining = 0;
    {
        const std::lock_guard lock{sparse_jit_mutex};
        const auto it = sparse_jit_regions.find(executable);
        if (it == sparse_jit_regions.end()) std::abort();
        region = std::move(it->second);
        sparse_jit_committed -= region.committed;
        sparse_jit_committed_live.fetch_sub(region.committed, std::memory_order_relaxed);
        sparse_jit_reserved_live.fetch_sub(region.capacity, std::memory_order_relaxed);
        remaining = sparse_jit_committed;
        // Guest workers must already be quiescent before BlockOfCode releases
        // its executable view; invalidate all per-thread positive hints now.
        sparse_jit_generation.fetch_add(1, std::memory_order_acq_rel);
        sparse_jit_regions.erase(it);
    }
    if (munmap(executable, region.capacity) != 0 ||
        munmap(region.writable, region.capacity) != 0) std::abort();
    for (const auto physical : region.physical)
        if (sceKernelReleaseDirectMemory(physical, LargePage) != 0) std::abort();
    std::printf("EDEN_JIT_SPARSE_RELEASE capacity=%zu committed=%zu remaining=%zu\n",
                region.capacity, region.committed, remaining);
}
#endif

void FreeMemoryPages(void* pointer, std::size_t size) noexcept {
    if (!pointer) return;
    const long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) std::abort();
    const auto header = header_of(pointer, page);
    auto* base = static_cast<std::uint8_t*>(pointer) - header.lead;
    if (header.total != allocation_size(size, page, header.lead) || munmap(base, header.total) != 0) std::abort();
#ifdef PS5_NATIVE
    if (sceKernelReleaseDirectMemory(header.physical, header.total) != 0) std::abort();
#endif
}
// Xbyak's allocator interface supplies only the pointer at release. The owned
// header already records the exact mapped size; retain the same checked free.
void FreeMemoryPages(void* pointer) noexcept {
    if (!pointer) return;
    const long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) std::abort();
    const auto header = header_of(pointer, page);
    if (header.total <= header.lead) std::abort();
    FreeMemoryPages(pointer, header.total - header.lead);
}

// ---- Sparse pages: Eden's large tables ----
//
// Eden indexes its guest page table (and the GPU's address tables) directly: 8 bytes for every
// 4 KiB of a 512 GiB address space is a 1 GiB table, of which a game writes a few MiB. On a PC
// that costs nothing: the table is mapped read-only, the system shows one shared page of zeroes
// wherever nothing was written, and SparseLargeVector makes a page writable before its first
// write. The PS5 has no such page, so the same thing is built from mappings:
//
//   - the table's address range is reserved;
//   - every 2 MiB slot of it shows one shared block of zeroes, read-only (the JIT reads the
//     table for any address a game touches, mapped or not);
//   - CommitSparsePage, called before a first write, gives the slot a zeroed block of its own.
//
// A session's page table then takes 2 MiB per GiB of address space the game maps, not 1 GiB.
// The Linux build mirrors it (read-only until committed), so the host checks fail on a write
// that was not announced, as the console would.
namespace {
constexpr std::size_t SparseSlot = LargePage;
struct SparseRange {
    std::atomic<std::uintptr_t> begin{0}; // 0: free
    std::uintptr_t end = 0;
    std::atomic<bool>* owned = nullptr; // per slot: it has a block of its own
    std::int64_t* physical = nullptr;   // that block (PS5)
};
std::array<SparseRange, 64> sparse_ranges;
std::mutex sparse_mutex;
std::atomic<std::size_t> sparse_reserved{0}, sparse_committed{0};
std::atomic<int> sparse_state{0}; // 0 unknown, 1 in use, 2 not available (tables are dense)

SparseRange* SparseRangeOf(std::uintptr_t address) {
    for (auto& range : sparse_ranges) {
        const auto begin = range.begin.load(std::memory_order_acquire);
        if (begin != 0 && address >= begin && address < range.end) return &range;
    }
    return nullptr;
}

#ifdef PS5_NATIVE
std::int64_t zero_block = -1;

// A 2 MiB block of direct memory, zeroed through a mapping of its own that is gone again.
bool ZeroedBlock(std::int64_t* physical) {
    if (AllocateDirectOwned(SparseSlot, SparseSlot, physical) != 0)
        return false;
    void* view = reinterpret_cast<void*>(cpu_mapping_hint);
    const auto rc = sceKernelMapDirectMemory(&view, SparseSlot, PROT_READ | PROT_WRITE,
                                             0, *physical, SparseSlot);
    if (rc != 0 || !cpu_mapping_range(view, SparseSlot)) {
        // Never release backing while a successful but out-of-range alias
        // still maps it. The zero page has no published readers yet.
        // An error with a changed output VA has unknown alias ownership.
        if (rc != 0 && view != reinterpret_cast<void*>(cpu_mapping_hint))
            std::abort();
        if (rc == 0 && view && view != MAP_FAILED &&
            munmap(view, SparseSlot) != 0) std::abort();
        if (sceKernelReleaseDirectMemory(*physical, SparseSlot) != 0) std::abort();
        return false;
    }
    std::memset(view, 0, SparseSlot);
    if (munmap(view, SparseSlot) != 0) std::abort();
    return true;
}
bool MapSlot(std::uintptr_t at, int protection, std::int64_t physical) {
    void* address = reinterpret_cast<void*>(at);
    const auto rc = sceKernelMapDirectMemory(&address, SparseSlot, protection,
                                             MAP_FIXED, physical, SparseSlot);
    if (address != reinterpret_cast<void*>(at)) {
        // A surprising successful MAP_FIXED response owns a FOREIGN alias.
        // It is unsafe to drop the physical page while this alias remains
        // mapped. Unlike the ordinary fixed-address failure (same pointer),
        // a mutated output on error has unknown ownership: fail closed.
        if (rc != 0 || !address || address == MAP_FAILED) std::abort();
        if (munmap(address, SparseSlot) != 0) std::abort();
        return false;
    }
    return rc == 0;
}
#endif

// Reserves `span` bytes whose every slot reads as zeroes. Null when the platform refuses.
void* ReserveSparse(std::size_t span) {
#ifdef PS5_NATIVE
    void* address = ReserveCpuVirtualRange(span, SparseSlot);
    if (!address) return nullptr;
    const auto start = reinterpret_cast<std::uintptr_t>(address);
    for (std::size_t offset = 0; offset < span; offset += SparseSlot) {
        if (!MapSlot(start + offset, PROT_READ, zero_block)) {
            if (munmap(address, span) != 0) std::abort();
            return nullptr;
        }
    }
    return address;
#else
    void* address = mmap(nullptr, span, PROT_READ, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    return address == MAP_FAILED ? nullptr : address;
#endif
}

// Gives the slot at `at` memory of its own, zeroed and writable. sparse_mutex is held.
bool OwnSlot(std::uintptr_t at, std::int64_t* physical) {
#ifdef PS5_NATIVE
    // The block is zeroed before it appears in the table: a JIT thread may read the slot at any
    // moment, and the mapping changes in one step.
    if (!ZeroedBlock(physical)) return false;
    if (MapSlot(at, PROT_READ | PROT_WRITE, *physical)) return true;
    (void)sceKernelReleaseDirectMemory(*physical, SparseSlot);
    return false;
#else
    *physical = 0;
    return mprotect(reinterpret_cast<void*>(at), SparseSlot, PROT_READ | PROT_WRITE) == 0;
#endif
}

void ReleaseSparse(SparseRange& range) {
    const auto begin = range.begin.load(std::memory_order_relaxed);
    const std::size_t span = range.end - begin;
    if (munmap(reinterpret_cast<void*>(begin), span) != 0) std::abort();
    std::size_t owned = 0;
    for (std::size_t slot = 0; slot < span / SparseSlot; ++slot) {
        if (!range.owned[slot].load(std::memory_order_relaxed)) continue;
        ++owned;
#ifdef PS5_NATIVE
        if (sceKernelReleaseDirectMemory(range.physical[slot], SparseSlot) != 0) std::abort();
#endif
    }
    sparse_reserved.fetch_sub(span, std::memory_order_relaxed);
    sparse_committed.fetch_sub(owned * SparseSlot, std::memory_order_relaxed);
    range.begin.store(0, std::memory_order_release);
    delete[] range.owned;
    delete[] range.physical;
    range.owned = nullptr;
    range.physical = nullptr;
}

// Once: can tables be sparse here? On the console this is a check of the three mapping steps
// above with real memory; a refusal leaves the tables dense, as they were before.
bool SparseAvailable() {
    int state = sparse_state.load(std::memory_order_acquire);
    if (state != 0) return state == 1;
    const std::lock_guard lock{sparse_mutex};
    state = sparse_state.load(std::memory_order_relaxed);
    if (state != 0) return state == 1;
    bool ok = true;
    const char* step = "ok";
#ifdef PS5_NATIVE
    ok = !DevSetting("sparse_tables=off");
    if (!ok) step = "switched-off";
    if (ok) {
        (void)sceKernelEnableDmemAliasing(); // reports zero regardless; the mappings below are the check
        ok = ZeroedBlock(&zero_block);
        if (!ok) step = "zero-block";
    }
#endif
    if (ok) {
        auto* probe = static_cast<volatile std::uint64_t*>(ReserveSparse(2 * SparseSlot));
        const std::size_t words = SparseSlot / sizeof(std::uint64_t);
        std::int64_t physical = -1;
        if (probe == nullptr) {
            ok = false;
            step = "reserve";
        } else {
            if (probe[0] != 0 || probe[words - 1] != 0 || probe[words] != 0 || probe[2 * words - 1] != 0) {
                ok = false;
                step = "zero-read";
            } else if (!OwnSlot(reinterpret_cast<std::uintptr_t>(probe) + SparseSlot, &physical)) {
                ok = false;
                step = "own";
            } else {
                probe[words] = 0x5a17ed5a17ed5a17ull;
                probe[2 * words - 1] = 0x1234567890abcdefull;
                if (probe[words] != 0x5a17ed5a17ed5a17ull || probe[2 * words - 1] != 0x1234567890abcdefull ||
                    probe[0] != 0 || probe[words - 1] != 0 || probe[words + 1] != 0) {
                    ok = false;
                    step = "own-read";
                }
#ifdef PS5_NATIVE
                // The written slot goes back; the shared block must still be all zeroes.
                if (munmap(const_cast<std::uint64_t*>(probe) + words, SparseSlot) != 0 ||
                    sceKernelReleaseDirectMemory(physical, SparseSlot) != 0)
                    std::abort();
                if (!MapSlot(reinterpret_cast<std::uintptr_t>(probe) + SparseSlot, PROT_READ, zero_block) ||
                    probe[words] != 0 || probe[2 * words - 1] != 0) {
                    ok = false;
                    step = "shared-zero";
                }
#endif
            }
            if (munmap(const_cast<std::uint64_t*>(probe), 2 * SparseSlot) != 0) std::abort();
        }
    }
    char line[96];
    const int length = std::snprintf(line, sizeof(line), "EDEN_SPARSE_TABLES available=%d step=%s\n", ok ? 1 : 0, step);
    if (length > 0) Report(line);
    sparse_state.store(ok ? 1 : 2, std::memory_order_release);
    return ok;
}
} // namespace

// The first table asks this; the app asks at start, so the log says it in every session.
bool SparseTablesAvailable() noexcept {
    return SparseAvailable();
}

void* AllocateSparsePages(std::size_t size) noexcept {
    const std::size_t span = (size + SparseSlot - 1) / SparseSlot * SparseSlot;
    if (size < 2 * SparseSlot || span < size || !SparseAvailable()) return AllocateMemoryPages(size);
    const std::lock_guard lock{sparse_mutex};
    SparseRange* free_range = nullptr;
    for (auto& range : sparse_ranges)
        if (range.begin.load(std::memory_order_relaxed) == 0) {
            free_range = &range;
            break;
        }
    const std::size_t slots = span / SparseSlot;
    auto* owned = free_range ? new (std::nothrow) std::atomic<bool>[slots] : nullptr;
    auto* physical = owned ? new (std::nothrow) std::int64_t[slots] : nullptr;
    void* address = physical ? ReserveSparse(span) : nullptr;
    if (address == nullptr) {
        delete[] owned;
        delete[] physical;
        // The platform took the check's two slots but not this table: it is dense, as before.
        char line[96];
        const int length = std::snprintf(line, sizeof(line), "EDEN_SPARSE_TABLES dense bytes=%zu\n", size);
        if (length > 0) Report(line);
        return AllocateMemoryPages(size);
    }
    for (std::size_t slot = 0; slot < slots; ++slot) {
        owned[slot].store(false, std::memory_order_relaxed);
        physical[slot] = -1;
    }
    free_range->owned = owned;
    free_range->physical = physical;
    free_range->end = reinterpret_cast<std::uintptr_t>(address) + span;
    free_range->begin.store(reinterpret_cast<std::uintptr_t>(address), std::memory_order_release);
    sparse_reserved.fetch_add(span, std::memory_order_relaxed);
    return address;
}

void FreeSparsePages(void* base, std::size_t size) noexcept {
    if (!base) return;
    {
        const std::lock_guard lock{sparse_mutex};
        SparseRange* range = SparseRangeOf(reinterpret_cast<std::uintptr_t>(base));
        if (range != nullptr) {
            if (range->begin.load(std::memory_order_relaxed) != reinterpret_cast<std::uintptr_t>(base)) std::abort();
            ReleaseSparse(*range);
            return;
        }
    }
    FreeMemoryPages(base, size); // a table that was allocated dense
}

void CommitSparsePage(std::uintptr_t page) noexcept {
    // FreeSparsePages() destroys 'owned' under this same mutex.
    // Do not dereference the range or its slot bitmap before taking the lock:
    // it could have been released and the static range record reused.
    // This is a first-commit slow path, not the ordinary guest table read path.
    const std::lock_guard lock{sparse_mutex};
    SparseRange* range = SparseRangeOf(page);
    if (range == nullptr) return; // dense: already writable
    const auto begin = range->begin.load(std::memory_order_relaxed);
    const std::size_t slot = (page - begin) / SparseSlot;
    if (range->owned[slot].load(std::memory_order_relaxed)) return;
    if (!OwnSlot(begin + slot * SparseSlot, &range->physical[slot])) {
        // Out of memory in the middle of a guest mapping: there is no table to continue with.
        Report("EDEN_SPARSE_TABLES commit failed: out of memory\n");
        std::abort();
    }
    sparse_committed.fetch_add(SparseSlot, std::memory_order_relaxed);
    range->owned[slot].store(true, std::memory_order_release);
}

std::size_t SparseCommitSpan() noexcept {
    return SparseSlot;
}

// A complete zeroed sparse slot no longer needs private direct memory. Replace it with the
// process-wide read-only zero block again, then release its backing. SparseLargeVector calls this
// only after its committed-page bitmap says the whole 2 MiB slot is empty.
void DecommitSparsePage(std::uintptr_t page) noexcept {
    SparseRange* range = SparseRangeOf(page);
    if (range == nullptr) return; // Dense fallback: ZeroRegion already wrote the zeroes.
    const std::lock_guard lock{sparse_mutex};
    range = SparseRangeOf(page);
    if (range == nullptr) return;
    const auto begin = range->begin.load(std::memory_order_relaxed);
    const std::size_t slot = (page - begin) / SparseSlot;
    if (!range->owned[slot].load(std::memory_order_relaxed)) return;
    const std::uintptr_t at = begin + slot * SparseSlot;
#ifdef PS5_NATIVE
    const std::int64_t physical = range->physical[slot];
    // MAP_FIXED swaps the mapping at the same VA. Readers therefore see either the old private
    // block or the shared zero block, never an unmapped hole.
    if (!MapSlot(at, PROT_READ, zero_block)) std::abort();
    if (sceKernelReleaseDirectMemory(physical, SparseSlot) != 0) std::abort();
#else
    if (madvise(reinterpret_cast<void*>(at), SparseSlot, MADV_DONTNEED) != 0) std::abort();
    if (mprotect(reinterpret_cast<void*>(at), SparseSlot, PROT_READ) != 0) std::abort();
#endif
    range->physical[slot] = -1;
    range->owned[slot].store(false, std::memory_order_release);
    sparse_committed.fetch_sub(SparseSlot, std::memory_order_relaxed);
}

// Address space the sparse tables span, and the memory they hold (for the log).
void SparseUsage(std::size_t* reserved, std::size_t* committed) noexcept {
    *reserved = sparse_reserved.load(std::memory_order_relaxed);
    *committed = sparse_committed.load(std::memory_order_relaxed);
}

// ---- A range that grows: the heap ----
//
// ReserveMemoryRange takes address space only. CommitMemoryRange backs a part of it with zeroed
// memory, for good. Both work in whole large pages; the heap commits its range from the start,
// one piece after another, as allocations need it (headless/heap_arenas.inc).
void* ReserveMemoryRange(std::size_t size) noexcept {
    if (size == 0 || size % LargePage != 0) return nullptr;
#ifdef PS5_NATIVE
    // Development A/B: dev-settings heap=whole takes the heap's memory at start, as before.
    if (DevSetting("heap=whole")) return nullptr;
    return ReserveCpuVirtualRange(size, LargePage);
#else
    void* address = mmap(nullptr, size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    return address == MAP_FAILED ? nullptr : address;
#endif
}

bool CommitMemoryRange(void* address, std::size_t size, std::int64_t* physical_out) noexcept {
    if (physical_out) *physical_out = -1;
    if (address == nullptr || size == 0 || size % LargePage != 0 ||
        reinterpret_cast<std::uintptr_t>(address) % LargePage != 0)
        return false;
#ifdef PS5_NATIVE
    // New backing pieces are allocated, mapped and cleared synchronously.
    // Measure ONLY heap growth (not the per-malloc or per-frame hot path).
    timespec started{}, allocated{}, mapped{}, zeroed{};
    (void)clock_gettime(CLOCK_MONOTONIC, &started);
    std::int64_t physical = -1;
    if (AllocateDirectOwned(size, LargePage, &physical) != 0)
        return false;
    (void)clock_gettime(CLOCK_MONOTONIC, &allocated);
    void* at = address;
    const auto map_rc = sceKernelMapDirectMemory(&at, size, PROT_READ | PROT_WRITE,
                                                MAP_FIXED, physical, LargePage);
    if (map_rc != 0 || at != address) {
        // MAP_FIXED should not return a different VA, but on success it owns
        // that mapping. Unmap the unexpected alias BEFORE releasing its direct
        // physical backing; otherwise a live mapping could retain stale PA.
        // A failed fixed-map that mutates its output gives no reliable
        // ownership information. Do not free the direct memory in that case.
        if (map_rc != 0 && at != address) std::abort();
        if (map_rc == 0 && at != address && at && at != MAP_FAILED &&
            munmap(at, size) != 0) std::abort();
        if (sceKernelReleaseDirectMemory(physical, size) != 0) std::abort();
        return false;
    }
    (void)clock_gettime(CLOCK_MONOTONIC, &mapped);
    std::memset(address, 0, size);
    (void)clock_gettime(CLOCK_MONOTONIC, &zeroed);
    const auto delta_ns = [](const timespec& a, const timespec& b) noexcept -> unsigned long long {
        const auto elapsed = (static_cast<long long>(b.tv_sec) - static_cast<long long>(a.tv_sec)) *
                                 1000000000LL + (b.tv_nsec - a.tv_nsec);
        return elapsed > 0 ? static_cast<unsigned long long>(elapsed) : 0ULL;
    };
    // The heap grows through here: no stdio that may recurse into malloc.
    char line[192];
    const int length = std::snprintf(line, sizeof(line),
        "EDEN_HEAP_PIECE bytes=%zu va=%p pa=%llx alloc_ns=%llu map_ns=%llu zero_ns=%llu\n",
        size, address, static_cast<unsigned long long>(physical),
        delta_ns(started, allocated), delta_ns(allocated, mapped), delta_ns(mapped, zeroed));
    if (length > 0) Note(line);
    // The 128 MiB initial heap backing has a specific physical owner. Return
    // it without any dynamic bookkeeping, so failed mspace initialization
    // can release PA as well as the 3 GiB virtual reservation.
    if (physical_out) *physical_out = physical;
    return true;
#else
    return mprotect(address, size, PROT_READ | PROT_WRITE) == 0;
#endif
}
bool CommitMemoryRange(void* address, std::size_t size) noexcept {
    return CommitMemoryRange(address, size, nullptr);
}

// A just-committed heap growth segment whose mspace constructor returned
// NULL has no published owner and no live pointers. Replace ONLY that whole
// piece with an inaccessible guard and free its exact direct backing. The
// rest of the 3 GiB reservation remains untouched for existing mspaces.
// JIT sparse rollback already uses this same fixed PROT_NONE mapping pattern.
void RollbackUnpublishedHeapGrowth(void* address, std::size_t size,
                                   std::int64_t physical) noexcept {
    if (!address || size == 0 || size % LargePage != 0 ||
        reinterpret_cast<std::uintptr_t>(address) % LargePage != 0)
        std::abort();
#ifdef PS5_NATIVE
    if (physical < 0 || !cpu_mapping_range(address, size)) std::abort();
#else
    (void)physical;
#endif
    void* guard = mmap(address, size, PROT_NONE, MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (guard != address) std::abort();
#ifdef PS5_NATIVE
    if (sceKernelReleaseDirectMemory(physical, size) != 0) std::abort();
#endif
}

void AbandonInitialHeapReservation(void* base, std::size_t reserved,
                                   std::int64_t first_physical, std::size_t committed) noexcept {
    // Called ONLY when creating the very first mspace failed. There are no
    // live allocations or mspace descendants, and heap state is unpublished.
    if (!base || !reserved || !committed || committed > reserved)
        std::abort();
#ifdef PS5_NATIVE
    if (first_physical < 0) std::abort();
#else
    (void)first_physical;
#endif
    // Every direct-memory mapping must be unmapped before releasing its PA.
    if (munmap(base, reserved) != 0) std::abort();
#ifdef PS5_NATIVE
    if (sceKernelReleaseDirectMemory(first_physical, committed) != 0) std::abort();
#endif
}
} // namespace Common
