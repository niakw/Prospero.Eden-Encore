#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the actual fixed HLE counters under 8 concurrent host producers.

The native PS5 guest HLE dispatch path still needs a firmware timing A/B:
this host unit checks bounded reporting, races, name lifetime and overflow.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "headless/performance.cpp").read_text()
assert '#include "hle_counters.h"' in source
hot = source.split("void RecordHle(", 1)[1].split("void ReportJitCodeState(", 1)[0]
assert "hle_calls.Record(service, command, ns);" in hot
assert "hle_mutex" not in hot and "std::map<" not in hot
assert "hle_calls.ForEach(" in source
assert "EDEN_DEV_HLE_OVERFLOW" in source

compiler = next((c for c in ("clang++-18", "clang++", "g++") if shutil.which(c)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for HLE contention source preflight")

fixture = r"""
#include "hle_counters.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <latch>
#include <string>
#include <unordered_set>
#include <thread>
#include <vector>

int main() {
    using Eden::Performance::HleCounters;
    HleCounters counters;
    constexpr unsigned threads = 8;
    constexpr unsigned operations = 24000;
    constexpr std::array names{"IFileSystem", "IFile", "nvdrv"};
    std::latch go(threads);
    std::vector<std::thread> pool;
    for (unsigned tid = 0; tid < threads; ++tid)
        pool.emplace_back([&, tid] {
            go.arrive_and_wait();
            for (unsigned n = 0; n < operations; ++n)
                counters.Record(names[(tid + n) % names.size()], n % 11u, 2500);
        });
    for (auto& thread : pool) thread.join();

    char recycled[80] = "old-session-service";
    counters.Record(recycled, 123u, 1000000);
    std::strcpy(recycled, "new-session-service");
    counters.Record(recycled, 123u, 1000000);
    std::uint64_t calls = 0, ns = 0;
    unsigned old_names = 0, new_names = 0;
    std::unordered_set<std::string> identities;
    counters.ForEach([&](const char* name, unsigned cmd, std::uint64_t c, std::uint64_t duration) {
        assert(identities.insert(std::string(name) + "#" + std::to_string(cmd)).second);
        calls += c; ns += duration;
        if (std::strcmp(name, "old-session-service") == 0 && cmd == 123u) {
            assert(c == 1); ++old_names;
        }
        if (std::strcmp(name, "new-session-service") == 0 && cmd == 123u) {
            assert(c == 1); ++new_names;
        }
    });
    assert(calls == threads * operations + 2);
    assert(ns == threads * operations * 2500ull + 2000000ull);
    assert(old_names == 1 && new_names == 1);
    assert(identities.size() == 35); // 3 service names x 11 commands, plus 2 recycled names
    assert(counters.OverflowCalls() == 0);

    // A flooded table must not allocate memory or spin forever.
    HleCounters saturated;
    for (unsigned n = 0; n < HleCounters::kCapacity + 3; ++n) {
        char name[80];
        std::snprintf(name, sizeof(name), "unique-service-%u", n);
        saturated.Record(name, n, 5);
    }
    assert(saturated.OverflowCalls() == 3);
    assert(saturated.OverflowNs() == 15);
    std::uint64_t admitted = 0;
    saturated.ForEach([&](const char*, unsigned, std::uint64_t c, std::uint64_t) {
        admitted += c;
    });
    assert(admitted == HleCounters::kCapacity);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-hle-counters-") as folder:
    source_path = Path(folder) / "hle_test.cpp"
    binary = Path(folder) / "hle_test"
    source_path.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", "-Wall", "-Wextra",
                    "-Werror", "-I", str(root / "headless"),
                    str(source_path), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=35)
print("PASS: 8-thread HLE counters, identical-name pooling, owned names and bounded overflow")
print("PS5 console HLE latency/FPS impact remains UNMEASURED")
