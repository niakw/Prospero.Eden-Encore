#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host exercise of the actual C++ owner-rollback function (NOT firmware ABI).

The heap C harness tests publication and accounting. This fixture extracts
the unmodified source function so the guard-before-physical-release ordering
is compiled and replayed, without a full SDK rebuild or local source edits.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
ps5 = (root / "src/memory_pages.cpp").read_text()
start = ps5.index("void RollbackUnpublishedHeapGrowth(")
end = ps5.index("void AbandonInitialHeapReservation(", start)
function = ps5[start:end]
assert "mmap(address, size, PROT_NONE, MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS" in function
assert function.index("if (guard != address) std::abort();") < function.index(
    "sceKernelReleaseDirectMemory(physical, size)")
compiler = next((item for item in ("clang++-18", "clang++", "g++") if shutil.which(item)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for real heap rollback helper host preflight")
prefix = r"""
#define _GNU_SOURCE
#include <cassert>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <sys/mman.h>
#include <unistd.h>
#include <cstdio>

namespace Common {
static constexpr std::size_t LargePage = 2u << 20;
static std::int64_t expected_physical = -1;
static std::size_t expected_size = 0;
static void* tracked_va = nullptr;
static unsigned physical_releases = 0;

static bool cpu_mapping_range(void* ptr, std::size_t bytes) {
    return ptr == tracked_va && bytes == expected_size;
}
static int sceKernelReleaseDirectMemory(std::int64_t owner, std::size_t bytes) {
    assert(owner == expected_physical && bytes == expected_size);
    // MAP_FIXED must have replaced the physical RW mapping with a fresh
    // inaccessible anonymous guard BEFORE releasing its simulated owner.
    unsigned char resident = 255;
    assert(mincore(tracked_va, 4096, &resident) == 0);
    assert((resident & 1) == 0);
    ++physical_releases;
    return 0;
}
"""
suffix = r"""
} // namespace Common
int main() {
    constexpr std::size_t reservation = 6u << 20;
    auto* base = static_cast<char*>(mmap(nullptr, reservation, PROT_NONE,
                                         MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    assert(base != MAP_FAILED);
    auto* middle = base + Common::LargePage;
    auto* rw = mmap(middle, Common::LargePage, PROT_READ | PROT_WRITE,
                    MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(rw == middle);
    reinterpret_cast<char*>(rw)[0] = 1;
    reinterpret_cast<char*>(rw)[Common::LargePage - 1] = 2;
    Common::tracked_va = rw;
    Common::expected_size = Common::LargePage;
    Common::expected_physical = 0x1234000;
    Common::RollbackUnpublishedHeapGrowth(rw, Common::LargePage,
                                           Common::expected_physical);
    assert(Common::physical_releases == 1);
    // The surrounding 3 GiB-reservation analogue must still exist and
    // retain its PROT_NONE guards; only the failed middle span was reset.
    for (auto* ptr : {base, base + Common::LargePage,
                      base + 2 * Common::LargePage}) {
        unsigned char resident = 255;
        assert(mincore(ptr, 4096, &resident) == 0);
        assert((resident & 1) == 0);
    }
    assert(munmap(base, reservation) == 0);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-heap-rollback-") as tmp:
    directory = Path(tmp)
    source, executable = directory / "rollback.cpp", directory / "rollback"
    source.write_text(prefix + function + suffix)
    subprocess.run([compiler, "-std=c++20", "-DPS5_NATIVE=1",
                    "-O2", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print("PASS heap rollback source: direct backing only after guard, surrounding VA preserved")
print("PS5 kernel MAP_FIXED and physical release ABIs remain UNQUALIFIED on firmware")
