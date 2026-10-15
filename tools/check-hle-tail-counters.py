#!/usr/bin/env python3
"""Compile the actual bounded HLE telemetry and verify slow-tail attribution.

This is a host-only test. No console services or guest memory are exercised.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = r'''
#include "hle_counters.h"
#include <cassert>
#include <cstdint>
#include <memory>
#include <thread>
#include <vector>
using Eden::Performance::HleCounters;
int main() {
    auto samples = std::make_unique<HleCounters>();
    samples->Record("IHOSBinderDriver", 3u, -1);
    samples->Record("IHOSBinderDriver", 3u, 19'999'999);
    samples->Record("IHOSBinderDriver", 3u, 20'000'000);
    samples->Record("IHOSBinderDriver", 3u, 99'999'999);
    samples->Record("IHOSBinderDriver", 3u, 100'000'000);
    samples->Record("IHOSBinderDriver", 3u, 300'000'000);
    std::vector<std::thread> threads;
    for (int t = 0; t < 4; ++t)
        threads.emplace_back([&] {
            for (int i = 0; i < 125; ++i)
                samples->Record("IHOSBinderDriver", 3u, 100);
        });
    for (auto& t : threads) t.join();
    bool seen = false;
    unsigned rows = 0;
    samples->ForEachLatency([&](const char* name, unsigned cmd,
                               std::uint64_t calls, std::uint64_t ns,
                               std::uint64_t ge20, std::uint64_t ge100,
                               std::uint64_t max_ns) {
        ++rows;
        assert(std::string_view{name} == "IHOSBinderDriver");
        assert(cmd == 3u);
        assert(calls == 506u);
        assert(ns == 539'999'998u + 50'000u);
        assert(ge20 == 4u);
        assert(ge100 == 2u);
        assert(max_ns == 300'000'000u);
        seen = true;
    });
    assert(seen && rows == 1u && samples->OverflowCalls() == 0u);
    std::uint64_t old_calls = 0;
    samples->ForEach([&](const char*, unsigned, std::uint64_t calls, std::uint64_t) {
        old_calls += calls;
    });
    assert(old_calls == 506u);
}
'''
with tempfile.TemporaryDirectory(prefix="encore-hle-tail-") as folder:
    src = Path(folder) / "test.cpp"
    binary = Path(folder) / "test-hle"
    src.write_text(source, encoding="utf-8")
    compiler = os.environ.get("CXX", "c++")
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread",
                    "-I", str(root / "headless"), str(src), "-o", str(binary)],
                   check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: bounded per-service HLE >20ms/>100ms tail and maximum latency")
