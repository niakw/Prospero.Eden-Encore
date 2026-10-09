#!/usr/bin/env python3
"""Regression: sparse virtual capacity persists, physical demand stays sparse.

R237 measured the largest DIRECT-memory extent drop from 11,824 MiB to
4,128 MiB across relaunch, shrinking the VIRTUAL JIT arena 2,176 -> 656 MiB.
Only verified sparse RX/RW dual-mapped allocations may retain the earlier
largest verified extent. Dense physical arenas ALWAYS plan from current RAM.
Staged only; no execution without explicit user authorization.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
policy = (root / "headless/experimental_performance.h").read_text()
boot = (root / "headless/main.cpp").read_text()
allocator = (root / "headless/jit-allocator.h").read_text()
ps5 = (root / "src/memory_pages.cpp").read_text()
assert "ChooseSparseVirtualJitPlan(" in policy
assert "current_largest_free <= kHostReserve" in policy
assert "if (safe_launch || !memory_known" in policy
assert "ChooseJitMemoryPlan(false, true, verified_lifetime_peak)" in policy
assert "static std::size_t verified_sparse_peak_extent = 0;" in boot
assert "if (experimental_sparse_jit && jit_memory_known && !safe_launch)" in boot
assert "verified_sparse_peak_extent = std::max(" in boot
assert "jit_plan = Eden::Experimental::ChooseSparseVirtualJitPlan(" in boot
assert "Eden::Experimental::ApplyJitMemoryPlan(jit_plan)" in boot
assert "physical_policy=demand_pages" in boot
assert "Common::ProbeSparseJitAlias()" in boot
assert "ReserveSparseJitCode(sparse_span, &writable)" in allocator
assert "return nullptr;" in allocator.split("EDEN_JIT_SPARSE_RESERVE_FAILED", 1)[1]
assert "region.committed += LargePage;" in ps5
assert "sparse_jit_committed += LargePage;" in ps5
assert "sparse_jit_committed -= region.committed;" in ps5
# PS5 native kernel APIs can return a mapping whose first address is inside
# the CPU window while the complete range crosses the GPU-reserved high VA.
# All dense pages, dense executable aliases and sparse zero-page scratch
# must validate the whole mapped extent, then relinquish valid unexpected
# aliases BEFORE releasing direct physical backing.
dense_pages = ps5.split("void* AllocateMemoryPages(", 1)[1].split("#ifdef PS5_NATIVE\n// Direct-memory start", 1)[0]
dense_alias = ps5.split("void* MapExecutableAlias(", 1)[1].split("#endif", 1)[0]
zero_page = ps5.split("bool ZeroedBlock(", 1)[1].split("bool MapSlot(", 1)[0]
assert "cpu_mapping_range(base, total)" in dense_pages
assert "cpu_mapping_range(alias, span)" in dense_alias
assert "cpu_mapping_range(view, SparseSlot)" in zero_page
assert "munmap(view, SparseSlot)" in zero_page
assert "sceKernelReleaseDirectMemory(*physical, SparseSlot)" in zero_page
table_slot = ps5.split("bool MapSlot(", 1)[1].split("#endif", 1)[0]
assert "const auto rc = sceKernelMapDirectMemory(&address, SparseSlot, protection," in table_slot
assert "if (address != reinterpret_cast<void*>(at))" in table_slot
assert "if (rc != 0 || !address || address == MAP_FAILED) std::abort();" in table_slot
assert "if (munmap(address, SparseSlot) != 0) std::abort();" in table_slot
assert "return rc == 0;" in table_slot

cxx = next((e for e in ("clang++-18", "clang++", "g++") if shutil.which(e)), None)
if not cxx: raise SystemExit("Need C++20 compiler for sparse policy test")
code = r"""
#include "experimental_performance.h"
#include <cassert>
using namespace Eden::Experimental;
constexpr auto small_dense = ChooseJitMemoryPlan(false, true, 4128ull*kMiB);
constexpr auto large_dense = ChooseJitMemoryPlan(false, true, 11824ull*kMiB);
constexpr auto second_sparse = ChooseSparseVirtualJitPlan(false, true, 4128ull*kMiB, 11824ull*kMiB);
static_assert(small_dense.a64 == kA64Baseline);
static_assert(large_dense.expanded && second_sparse.expanded);
static_assert(second_sparse.a64 == large_dense.a64);
static_assert(second_sparse.a32 == large_dense.a32);
static_assert(second_sparse.a64[0] <= kSingleArenaAddressingLimit);
static_assert(ChooseSparseVirtualJitPlan(false, true, 4128ull*kMiB, 4128ull*kMiB).a64 == kA64Baseline);
static_assert(ChooseSparseVirtualJitPlan(false, true, 2500ull*kMiB, 11824ull*kMiB).a64 == kA64Baseline);
static_assert(ChooseSparseVirtualJitPlan(true, true, 4128ull*kMiB, 11824ull*kMiB).a64 == kA64Baseline);
static_assert(ChooseSparseVirtualJitPlan(false, false, 4128ull*kMiB, 11824ull*kMiB).a64 == kA64Baseline);
int main() { assert(second_sparse.admission_budget_bytes == large_dense.admission_budget_bytes); }
"""
with tempfile.TemporaryDirectory(prefix="eden-sparse-virtual-policy-") as work:
    source, exe = Path(work) / "probe.cpp", Path(work) / "probe"
    source.write_text(code)
    subprocess.run([cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root / "headless"), str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS C++ sparse-only virtual JIT highwater retention; dense and unknown/safe RAM unchanged")
print("NO PROOF of new physical memory headroom or safe live JIT block reclamation")
