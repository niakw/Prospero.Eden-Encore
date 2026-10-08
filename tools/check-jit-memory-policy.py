#!/usr/bin/env python3
"""Compile and exercise the shared A64/A32 PS5 JIT budget on the host.

This is a tiny host C++20 unit fixture, NOT a PS5 native build or hardware
performance test. CI can run it before preparing the costly pinned source.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
compiler = next((x for x in ("clang++-18", "clang++", "g++")
                 if shutil.which(x)), None)
if compiler is None:
    raise SystemExit("Missing C++20 compiler for mandatory host policy gate")

code = r"""
#include <cassert>
#include <cstdint>
#include <limits>
#include "experimental_performance.h"

using namespace Eden::Experimental;

int main() {
    const auto reference = ChooseJitMemoryPlan(false, false, 0);
    assert(reference.a64 == kA64Baseline);
    assert(reference.a32 == kA32Baseline);
    assert(!reference.expanded);
    const auto safe = ChooseJitMemoryPlan(true, true, 10ull * 1024 * kMiB);
    assert(safe.a64 == kA64Baseline && safe.a32 == kA32Baseline);

    auto previous = reference;
    for (std::size_t gib = 1; gib <= 15; ++gib) {
        auto plan = ChooseJitMemoryPlan(false, true, gib * 1024 * kMiB);
        for (std::size_t core = 0; core != 4; ++core) {
            assert(plan.a64[core] >= previous.a64[core]);
            assert(plan.a32[core] >= previous.a32[core]);
            assert(plan.a64[core] % kLargePage == 0);
            assert(plan.a32[core] % kLargePage == 0);
            assert(plan.a64[core] <= kSingleArenaAddressingLimit);
            assert(plan.a32[core] <= kSingleArenaAddressingLimit);
        }
        assert(plan.a64[3] == 16u * kMiB);
        assert(plan.a32[3] == 16u * kMiB);
        if (plan.expanded) {
            std::size_t total64 = 0;
            std::size_t total32 = 0;
            for (std::size_t i = 0; i != 4; ++i) {
                total64 += plan.a64[i];
                total32 += plan.a32[i];
            }
            // Entire actual per-ISA arenas (including core 3) must fit
            // inside the admitted budget, not exceed it by 16 MiB.
            assert(total64 <= plan.admission_budget_bytes);
            assert(total32 <= plan.admission_budget_bytes);
        }
        previous = plan;
    }

    const auto seven = ChooseJitMemoryPlan(false, true, 7ull * 1024 * kMiB);
    assert(seven.a64[0] > 320u * kMiB);
    assert(seven.a64[1] > 256u * kMiB);
    assert(seven.a32[0] > 512u * kMiB);
    assert(seven.a32[1] > 64u * kMiB);

    const auto huge = ChooseJitMemoryPlan(false, true,
                                          std::numeric_limits<std::size_t>::max());
    assert(huge.a64[0] <= kSingleArenaAddressingLimit);
    assert(huge.a32[0] <= kSingleArenaAddressingLimit);

    ApplyJitMemoryPlan(seven);
    for (std::size_t core = 0; core < 4; ++core) {
        assert(A64CacheBytes(core, 0) == seven.a64[core]);
        assert(A32CacheBytes(core, 0) == seven.a32[core]);
    }
    ApplyJitMemoryPlan(safe);
    assert(A64CacheBytes(0, 0) == kA64Baseline[0]);
    assert(A32CacheBytes(0, 0) == kA32Baseline[0]);
    assert(A64CacheBytes(7, 1234u) == 1234u);
    assert(A32CacheBytes(7, 1234u) == 1234u);
}
"""

with tempfile.TemporaryDirectory(prefix="eden-jit-policy-") as tmp:
    source, binary = Path(tmp) / "main.cpp", Path(tmp) / "jit-memory-test"
    source.write_text(code)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-I", str(root / "headless"),
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

print("PASS shared JIT memory policy: all-title A64/A32 monotonicity, guard, alignment, reset")
print("PS5 native compilation / runtime: NOT TESTED")
