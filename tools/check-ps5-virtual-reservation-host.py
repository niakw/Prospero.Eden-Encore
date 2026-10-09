#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-extracted CPU virtual-range reservation ownership replay (host only).

Exercises the *actual* wrapper against mocked Sony reserve APIs and real host
mmap/munmap. The PS5 firmware error-output contract remains UNQUALIFIED.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "src/memory_pages.cpp").read_text()
start = native.index("void* ReserveCpuVirtualRange(")
end = native.index("} // namespace", start)
helper = native[start:end]
assert "sceKernelReserveVirtualRange(&address, bytes, 0, alignment)" in helper
assert "if (address != reinterpret_cast<void*>(cpu_mapping_hint)) std::abort();" in helper
assert "if (!cpu_mapping_range(address, bytes))" in helper
assert "munmap(address, bytes) != 0" in helper
compiler = next((name for name in ("clang++-18", "clang++", "g++") if shutil.which(name)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for PS5 VA reservation host gate")

prefix = r"""
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include <cassert>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <csignal>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {
constexpr std::uintptr_t cpu_mapping_hint = 0x1000000000ull;
static int reserve_scenario = 0;
static void* last_mapping = nullptr;
static bool cpu_mapping_range(void* address, std::size_t bytes) {
    return reserve_scenario != 3 && address != nullptr && address != MAP_FAILED &&
           bytes == (2u << 20);
}
static int sceKernelReserveVirtualRange(void** address, std::size_t bytes,
                                         int flags, std::size_t align) {
    assert(address && flags == 0 && bytes == (2u << 20) && align == bytes);
    if (reserve_scenario == 1) return -1; // expected normal unchanged hint
    last_mapping = mmap(nullptr, bytes, PROT_NONE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(last_mapping != MAP_FAILED);
    *address = last_mapping;
    return reserve_scenario == 2 ? -1 : 0; // failed but mutated output
}
"""
tail = r"""
} // namespace

int main() {
    constexpr std::size_t page = 2u << 20;
    reserve_scenario = 1;
    assert(ReserveCpuVirtualRange(page, page) == nullptr);
    reserve_scenario = 0;
    void* owned = ReserveCpuVirtualRange(page, page);
    assert(owned && owned == last_mapping);
    assert(munmap(owned, page) == 0);
    // Successful non-CPU-window VA must be released before rejecting it.
    reserve_scenario = 3;
    assert(ReserveCpuVirtualRange(page, page) == nullptr);
    unsigned char resident = 0;
    errno = 0;
    assert(mincore(last_mapping, 4096, &resident) != 0 && errno == ENOMEM);
    // Failed reserve that mutates the output cannot prove alias ownership:
    // fail closed instead of continuing with uncertain address-space state.
    const pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        rlimit no_dump{0, 0};
        (void)setrlimit(RLIMIT_CORE, &no_dump);
        reserve_scenario = 2;
        (void)ReserveCpuVirtualRange(page, page);
        _exit(77); // abort expected
    }
    int status = 0;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-ps5-va-") as temporary:
    folder = Path(temporary)
    src, exe = folder / "va.cpp", folder / "va"
    src.write_text(prefix + helper + tail)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: source-extracted native VA wrapper accepts valid ranges, rejects normal failures, cleans invalid addresses, aborts on mutated errors")
print("PS5 firmware VA ABI and real CPU window remain UNTESTED")
