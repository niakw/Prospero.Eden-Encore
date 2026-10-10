#!/usr/bin/env python3
"""Compile the ACTUAL production GPU atomic_ref helpers in a C++20 host race fixture.

Extracts six method bodies added to the pinned device_memory_manager.h
overlay, compiles them with ASan/UBSan, and runs a concurrent-reader/writer
test. This tests the exact helpers, not a standalone hand-copied approximation.
TSan is also exercised on supported Linux CI; no PS5 SDK/native build.
"""
from __future__ import annotations

from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
patch = (root / "headless/backports/eden-ps5-gpu-atomic-forward-table.patch").read_text()
lines = patch.splitlines()
start = next(i for i, line in enumerate(lines)
             if line.startswith("+    static u32 AtomicLoadPhysical("))
methods = []
seen_last = False
for line in lines[start:]:
    if line.startswith("+"):
        methods.append(line[1:])
        if "static void AtomicStoreBacking(" in line:
            seen_last = True
    elif seen_last:
        break
    else:
        raise AssertionError("non-contiguous production GPU atomic helpers")
body = "\n".join(methods)
for name in ("AtomicLoadPhysical", "AtomicStorePhysical",
             "AtomicLoadContinuity", "AtomicStoreContinuity",
             "AtomicLoadBacking", "AtomicStoreBacking"):
    assert f"{name}(" in body, name
assert body.count("std::atomic_ref<") == 6
# The reverse lookup is also compiled inline from other translation units.
# Extract the exact two scalar-slot helpers from their own ordered patch.
reverse_lines = (root / "headless/backports/eden-ps5-gpu-atomic-reverse-table.patch").read_text().splitlines()
reverse_start = next(i for i, line in enumerate(reverse_lines)
                     if line.startswith("+    static u32 AtomicLoadReverse("))
reverse_methods = []
last_reverse = False
for line in reverse_lines[reverse_start:]:
    if line.startswith("+"):
        reverse_methods.append(line[1:])
        if "static void AtomicStoreReverse(" in line:
            last_reverse = True
    elif last_reverse:
        break
    else:
        raise AssertionError("non-contiguous reverse GPU atomic helpers")
reverse_body = "\n".join(reverse_methods)
assert reverse_body.count("std::atomic_ref<") == 2
assert reverse_body.rstrip().endswith("}")
assert "#ifdef PS5_NATIVE" not in reverse_body
assert "#ifdef PS5_NATIVE" not in body
assert "#else" not in body
assert "#endif" not in body
# All translation units must use the same atomic helpers, even if the
# PS5_NATIVE define is scoped to a single GPU manager source file.
assert body.rstrip().endswith("}")
assert "+    void InsertCPUBacking(size_t page_index" in patch
assert "+    constexpr void InsertCPUBacking" not in patch
source = """\
#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <thread>
#include <type_traits>
#include <vector>
using u32 = std::uint32_t;
using VAddr = std::uint64_t;
struct Harness {
    struct TrackedEntry {
        VAddr cpu_backing_address;
        u32 continuity_tracker;
        u32 compressed_physical_ptr;
    };
    static_assert(sizeof(TrackedEntry) == 16);
    static_assert(std::is_trivially_copyable_v<TrackedEntry>);
""" + body + "\n" + reverse_body + """
};
int main() {
    Harness::TrackedEntry entry{};
    u32 reverse_slot{};
    constexpr int iterations = 60000;
    std::vector<std::thread> workers;
    for (int writer = 0; writer < 3; ++writer) {
        workers.emplace_back([&, writer] {
            for (int i = 0; i < iterations; ++i) {
                auto value = static_cast<u32>((i + writer) & 65535);
                Harness::AtomicStorePhysical(entry, value);
                Harness::AtomicStoreContinuity(entry, value);
                Harness::AtomicStoreBacking(entry, static_cast<VAddr>(value));
                Harness::AtomicStoreReverse(reverse_slot, value);
            }
        });
    }
    for (int reader = 0; reader < 5; ++reader) {
        workers.emplace_back([&] {
            for (int i = 0; i < iterations; ++i) {
                assert(Harness::AtomicLoadPhysical(entry) <= 65535);
                assert(Harness::AtomicLoadContinuity(entry) <= 65535);
                assert(Harness::AtomicLoadBacking(entry) <= 65535);
                assert(Harness::AtomicLoadReverse(reverse_slot) <= 65535);
            }
        });
    }
    for (auto& thread : workers) thread.join();
    std::cout << "PASS exact PS5 GPU atomic_ref forward table: 8 threads, "
              << iterations << " operations/thread\\n";
}
"""
compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if compiler is None:
    raise SystemExit("C++20 compiler missing; refusing a false source-only PASS")
with tempfile.TemporaryDirectory(prefix="eden-gpu-atomic-host-") as dirname:
    folder = Path(dirname)
    file = folder / "atomic.cpp"
    file.write_text(source, encoding="utf-8")
    asan = folder / "gpu-atomic-asan"
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-DPS5_NATIVE=1",
                    "-pthread", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(file), "-o", str(asan)], check=True, timeout=90)
    subprocess.run([str(asan)], check=True, timeout=90)
    if platform.system() == "Linux" and platform.machine() in ("x86_64", "aarch64"):
        tsan = folder / "gpu-atomic-tsan"
        subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-DPS5_NATIVE=1",
                        "-pthread", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=thread", "-fno-sanitize-recover=all",
                        str(file), "-o", str(tsan)], check=True, timeout=90)
        subprocess.run([str(tsan)], check=True, timeout=180)
print("Host C++20 forward+reverse atomic_ref accessors verified; GPU remap transactions unqualified")
