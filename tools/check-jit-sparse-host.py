#!/usr/bin/env python3
"""Host mock for PS5 native sparse JIT memory mapping; not a console qualification.

Compiles actual src/memory_pages.cpp with PS5_NATIVE and only seven mocked
sceKernel direct-memory APIs. Checks bootstrap, dual aliases, growth,
ownership accounting, allocation failure and cleanup without a game/build.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CXX = next((p for p in ("clang++-18", "clang++", "g++") if shutil.which(p)), None)
if not CXX:
    raise SystemExit("C++20 compiler required for native-memory mock")

MOCK = r"""
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <cassert>
#include <cerrno>
#include <csignal>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include "jit-allocator.h"
#include "experimental_performance.h"

namespace Common {
bool ProbeSparseJitAlias() noexcept;
void* ReserveSparseJitCode(std::size_t size, void** writable_out) noexcept;
bool IsSparseJitCode(const void*) noexcept;
bool CommitSparseJitCode(void*, std::size_t) noexcept;
void ReleaseSparseJitCode(void*) noexcept;
void SparseJitUsage(std::size_t*, std::size_t*) noexcept;
}

constexpr std::size_t PAGE = 2 * 1024 * 1024;
static int owned_fds = 0;
static int alloc_calls = 0;
static int fail_at_call = 0;
static int map_calls = 0;
static int fail_map_at = 0;
static bool fail_after_mapping = false;
static int fail_protect_at = 0;
static int protect_calls = 0;
static std::uintptr_t next_reservation = 0x1000000000ULL;

extern "C" std::int64_t sceKernelGetDirectMemorySize() {
    return std::int64_t{12} << 30;
}
extern "C" std::int32_t sceKernelEnableDmemAliasing() { return 0; }
extern "C" int sceKernelDebugOutText(int, const char*) { return 0; }

extern "C" std::int32_t sceKernelReserveVirtualRange(
        void** address, std::size_t size, int, std::size_t alignment) {
    assert(size && alignment == PAGE && size % PAGE == 0);
    for (int trial = 0; trial < 16; ++trial) {
        const auto candidate = next_reservation;
        next_reservation += ((size + PAGE - 1) / PAGE) * PAGE + PAGE;
        void* p = mmap(reinterpret_cast<void*>(candidate), size, PROT_NONE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (p != MAP_FAILED) { *address = p; return 0; }
    }
    return -1;
}
extern "C" std::int32_t sceKernelAllocateDirectMemory(
        std::int64_t, std::int64_t, std::size_t size, std::size_t align,
        int type, std::int64_t* physical) {
    ++alloc_calls;
    if (fail_at_call && alloc_calls == fail_at_call) return -1;
    assert(size == PAGE && align == PAGE && type == 12);
    const int fd = memfd_create("jit-direct-memory-mock", MFD_CLOEXEC);
    assert(fd >= 0 && ftruncate(fd, static_cast<off_t>(size)) == 0);
    ++owned_fds;
    *physical = static_cast<std::int64_t>(fd) << 32;
    return 0;
}
extern "C" std::int32_t sceKernelMapDirectMemory(
        void** address, std::size_t size, int prot, int flags,
        std::int64_t physical, std::size_t align) {
    assert(size == PAGE && align == PAGE && (flags & MAP_FIXED));
    assert((prot & PROT_EXEC) == 0);
    ++map_calls;
    if (fail_map_at == map_calls && !fail_after_mapping) return -1;
    const int fd = static_cast<int>(physical >> 32);
    void* mapped = mmap(*address, size, prot, MAP_SHARED | MAP_FIXED, fd, 0);
    if (mapped == MAP_FAILED) return -1;
    *address = mapped;
    // Simulate a PS5 syscall that changes a mapping but reports failure.
    if (fail_map_at == map_calls && fail_after_mapping) return -1;
    return 0;
}
#ifdef EDEN_TEST_WRAP_MPROTECT
extern "C" int __real_mprotect(void*, std::size_t, int);
extern "C" int __wrap_mprotect(void* address, std::size_t size, int prot) {
    ++protect_calls;
    if (fail_protect_at == protect_calls) { errno = EPERM; return -1; }
    return __real_mprotect(address, size, prot);
}
#endif
extern "C" std::int32_t sceKernelReleaseDirectMemory(
        std::int64_t physical, std::size_t size) {
    assert(size == PAGE);
    --owned_fds;
    return close(static_cast<int>(physical >> 32));
}

// Failed sparse growth must leave the next, not-yet-owned direct page
// inaccessible on BOTH aliases. Merely checking accounting misses unsafe
// partially mapped executable pages.
void assert_inaccessible(const volatile unsigned char* address) {
    const pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        const auto byte = *address;
        (void)byte;
        _exit(0);
    }
    int status = 0;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGSEGV);
}
void usage(std::size_t reserve, std::size_t commit) {
    std::size_t a = 0, b = 0;
    Common::SparseJitUsage(&a, &b);
    assert(a == reserve && b == commit);
}
int main() {
    usage(0, 0);
    assert(Common::ProbeSparseJitAlias());
    assert(owned_fds == 0);
    const int before = alloc_calls;

    void* rw = nullptr;
    void* rx = Common::ReserveSparseJitCode(64 * 1024 * 1024, &rw);
    assert(rx && rw && rx != rw);
    assert(Common::IsSparseJitCode(rx));
    assert(!Common::IsSparseJitCode(rw));
    // Constant-pool bootstrap must be physical before first Xbyak write.
    usage(64 * 1024 * 1024, 2 * PAGE);
    assert(alloc_calls == before + 2);
    auto* w = static_cast<volatile unsigned char*>(rw);
    auto* x = static_cast<volatile unsigned char*>(rx);
    w[0] = 13;
    w[2 * PAGE - 1] = 47;
    assert(x[0] == 13 && x[2 * PAGE - 1] == 47);
    assert(Common::CommitSparseJitCode(rx, 5 * 1024 * 1024));
    usage(64 * 1024 * 1024, 3 * PAGE);
    w[2 * PAGE] = 99;
    assert(x[2 * PAGE] == 99);

    // A native OOM BEFORE a new mapping must not leak direct pages or
    // discard the prior committed code; the caller can reuse them.
    fail_at_call = alloc_calls + 1;
    assert(!Common::CommitSparseJitCode(rx, 8 * 1024 * 1024));
    usage(64 * 1024 * 1024, 3 * PAGE);
    assert(Common::CommitSparseJitCode(rx, 5 * 1024 * 1024));
    assert(!Common::CommitSparseJitCode(rx, 65 * 1024 * 1024));
    assert(x[0] == 13 && x[2 * PAGE] == 99);
    fail_at_call = 0;

    // Recoverable mid-map failures: only the NEW chunk is rolled back.
    // A previous executable chunk must remain intact and usable.
    for (int point = 0; point != 3; ++point) {
#ifndef EDEN_TEST_WRAP_MPROTECT
        if (point == 2) continue;
#endif
        fail_map_at = map_calls + (point == 0 ? 1 : 2);
        fail_after_mapping = point == 1;
        if (point == 2) {
            fail_map_at = 0;
            fail_after_mapping = false;
            fail_protect_at = protect_calls + 1;
        }
        assert(!Common::CommitSparseJitCode(rx, 8 * 1024 * 1024));
        usage(64 * 1024 * 1024, 3 * PAGE);
        assert(owned_fds == 3);
        assert(x[0] == 13 && x[2 * PAGE] == 99);
        assert_inaccessible(w + 3 * PAGE);
        assert_inaccessible(x + 3 * PAGE);
        fail_map_at = 0;
        fail_after_mapping = false;
        fail_protect_at = 0;
    }
    assert(Common::CommitSparseJitCode(rx, 8 * 1024 * 1024));
    usage(64 * 1024 * 1024, 4 * PAGE);
    w[3 * PAGE] = 0x77;
    assert(x[3 * PAGE] == 0x77);
    Common::ReleaseSparseJitCode(rx);
    usage(0, 0);
    assert(owned_fds == 0);

    // Bootstrap itself can fail: the reservation must be torn down,
    // allowing the allocator to fall back to qualified dense backing.
    fail_at_call = alloc_calls + 1;
    void* failed_writable = nullptr;
    assert(Common::ReserveSparseJitCode(32 * 1024 * 1024,
                                       &failed_writable) == nullptr);
    assert(failed_writable == nullptr);
    usage(0, 0);
    assert(owned_fds == 0);

    // The second 2 MiB bootstrap allocation can also fail after the first
    // chunk has already been installed. Both VA views and the first owned
    // direct-memory chunk must be released before dense fallback.
    fail_at_call = alloc_calls + 2;
    failed_writable = nullptr;
    assert(Common::ReserveSparseJitCode(32 * 1024 * 1024,
                                       &failed_writable) == nullptr);
    assert(failed_writable == nullptr);
    usage(0, 0);
    assert(owned_fds == 0);

    // A partially mapped bootstrap must also release both VA ranges and
    // physical memory, rather than leaving a dangling constructor pointer.
    fail_at_call = 0;
    fail_map_at = map_calls + 2;
    fail_after_mapping = false;
    failed_writable = nullptr;
    assert(Common::ReserveSparseJitCode(32 * 1024 * 1024,
                                       &failed_writable) == nullptr);
    assert(failed_writable == nullptr);
    fail_map_at = 0;
    usage(0, 0);
    assert(owned_fds == 0);
    // End-to-end host simulation with the REAL Xbyak allocator adapter.
    // A virtual 64 MiB JIT arena must consume only its 4 MiB bootstrap
    // physical backing until the code emitter explicitly asks for more.
    const int alloc_before_adapter = alloc_calls;
    Eden::Experimental::sparse_jit_cache.store(true);
    auto* allocator = EdenJitAllocator();
    auto* executable = allocator->alloc(64 * 1024 * 1024);
    assert(executable);
    auto* writable = allocator->writableAddress(executable);
    assert(writable && writable != executable);
    assert(Common::IsSparseJitCode(executable));
    assert(alloc_calls == alloc_before_adapter + 2);
    usage(64 * 1024 * 1024, 4 * 1024 * 1024);
    const auto& stats_at_boot = owned_fds;
    assert(stats_at_boot == 2);
    writable[0] = 0x51;
    assert(executable[0] == 0x51);
    assert(Common::CommitSparseJitCode(executable, 9 * 1024 * 1024));
    usage(64 * 1024 * 1024, 10 * 1024 * 1024);
    writable[8 * 1024 * 1024] = 0x42;
    assert(executable[8 * 1024 * 1024] == 0x42);
    allocator->free(executable);
    usage(0, 0);
    assert(owned_fds == 0);
    Eden::Experimental::sparse_jit_cache.store(false);
    std::puts("PASS sparse PS5 direct-memory mocks: alias/bootstrap/growth/OOM/partial-map rollback/cleanup");
    std::puts("PASS actual Xbyak JIT adapter: 64MiB virtual / 4MiB physical at boot, 10MiB after growth, zero after free");
}
""";

XBYAK_HEADER = r"""
#pragma once
#include <cstddef>
#include <cstdint>
namespace Xbyak {
struct Allocator {
    virtual ~Allocator() = default;
    virtual std::uint8_t* alloc(std::size_t) = 0;
    virtual void free(std::uint8_t*) = 0;
    virtual std::uint8_t* writableAddress(std::uint8_t* p) { return p; }
    virtual bool useProtect() const { return true; }
};
}
"""

with tempfile.TemporaryDirectory(prefix="eden-sparse-host-") as temp:
    source = Path(temp) / "sparse.cpp"
    executable = Path(temp) / "sparse-check"
    (Path(temp) / "xbyak").mkdir()
    (Path(temp) / "xbyak" / "xbyak.h").write_text(XBYAK_HEADER)
    source.write_text(MOCK)
    linux = sys.platform.startswith("linux")
    subprocess.run([CXX, "-std=c++20", "-O1", "-g0", "-pthread", "-Wall",
                    "-Wextra", "-Werror", "-DPS5_NATIVE=1",
                    "-DEDEN_JIT_ALIAS_NATIVE=1",
                    "-I", str(Path(temp)), "-I", str(ROOT / "headless"),
                    *(["-DEDEN_TEST_WRAP_MPROTECT=1", "-Wl,--wrap=mprotect"]
                      if linux else []),
                    str(source), str(ROOT / "src/memory_pages.cpp"),
                    "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)

print("PASS sparse JIT host-native mock; real PS5 firmware mapping remains unqualified")
