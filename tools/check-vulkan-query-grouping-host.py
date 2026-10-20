#!/usr/bin/env python3
"""Prove query page coverage/redirects and count grouping comparisons on host."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp").read_text()
method = source.split("void QueryCacheRuntime::SyncValues(", 1)[1]
start, end = "    impl->redirect_cache.clear();", "    // ObtainCPUBuffer takes a u32 length."
active = start + method.split(start, 1)[1].split(end, 1)[0]
baseline = (ROOT / "tools/fixtures/query-sync-linear-grouping.inc").read_text()
# Count the real sort predicate and the former group probes, without replacing
# either algorithm. The remaining query-copy loops must retain original order.
compare = "return Common::AlignDown(values[a].address, Core::DEVICE_PAGESIZE) <"
assert active.count(compare) == 1
active = active.replace(compare, "++comparisons; " + compare)
probe = "            auto& loc = impl->little_cache[i];"
assert baseline.count(probe) == 1
baseline = baseline.replace(probe, "            ++comparisons;\n" + probe)
assert method.count("for (size_t i = 0; i < values.size(); ++i)") == 2
for workflow in ("encore-core-preflight.yml", "encore-core-fast-gate.yml"):
    assert "python3 -B tools/check-vulkan-query-grouping-host.py" in (
        ROOT / ".github/workflows" / workflow).read_text()

cpp = r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <numeric>
#include <random>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>
using DAddr = std::uint64_t;
using u32 = std::uint32_t;
namespace Core { constexpr DAddr DEVICE_PAGESIZE = 4096; }
namespace Common { DAddr AlignDown(DAddr n, DAddr a) { return n - n % a; } }
struct Value { DAddr address; std::size_t size; };
struct Impl {
    std::vector<std::size_t> redirect_cache, sync_order;
    std::vector<std::pair<DAddr, DAddr>> little_cache;
};
struct Plan {
    Impl data;
    Impl* impl = &data;
    std::size_t comparisons = 0;
    void Before(std::span<const Value> values) {
BASELINE
        (void)total_size;
    }
    void After(std::span<const Value> values) {
ACTIVE
        (void)total_size;
    }
};
void Verify(const Plan& plan, const std::vector<Value>& values) {
    const auto& ranges = plan.data.little_cache;
    assert(plan.data.redirect_cache.size() == values.size());
    std::size_t pages = 0;
    for (const auto& value : values)
        pages = std::max(pages, std::size_t((value.address + value.size - 1) / 4096 + 1));
    std::vector<unsigned> expected(pages), actual(pages);
    for (std::size_t i = 0; i < values.size(); ++i) {
        const auto& value = values[i];
        const auto group = plan.data.redirect_cache[i];
        assert(group < ranges.size());
        assert(ranges[group].first <= value.address);
        assert(ranges[group].second >= value.address + value.size);
        for (auto p = value.address / 4096; p <= (value.address + value.size - 1) / 4096; ++p)
            expected[p] = 1;
    }
    for (std::size_t i = 0; i < ranges.size(); ++i) {
        const auto& [begin, end] = ranges[i];
        assert(begin < end && begin % 4096 == 0 && end % 4096 == 0);
        if (i) assert(ranges[i - 1].second < begin);
        for (auto p = begin / 4096; p < end / 4096; ++p) {
            assert(p < actual.size());
            ++actual[p];
        }
    }
    assert(actual == expected); // no dropped pages, gaps introduced or overlap
}
int main() {
    Plan old, current;
    std::vector<Value> separated;
    for (unsigned i = 0; i < 1024; ++i) separated.push_back({8192ULL * i, 8});
    old.Before(separated);
    assert(old.comparisons == 1024 * 1023 / 2);
    current.After(separated);
    Verify(current, separated);
    assert(current.comparisons < old.comparisons / 8);
    assert(current.comparisons == 1023);
    const auto comparisons = current.comparisons;
    // A crossing result connects existing page 0 and page 2 groups. Results
    // themselves are disjoint; this exercises page-span coalescing only.
    const std::vector<Value> bridge{{0, 8}, {8192 + 8, 8}, {8192 - 4, 8}};
    old.Before(bridge);
    assert(old.data.little_cache.size() == 2);
    current.After(bridge);
    Verify(current, bridge);
    assert(current.data.little_cache.size() == 1);
    assert(current.data.redirect_cache == std::vector<std::size_t>({0, 0, 0}));
    std::mt19937 rng(187);
    for (unsigned repeat = 0; repeat < 32; ++repeat) {
        std::shuffle(separated.begin(), separated.end(), rng);
        current.After(separated);
        Verify(current, separated);
    }
    std::reverse(separated.begin(), separated.end());
    current.After(separated);
    Verify(current, separated);
    current.After({});
    Verify(current, {});
    std::vector<Value> same_page;
    for (unsigned i = 0; i < 1024; ++i) same_page.push_back({(1023 - i) % 4096, 1});
    current.comparisons = 0;
    current.After(same_page);
    Verify(current, same_page);
    assert(current.comparisons == 1023 && current.data.little_cache.size() == 1);
    const std::vector<Value> duplicate_pages{{12, 8}, {40, 8}, {4, 8}, {8192, 8}};
    current.After(duplicate_pages);
    Verify(current, duplicate_pages);
    std::printf("QUERY_GROUPING_PASS ranges=1024 before_comparisons=523776 "
                "after_comparisons=%zu shuffled_batches=32 bridge_groups_before=2 after=1\n",
                comparisons);
}
""".replace("BASELINE", baseline).replace("ACTIVE", active)
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-query-grouping-") as temp:
    path, executable = Path(temp) / "group.cpp", Path(temp) / "group"
    path.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(path), "-o", str(executable)], check=True, timeout=90)
    subprocess.run([str(executable)], check=True, timeout=30)
print("QUERY_GROUPING_HOST_ONLY PS5_frametime=unmeasured")
