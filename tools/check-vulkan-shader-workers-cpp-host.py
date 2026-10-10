#!/usr/bin/env python3
"""Execute the exact generated Vulkan shader worker admission policy on host.

Extracts the C++ replacement from prepare-vulkan-port.py (rather than
reimplementing the policy), replacing only the hardware concurrency hint with
a deterministic mock. Tests 13 eligible primary+secondary CPUs and 8 secondary
slots independently of the eight-thread sanitizer tests. This is NOT a PS5
native build and makes no claim about actual console CPU affinity.
"""
from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
generator = root / "tools/prepare-vulkan-port.py"
tree = ast.parse(generator.read_text(encoding="utf-8"), filename=str(generator))
matches = [
    node.value.value
    for node in tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "pipeline_worker_replacement"
            for t in node.targets)
    and isinstance(node.value, ast.Constant)
    and isinstance(node.value.value, str)
]
assert len(matches) == 1, "missing precisely one generated shader worker policy"
policy = matches[0]
assert policy.startswith("#ifdef PS5_NATIVE\n")
assert policy.endswith("\n}")
assert policy.count("std::thread::hardware_concurrency()") == 1
assert "const size_t schedulable = available ? available : std::min<size_t>(reported, 4);" in policy
assert "const size_t reported" in policy
assert "constexpr size_t max_pipeline_workers = 6;" in policy
assert "PinnedWorkerMask()" in policy and "VerifiedSecondaryPlacementMask()" in policy
# Substitute the configurable hint *only* for deterministic host testing.
policy = policy.replace("std::thread::hardware_concurrency()", "MockReported()")

prefix = r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <thread>
using cpuset_t = std::uint64_t;
#define CPU_LEVEL_WHICH 1
#define CPU_WHICH_TID 1
#define CPU_ISSET(cpu,ptr) (((*(ptr)) >> (cpu)) & 1ULL)
static std::uint64_t allowed_mask = 0;
static std::uint64_t primary_mask = 0;
static std::uint64_t secondary_mask = 0;
static unsigned reported_hint = 16;
static int affinity_failure = 0;
static unsigned MockReported() { return reported_hint; }
static int cpuset_getaffinity(int, int, int, std::size_t length, cpuset_t *out) {
    assert(length == 8 && out != nullptr);
    *out = allowed_mask;
    return affinity_failure;
}
namespace Eden::Performance {
std::uint64_t PinnedWorkerMask() { return ::primary_mask; }
std::uint64_t VerifiedSecondaryPlacementMask() { return ::secondary_mask; }
}
static std::size_t ActualShaderWorkerPolicy(std::size_t max_core_threads) {
    (void)max_core_threads;
#ifndef ANDROID
"""
suffix = r"""
int main() {
    constexpr std::uint64_t full13 = (1ULL << 13) - 1;
    constexpr std::uint64_t primary5 = 0x1F;
    constexpr std::uint64_t secondary8 = full13 & ~primary5;
    assert(__builtin_popcountll(full13) == 13);
    assert(__builtin_popcountll(secondary8) == 8);

    primary_mask = primary5;
    secondary_mask = 0;
    allowed_mask = full13;
    reported_hint = 16;
    affinity_failure = 0;
    assert(ActualShaderWorkerPolicy(8) == 6);

    allowed_mask = secondary8; // shader thread has *already* excluded primary
    assert(ActualShaderWorkerPolicy(8) == 6);

    reported_hint = 4; // hardware_concurrency is a hint, not a CPU mask
    assert(ActualShaderWorkerPolicy(8) == 6);
    reported_hint = 2;
    assert(ActualShaderWorkerPolicy(8) == 6);

    primary_mask = 0;
    secondary_mask = secondary8;
    reported_hint = 16;
    assert(ActualShaderWorkerPolicy(8) == 6); // verified logical-only split

    secondary_mask = 0;  // no isolation evidence
    assert(ActualShaderWorkerPolicy(8) == 1); // fail conservatively
    affinity_failure = -1;
    assert(ActualShaderWorkerPolicy(8) == 1);
    affinity_failure = 0;

    allowed_mask = (std::uint64_t{1} << 8) - 1;
    primary_mask = 0x3; // two primaries are actually in the shader mask
    assert(ActualShaderWorkerPolicy(8) == 4); // 8 - (2 + 2)
    allowed_mask = 0;
    primary_mask = 0;
    assert(ActualShaderWorkerPolicy(8) == 1);

    allowed_mask = full13;
    reported_hint = 16;
    primary_mask = primary5;
    assert(ActualShaderWorkerPolicy(8) == 6);
    std::puts("PASS actual generated shader worker admission: 16 hardware, 13 allowed, 8 secondary, 6 builders");
}
"""
compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if compiler is None:
    raise SystemExit("Missing host C++20 compiler; refusing source-only PASS")
with tempfile.TemporaryDirectory(prefix="eden-shader-worker-policy-") as dirname:
    file = Path(dirname) / "shader-workers.cpp"
    exe = Path(dirname) / "shader-workers"
    file.write_text(prefix + policy + "\n" + suffix, encoding="utf-8")
    subprocess.run([compiler, "-std=c++20", "-DPS5_NATIVE=1", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(file), "-o", str(exe)], check=True, timeout=90)
    subprocess.run([str(exe)], check=True, timeout=90)
print("Native PS5 CPU mask still requires console log confirmation")
