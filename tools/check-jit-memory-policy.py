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
            constexpr std::size_t physical_headers = 4 * kLargePage;
            assert(total64 + physical_headers <= plan.admission_budget_bytes);
            assert(total32 + physical_headers <= plan.admission_budget_bytes);
        }
        previous = plan;
    }

    // Near the admission threshold, never claim a grown plan until there
    // is enough memory for BOTH the baseline code and its physical headers.
    constexpr std::size_t baseline = 656ull * kMiB;
    constexpr std::size_t physical_headers = 4 * kLargePage;
    const auto threshold = (kHostReserve + 4 * (baseline + physical_headers)) / kLargePage * kLargePage;
    const auto borderline = ChooseJitMemoryPlan(false, true, threshold);
    assert(!borderline.expanded);
    assert(borderline.a64 == kA64Baseline);
    const auto slight_growth = ChooseJitMemoryPlan(false, true, threshold + 4 * kLargePage);
    if (slight_growth.expanded) {
        std::size_t total = 0;
        for (auto size : slight_growth.a64) total += size;
        assert(total + physical_headers <= slight_growth.admission_budget_bytes);
    }

    const auto seven = ChooseJitMemoryPlan(false, true, 7ull * 1024 * kMiB);
    assert(seven.a64[0] > 320u * kMiB);
    assert(seven.a64[1] > 256u * kMiB);
    assert(seven.a32[0] > 512u * kMiB);
    assert(seven.a32[1] > 64u * kMiB);

    // Once core 0 hits the single-arena addressing ceiling, guest JIT
    // capacity that would otherwise be wasted goes to cores 1-2. The
    // higher-capacity plan must STILL obey the unchanged physical budget.
    // Real crash trace, 8 October 2026: 11826 MiB largest free pool at
    // launch; old half-pool admission 4376 MiB dense JIT; >440 MiB direct
    // allocation failed later with just 38 MiB contiguous free.
    constexpr std::size_t crash_free = 11826ull * kMiB;
    const auto crash_prevention = ChooseJitMemoryPlan(false, true, crash_free);
    assert(crash_prevention.expanded);
    assert(crash_prevention.admission_budget_bytes < 2500ull * kMiB);
    assert(crash_prevention.admission_budget_bytes > 1800ull * kMiB);
    assert(crash_free - kHostReserve - crash_prevention.admission_budget_bytes >=
           ((crash_free - kHostReserve) * 3) / 4);
    for (const auto* arenas : {&crash_prevention.a64, &crash_prevention.a32}) {
        std::size_t dense = physical_headers;
        for (auto bytes : *arenas) dense += bytes;
        assert(dense <= crash_prevention.admission_budget_bytes);
    }
    // We still use ALL extra physical JIT capacity proportionally for all
    // titles rather than retaining an arbitrary per-game A/B/C ceiling.
    const auto ten = ChooseJitMemoryPlan(false, true, 10ull * 1024 * kMiB);
    const auto twelve = ChooseJitMemoryPlan(false, true, 12ull * 1024 * kMiB);
    assert(ten.a32[0] > seven.a32[0]);
    assert(twelve.a64[0] > ten.a64[0]);
    // Synthetic larger pools still exercise the Xbyak per-arena addressing
    // limit and redistribution of physical surplus to other guest workers.
    const auto twenty = ChooseJitMemoryPlan(false, true, 20ull * 1024 * kMiB);
    assert(twenty.a32[0] == kSingleArenaAddressingLimit);
    const auto twenty_growth = twenty.admission_budget_bytes - baseline - physical_headers;
    const auto twenty_original_core1 = std::size_t{kA32Baseline[1]} +
        ((twenty_growth / 4) / kLargePage) * kLargePage;
    assert(twenty.a32[1] > twenty_original_core1);
    assert(twenty.a64[0] == kSingleArenaAddressingLimit);
    assert(twenty.a64[1] <= kSingleArenaAddressingLimit);
    // Two-megabyte granularity regression: no single worker's allocation
    // may SHRINK because another worker just reached its memory ceiling.
    auto last = ChooseJitMemoryPlan(false, true, kHostReserve);
    for (std::size_t free = kHostReserve + kLargePage;
         free <= 15ull * 1024 * kMiB; free += kLargePage) {
        const auto plan = ChooseJitMemoryPlan(false, true, free);
        for (std::size_t i = 0; i < 4; ++i) {
            assert(plan.a64[i] >= last.a64[i]);
            assert(plan.a32[i] >= last.a32[i]);
            assert(plan.a64[i] <= kSingleArenaAddressingLimit);
            assert(plan.a32[i] <= kSingleArenaAddressingLimit);
        }
        if (plan.expanded) {
            std::size_t total64 = 0, total32 = 0;
            for (std::size_t i = 0; i < 4; ++i) {
                total64 += plan.a64[i];
                total32 += plan.a32[i];
            }
            assert(total64 + physical_headers <= plan.admission_budget_bytes);
            assert(total32 + physical_headers <= plan.admission_budget_bytes);
        }
        last = plan;
    }

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
