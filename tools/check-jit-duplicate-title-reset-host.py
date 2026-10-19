#!/usr/bin/env python3
"""Host C++ regression for DEV JIT duplicate history across guest title changes.

Compiles the actual class extracted from the maintained performance unit. Verifies that the native
frontend calls reset after previous guest workers joined. No PS5 benchmark.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE = (ROOT / "headless/performance.cpp").read_text()
DECL = (ROOT / "headless/performance.h").read_text()
MAIN = (ROOT / "headless/main.cpp").read_text()
begin = PERFORMANCE.rfind("namespace Eden::Performance {", 0, PERFORMANCE.index("class JitDuplicateHistory final {"))
end = PERFORMANCE.index("} // namespace Eden::Performance", begin) + len("} // namespace Eden::Performance")
CLASS = PERFORMANCE[begin:end]
assert "#ifdef EDEN_DEV_PROFILE\\nnamespace Eden::Performance" not in CLASS
assert 'void Eden::Performance::ResetJitDuplicateTrackingForTitle() noexcept {' in PERFORMANCE
assert 'JitHistory().Reset();' in PERFORMANCE
assert 'JitHistory().Record(core, location,' in PERFORMANCE
assert 'jit_duplicates[core][index].fetch_add(1, std::memory_order_relaxed);' in PERFORMANCE
assert 'void ResetJitDuplicateTrackingForTitle() noexcept;' in DECL
before = MAIN.index('Eden::Performance::ResetDirectMemoryProbeForTitle();')
after = MAIN.index('Eden::Performance::ResetJitDuplicateTrackingForTitle();', before)
assert before < after < MAIN.index('Eden::Display::output_width.store(', after)
assert MAIN.count("Eden::Performance::ResetJitDuplicateTrackingForTitle();") == 1
assert 'jit_duplicate_tracking.store(false, std::memory_order_relaxed)' in MAIN
assert 'entry == "jit_dups=on"' in MAIN

CPP = r"""
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <unordered_map>
#include <cassert>
#include <atomic>
#include <thread>
#include <vector>
INJECT_CLASS
using Eden::Performance::JitDuplicateHistory;

int main() {
    JitDuplicateHistory tracker;
    tracker.Reset(); // Must not allocate any buckets on an unused title.
    assert(tracker.BucketsForHostTest() <= 2);
    constexpr unsigned long long kLocation = 0x1000;
    assert(tracker.Record(0, kLocation, 1000) == 0);  // first block in title A
    const auto initial_buckets = tracker.BucketsForHostTest();
    assert(initial_buckets >= 16384 && initial_buckets < 65536);
    assert(tracker.Record(0, kLocation, 2000) == 1);  // repeat within title A
    assert(tracker.Record(1, kLocation, 3000) == 2);  // second guest core
    assert(tracker.Record(2, kLocation + 4, 4000) == 0);
    tracker.Reset(); // title B may use exactly the same virtual addresses
    assert(tracker.BucketsForHostTest() <= 2); // no retained large hash table
    assert(tracker.Record(0, kLocation, 5000) == 0);
    assert(tracker.Record(1, kLocation, 6000) == 2);
    assert(tracker.Record(2, kLocation + 4, 7000) == 0);

    // Separate guest cores can share a title without losing first-owner status.
    tracker.Reset();
    constexpr unsigned kThreads = 4;
    std::atomic<unsigned> first{};
    std::atomic<unsigned> other{};
    std::vector<std::thread> workers;
    for (unsigned core = 0; core < kThreads; ++core) {
        workers.emplace_back([&, core] {
            unsigned bucket = tracker.Record(core, kLocation, 10000 + core);
            if (bucket == 0) ++first;
            else if (bucket >= 2 && bucket <= 7) ++other;
            else assert(false);
        });
    }
    for (auto& worker : workers) worker.join();
    assert(first == 1 && other == 3);
    tracker.Reset(); // joined workers; no stale owner in subsequent title
    assert(tracker.BucketsForHostTest() <= 2);
    assert(tracker.Record(0, kLocation, 20000) == 0);
    // A very large diagnostic session can still grow without a hard cap,
    // and the following title must relinquish that peak capacity.
    for (unsigned i = 0; i < 50000; ++i)
        assert(tracker.Record(0, kLocation + 0x10000ULL + i, 30000 + i) == 0);
    assert(tracker.BucketsForHostTest() > initial_buckets);
    tracker.Reset();
    assert(tracker.BucketsForHostTest() <= 2);
    assert(tracker.Record(0, kLocation, 80000) == 0);
    assert(tracker.BucketsForHostTest() < 65536);
}
"""
compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-jit-title-reset-") as tmp:
    source = Path(tmp) / "witness.cpp"
    binary = Path(tmp) / "witness"
    source.write_text(CPP.replace("INJECT_CLASS", CLASS))
    subprocess.run(
        [compiler, "-std=c++20", "-O1", "-pthread", "-Wall", "-Wextra",
         "-DEDEN_JIT_DUP_HISTORY_HOST_TEST=1",
         "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
         "-I", str(ROOT / "headless"), str(source), "-o", str(binary)],
        check=True, capture_output=True, text=True, timeout=70)
    for _ in range(2):
        done = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, (done.returncode, done.stdout[-700:], done.stderr[-1000:])
print("ENCORE_JIT_DUPLICATE_TITLE_RESET_PASS session_isolation=1 concurrency=1 sanitized=1 wiring=1 bucket_lifecycle=1")
