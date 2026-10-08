// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <mutex>
#include <unordered_map>
#include <sys/mman.h>
#include <unistd.h>
#include <xbyak/xbyak.h>
#ifdef EDEN_JIT_ALIAS_NATIVE
#include "experimental_performance.h"
#endif
namespace Common {
void* AllocateMemoryPages(std::size_t) noexcept;
void FreeMemoryPages(void*) noexcept;
void* MapExecutableAlias(void*, std::size_t) noexcept;
#ifdef EDEN_JIT_ALIAS_NATIVE
void CountDenseJitDirect(void*, bool acquire) noexcept;
std::size_t ExecutableAliasSpan(void*) noexcept;
#endif
#ifdef EDEN_JIT_ALIAS_NATIVE
void* ReserveSparseJitCode(std::size_t, void**) noexcept;
bool CommitSparseJitCode(void*, std::size_t) noexcept;
bool IsSparseJitCode(const void*) noexcept;
void ReleaseSparseJitCode(void*) noexcept;
#endif
}
// Separate RW/NX and RX views avoid changing page permissions per compiled block.
// Unsupported native JIT allocation falls back to the qualified owned W^X path.
inline Xbyak::Allocator* EdenJitAllocator() {
    struct Allocator final : Xbyak::Allocator {
        struct Mapping { void* writable; std::size_t size; bool sparse = false; };
        std::mutex mutex;
        std::unordered_map<std::uint8_t*, Mapping> mappings;
        std::uint8_t* alloc(std::size_t size) override {
#ifdef EDEN_JIT_ALIAS_NATIVE
            auto* diagnostics = stdout; // Native stdout is the separate heap log.
#else
            auto* diagnostics = stderr; // Host stdout is the strict lifecycle receipt.
#endif
            const long page = sysconf(_SC_PAGESIZE);
            if (!size || page <= 0 || size > std::numeric_limits<std::size_t>::max() - page)
                return nullptr;
            const auto span = (size + page - 1) & ~(std::size_t(page) - 1);
            void* executable = MAP_FAILED;
            void* writable = MAP_FAILED;
#ifdef EDEN_JIT_ALIAS_NATIVE
            // Optional per-title path: stable RX/RW virtual ranges, commit only
            // the pages requested by BlockOfCode::EnsureMemoryCommitted.
            if (Eden::Experimental::sparse_jit_cache.load(std::memory_order_relaxed)) {
                // Xbyak may request an arena ending between two 2 MiB direct
                // memory chunks. Reserve whole *virtual* chunks while keeping
                // physical commits demand-backed; otherwise a valid uneven
                // request fails ReserveSparseJitCode's alignment contract.
                constexpr std::size_t kSparseChunk = 2u * 1024u * 1024u;
                if (size > std::numeric_limits<std::size_t>::max() - (kSparseChunk - 1))
                    return nullptr;
                const std::size_t sparse_span =
                    (size + kSparseChunk - 1) & ~(kSparseChunk - 1);
                executable = Common::ReserveSparseJitCode(sparse_span, &writable);
                if (executable) {
                    auto* pointer = static_cast<std::uint8_t*>(executable);
                    try {
                        std::lock_guard lock(mutex);
                        if (!mappings.emplace(pointer,
                                              Mapping{writable, sparse_span, true}).second)
                            std::abort(); // A live executable VA must be unique
                    } catch (...) {
                        Common::ReleaseSparseJitCode(executable);
                        return nullptr;
                    }
                    std::fprintf(diagnostics, "EDEN_JIT_ALIAS rx=%p rw=%p bytes=%zu active=1 sparse=1\n",
                                 executable, writable, sparse_span);
                    return pointer;
                }
                // Demand-backed JIT must NOT silently switch to a full
                // physical dense allocation on virtual-range failure:
                // that recreates the late-game RAM exhaustion observed on
                // real FC27 hardware. Let the A64/A32 JIT constructor
                // retry with a smaller stable VA arena. If even the
                // baseline fails, surface startup failure instead of
                // violating the explicitly selected sparse contract.
                std::fprintf(diagnostics, "EDEN_JIT_SPARSE_RESERVE_FAILED bytes=%zu errno=%d fallback=smaller_virtual_arena\n",
                             sparse_span, errno);
                return nullptr;
            }
            writable = Common::AllocateMemoryPages(size);
            if (!writable) return nullptr;
            Common::CountDenseJitDirect(writable, true);
            executable = Common::MapExecutableAlias(writable, size);
            if (!executable) {
                // PS5's JIT code must have a distinct executable alias.
                // Returning RW/NX here silently publishes a non-executable
                // instruction pointer. Release direct RAM and let Xbyak
                // propagate ERR_CANT_ALLOC to the bounded startup fallback.
                const int original_errno = errno;
                std::fprintf(diagnostics,
                             "EDEN_JIT_ALIAS bytes=%zu active=0 errno=%d fallback=retry\n",
                             span, original_errno);
                Common::CountDenseJitDirect(writable, false);
                Common::FreeMemoryPages(writable);
                errno = original_errno;
                return nullptr;
            }
#else
            const int executable_fd = memfd_create("eden-jit", MFD_CLOEXEC);
            if (executable_fd >= 0 && ftruncate(executable_fd, span) == 0) {
                executable = mmap(nullptr, span, PROT_READ | PROT_EXEC, MAP_SHARED, executable_fd, 0);
                writable = mmap(nullptr, span, PROT_READ | PROT_WRITE, MAP_SHARED, executable_fd, 0);
            }
            if (executable_fd >= 0 && close(executable_fd) != 0) std::abort();
#endif
            if (executable != MAP_FAILED && executable && writable != MAP_FAILED && writable && executable != writable) {
                auto* pointer = static_cast<std::uint8_t*>(executable);
                // The native direct mapping may round 3 MiB to a 4 MiB
                // large-page alias. Keep the REAL RX mapping length so free()
                // cannot leave an orphan executable tail after game exit.
                std::size_t mapped_span = span;
#ifdef EDEN_JIT_ALIAS_NATIVE
                mapped_span = Common::ExecutableAliasSpan(writable);
                if (mapped_span < span) std::abort();
#endif
                try {
                    std::lock_guard lock(mutex);
                    mappings.emplace(pointer, Mapping{writable, mapped_span});
                    std::fprintf(diagnostics,
                                 "EDEN_JIT_ALIAS rx=%p rw=%p bytes=%zu active=1\n",
                                 static_cast<void*>(pointer), writable, mapped_span);
                    return pointer;
                } catch (...) {
                    // Release both views before reporting allocation failure.
                    if (munmap(executable, mapped_span) != 0) std::abort();
#ifdef EDEN_JIT_ALIAS_NATIVE
                    Common::CountDenseJitDirect(writable, false);
                    Common::FreeMemoryPages(writable);
#else
                    if (munmap(writable, span) != 0) std::abort();
#endif
                    return nullptr;
                }
            }
#ifdef EDEN_JIT_ALIAS_NATIVE
            std::abort(); // Distinct views are required by the direct mapper.
#else
            if (executable != MAP_FAILED && executable && munmap(executable, span) != 0) std::abort();
            if (writable != MAP_FAILED && writable && writable != executable && munmap(writable, span) != 0) std::abort();
            std::fprintf(diagnostics, "EDEN_JIT_ALIAS bytes=%zu active=0 errno=%d\n", span, errno);
            return static_cast<std::uint8_t*>(Common::AllocateMemoryPages(size));
#endif
        }
        std::uint8_t* writableAddress(std::uint8_t* pointer) override {
            std::lock_guard lock(mutex);
            const auto entry = mappings.find(pointer);
            return entry == mappings.end() ? pointer : static_cast<std::uint8_t*>(entry->second.writable);
        }
        void free(std::uint8_t* pointer) override {
            {
                std::lock_guard lock(mutex);
                const auto entry = mappings.find(pointer);
                if (entry != mappings.end()) {
                    const auto mapping = entry->second;
                    if (mapping.sparse) {
#ifdef EDEN_JIT_ALIAS_NATIVE
                        Common::ReleaseSparseJitCode(pointer);
#endif
                        mappings.erase(entry);
                        return;
                    }
                    if (munmap(pointer, mapping.size) != 0) std::abort();
#ifdef EDEN_JIT_ALIAS_NATIVE
                    Common::CountDenseJitDirect(mapping.writable, false);
                    Common::FreeMemoryPages(mapping.writable);
#else
                    if (munmap(mapping.writable, mapping.size) != 0) std::abort();
#endif
                    mappings.erase(entry);
                    return;
                }
            }
#ifdef EDEN_JIT_ALIAS_NATIVE
            Common::CountDenseJitDirect(pointer, false);
#endif
            Common::FreeMemoryPages(pointer);
        }
        bool useProtect() const override { return false; }
    };
    static Allocator allocator;
    return &allocator;
}
