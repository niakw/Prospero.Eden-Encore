// SPDX-License-Identifier: GPL-3.0-or-later
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
    const auto limit = sceKernelGetDirectMemorySize();
    auto rc = sceKernelAllocateDirectMemory(0, limit, total, lead, 12, &physical);
    if (rc != 0) {
        std::fprintf(stderr, "Direct allocation failed: rc=%08x bytes=%zu limit=%lld\n",
                     unsigned(rc), total, static_cast<long long>(limit));
        errno = ENOMEM;
        return nullptr;
    }
    rc = sceKernelMapDirectMemory(&base, total, PROT_READ | PROT_WRITE, 0, physical, lead);
    if (rc != 0 || !cpu_mapping_address(base)) {
        std::fprintf(stderr, "Direct mapping failed: rc=%08x bytes=%zu\n", unsigned(rc), total);
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

#ifdef PS5_NATIVE
// Direct-memory start of an AllocateMemoryPages block's first data byte.
std::int64_t DirectMemoryStart(const void* pointer) noexcept {
    const long page = sysconf(_SC_PAGESIZE);
    if (!pointer || page <= 0) std::abort();
    const auto& header = header_of(pointer, page);
    return header.physical + static_cast<std::int64_t>(header.lead);
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
    if (rc != 0 || !cpu_mapping_address(alias)) {
        std::printf("EDEN_JIT_ALIAS_MAP rc=%08x bytes=%zu\n", unsigned(rc), span);
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
}

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
    void* rw = reinterpret_cast<void*>(cpu_mapping_hint);
    if (sceKernelReserveVirtualRange(&rw, size, 0, LargePage) != 0)
        return nullptr;
    if (!cpu_mapping_range(rw, size)) {
        if (munmap(rw, size) != 0) std::abort();
        return nullptr;
    }
    void* rx = reinterpret_cast<void*>(cpu_mapping_hint);
    if (sceKernelReserveVirtualRange(&rx, size, 0, LargePage) != 0) {
        if (munmap(rw, size) != 0) std::abort();
        return nullptr;
    }
    if (!cpu_mapping_range(rx, size) || rx == rw) {
        if (rx == rw) std::abort(); // Kernel returned overlapping reservations.
        if (rx && rx != MAP_FAILED && munmap(rx, size) != 0) std::abort();
        if (munmap(rw, size) != 0) std::abort();
        return nullptr;
    }
    try {
        SparseJitRegion region;
        region.writable = rw;
        region.capacity = size;
        region.physical.reserve(size / LargePage);
        const std::lock_guard lock{sparse_jit_mutex};
        if (!sparse_jit_regions.emplace(rx, std::move(region)).second)
            std::abort();
    } catch (...) {
        if (munmap(rx, size) != 0 || munmap(rw, size) != 0) std::abort();
        errno = ENOMEM;
        return nullptr;
    }
    // This firmware wrapper reports zero even if it is unsupported; actual
    // per-chunk MapDirectMemory/mprotect calls below are the qualification.
    (void)sceKernelEnableDmemAliasing();
    *writable_out = rw;
    std::printf("EDEN_JIT_SPARSE_RESERVE rx=%p rw=%p capacity=%zu committed=0\n", rx, rw, size);
    return rx;
}

// Called only by BlockOfCode::EnsureMemoryCommitted before emission.
// Never commit at an asynchronous page fault in executing JIT code.
bool CommitSparseJitCode(void* executable, std::size_t required) noexcept {
    const std::lock_guard lock{sparse_jit_mutex};
    const auto it = sparse_jit_regions.find(executable);
    if (it == sparse_jit_regions.end() || required > it->second.capacity) return false;
    auto& region = it->second;
    const std::size_t target = (required + LargePage - 1) / LargePage * LargePage;
    while (region.committed < target) {
        std::int64_t physical = -1;
        if (sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(),
                                           LargePage, LargePage, 12, &physical) != 0) {
            std::fprintf(stderr, "EDEN_JIT_SPARSE_OOM capacity=%zu committed=%zu required=%zu\n",
                         region.capacity, region.committed, required);
            return false;
        }
        auto* rw = static_cast<std::uint8_t*>(region.writable) + region.committed;
        auto* rx = static_cast<std::uint8_t*>(executable) + region.committed;
        void* actual_rw = rw;
        void* actual_rx = rx;
        // MAP_FIXED replaces the unbacked reservation with the *same* direct
        // allocation in two views. A failed partial mapping is fatal rather
        // than leaving stale executable pointers in a corrupt JIT region.
        if (sceKernelMapDirectMemory(&actual_rw, LargePage, PROT_READ | PROT_WRITE,
                                     MAP_FIXED, physical, LargePage) != 0 || actual_rw != rw) {
            std::fprintf(stderr, "EDEN_JIT_SPARSE_MAP failed=rw at=%p\n", rw);
            std::abort();
        }
        std::memset(rw, 0, LargePage);
        if (sceKernelMapDirectMemory(&actual_rx, LargePage, PROT_READ,
                                     MAP_FIXED, physical, LargePage) != 0 || actual_rx != rx ||
            mprotect(rx, LargePage, PROT_READ | PROT_EXEC) != 0) {
            std::fprintf(stderr, "EDEN_JIT_SPARSE_MAP failed=rx at=%p\n", rx);
            std::abort();
        }
        region.physical.push_back(physical); // capacity reserved at region creation
        region.committed += LargePage;
        sparse_jit_committed += LargePage;
    }
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
        remaining = sparse_jit_committed;
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
    if (sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), SparseSlot, SparseSlot, 12, physical) != 0)
        return false;
    void* view = reinterpret_cast<void*>(cpu_mapping_hint);
    if (sceKernelMapDirectMemory(&view, SparseSlot, PROT_READ | PROT_WRITE, 0, *physical, SparseSlot) != 0) {
        (void)sceKernelReleaseDirectMemory(*physical, SparseSlot);
        return false;
    }
    std::memset(view, 0, SparseSlot);
    if (munmap(view, SparseSlot) != 0) std::abort();
    return true;
}
bool MapSlot(std::uintptr_t at, int protection, std::int64_t physical) {
    void* address = reinterpret_cast<void*>(at);
    return sceKernelMapDirectMemory(&address, SparseSlot, protection, MAP_FIXED, physical, SparseSlot) == 0 &&
           address == reinterpret_cast<void*>(at);
}
#endif

// Reserves `span` bytes whose every slot reads as zeroes. Null when the platform refuses.
void* ReserveSparse(std::size_t span) {
#ifdef PS5_NATIVE
    void* address = reinterpret_cast<void*>(cpu_mapping_hint);
    if (sceKernelReserveVirtualRange(&address, span, 0, SparseSlot) != 0) return nullptr;
    if (!cpu_mapping_range(address, span)) {
        (void)munmap(address, span);
        return nullptr;
    }
    const auto start = reinterpret_cast<std::uintptr_t>(address);
    for (std::size_t offset = 0; offset < span; offset += SparseSlot) {
        if (!MapSlot(start + offset, PROT_READ, zero_block)) {
            (void)munmap(address, span);
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
    SparseRange* range = SparseRangeOf(page);
    if (range == nullptr) return; // dense: already writable
    const auto begin = range->begin.load(std::memory_order_relaxed);
    const std::size_t slot = (page - begin) / SparseSlot;
    if (range->owned[slot].load(std::memory_order_acquire)) return;
    const std::lock_guard lock{sparse_mutex};
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
    void* address = reinterpret_cast<void*>(cpu_mapping_hint);
    if (sceKernelReserveVirtualRange(&address, size, 0, LargePage) != 0) return nullptr;
    if (!cpu_mapping_range(address, size)) {
        (void)munmap(address, size);
        return nullptr;
    }
    return address;
#else
    void* address = mmap(nullptr, size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    return address == MAP_FAILED ? nullptr : address;
#endif
}

bool CommitMemoryRange(void* address, std::size_t size) noexcept {
    if (address == nullptr || size == 0 || size % LargePage != 0 ||
        reinterpret_cast<std::uintptr_t>(address) % LargePage != 0)
        return false;
#ifdef PS5_NATIVE
    std::int64_t physical = -1;
    if (sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), size, LargePage, 12, &physical) != 0)
        return false;
    void* at = address;
    if (sceKernelMapDirectMemory(&at, size, PROT_READ | PROT_WRITE, MAP_FIXED, physical, LargePage) != 0 ||
        at != address) {
        (void)sceKernelReleaseDirectMemory(physical, size);
        return false;
    }
    // The heap grows through here: no stdio (it may allocate).
    char line[96];
    const int length = std::snprintf(line, sizeof(line), "EDEN_HEAP_PIECE bytes=%zu va=%p pa=%llx\n", size, address,
                                     static_cast<unsigned long long>(physical));
    if (length > 0) Note(line);
    std::memset(address, 0, size);
    return true;
#else
    return mprotect(address, size, PROT_READ | PROT_WRITE) == 0;
#endif
}
} // namespace Common
