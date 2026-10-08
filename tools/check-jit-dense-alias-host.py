#!/usr/bin/env python3
"""Host-test the REAL EdenJitAllocator dense PS5 branch without upstream downloads.

A minimal Xbyak allocator interface shim and owned-memory mocks exercise the
actual headless/jit-allocator.h: alias failure MUST fail closed and free direct
memory, while successful ownership is released exactly once. This does not
qualify PS5 kernel MAP_FIXED, RX permissions or real code execution.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CXX = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if CXX is None:
    raise SystemExit("C++20 compiler required for native dense JIT alias contract")

XBYAK = r"""
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
CPP = r"""
#include "jit-allocator.h"
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <limits>
#include <unordered_map>
#include <sys/mman.h>

namespace {
std::unordered_map<void*, std::size_t> owned;
std::size_t dense_bytes = 0;
bool fail_direct = false;
bool fail_alias = false;
std::size_t frees = 0;
}
namespace Common {
void* AllocateMemoryPages(std::size_t size) noexcept {
    if (fail_direct) { errno = ENOMEM; return nullptr; }
    void* p = mmap(nullptr, size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED) return nullptr;
    try { owned.emplace(p, size); }
    catch (...) { munmap(p, size); return nullptr; }
    return p;
}
void FreeMemoryPages(void* p) noexcept {
    if (!p) return;
    auto it = owned.find(p);
    assert(it != owned.end());
    const auto size = it->second;
    owned.erase(it);
    assert(munmap(p, size) == 0);
    ++frees;
}
void CountDenseJitDirect(void* p, bool acquire) noexcept {
    auto it = owned.find(p);
    assert(it != owned.end());
    if (acquire) dense_bytes += it->second;
    else { assert(dense_bytes >= it->second); dense_bytes -= it->second; }
}
void* MapExecutableAlias(void* p, std::size_t size) noexcept {
    assert(owned.find(p) != owned.end());
    if (fail_alias) { errno = EACCES; return nullptr; }
    void* rx = mmap(nullptr, size, PROT_READ | PROT_EXEC,
                    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    return rx == MAP_FAILED ? nullptr : rx;
}
void* ReserveSparseJitCode(std::size_t, void**) noexcept {
    // Sparse is disabled in this regression; an accidental call is a bug.
    std::abort();
}
void ReleaseSparseJitCode(void*) noexcept { std::abort(); }
}
int main() {
    auto* allocator = EdenJitAllocator();
    Eden::Experimental::sparse_jit_cache.store(false);
    assert(!allocator->alloc(0));
    assert(!allocator->alloc(std::numeric_limits<std::size_t>::max()));
    assert(owned.empty() && dense_bytes == 0);

    // The old bug returned RW/NX memory when executable alias creation failed.
    for (int i = 0; i < 3; ++i) {
        fail_alias = true;
        const auto before = frees;
        errno = 0;
        assert(allocator->alloc(4096u << i) == nullptr);
        assert(errno == EACCES);
        assert(frees == before + 1);
        assert(owned.empty() && dense_bytes == 0);
    }
    fail_alias = false;
    fail_direct = true;
    assert(allocator->alloc(4096) == nullptr);
    assert(owned.empty() && dense_bytes == 0);
    fail_direct = false;

    // A successful alias has distinct RW and RX pointers, and both owners
    // are discarded on allocator.free rather than leaked over game restarts.
    for (std::size_t size : {4096u, 65536u, 4u * 1024u * 1024u}) {
        auto* rx = allocator->alloc(size);
        assert(rx);
        auto* rw = allocator->writableAddress(rx);
        assert(rw && rw != rx && owned.find(rw) != owned.end());
        assert(dense_bytes >= size);
        allocator->free(rx);
        assert(owned.empty() && dense_bytes == 0);
    }
    allocator->free(nullptr);
    assert(owned.empty() && dense_bytes == 0);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-dense-jit-alias-") as folder:
    tmp = Path(folder)
    (tmp / "xbyak").mkdir()
    (tmp / "xbyak" / "xbyak.h").write_text(XBYAK)
    src, exe = tmp / "test.cpp", tmp / "test"
    src.write_text(CPP)
    subprocess.run([CXX, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-DPS5_NATIVE=1", "-DEDEN_JIT_ALIAS_NATIVE=1",
                    "-I", str(tmp), "-I", str(ROOT / "headless"),
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS real PS5 dense JIT allocator: alias failure is fatal-to-attempt, no RW/NX fallback or owned-memory leak")
print("Firmware alias creation and native SDK: NOT TESTED")
