#!/usr/bin/env python3
"""Execute selected graphics sampler memo across stages with bounded conflicts."""
from pathlib import Path
import shutil
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_graphics_pipeline.cpp").read_text()
memo_marker = "    // Sampler table mapping is stable while the paired guest cache locks are"
assert native.count(memo_marker) == 1
# This is the source compiled by the native PS5 Vulkan CMake target; do not
# measure an inactive generator or an unselected standalone copy.
cmake=(root/"headless/vulkan.cmake").read_text()
assert 'file(COPY ' in cmake and 'EDEN_ACTIVE_VULKAN' in cmake
assert 'vk_graphics_pipeline' in cmake and '_cost.cpp' in cmake
assert 'PORT_BUILD_DIR' in cmake

begin = native.index(memo_marker)
end = native.index("    const auto config_stage{[&](size_t stage)", begin)
memo = native[begin:end]
assert memo.count("std::array<SamplerMemo, 16> sampler_memo{};") == 1
assert memo.count("texture_cache.GetSamplerId(handle, false)") == 1
assert memo.count("entry.valid = true;") == 1
assert memo.count("entry.handle != handle") == 1
loop_begin = native.index("        for (const auto& desc : info.texture_descriptors)", end)
loop_end = native.index("        if constexpr (Spec::has_images) {", loop_begin)
loop = native[loop_begin:loop_end]
assert loop.count("views.push_back({handle.first});") == 1
assert loop.count("samplers.push_back(resolve_sampler(handle.second));") == 1
# The reference implementation is the exact pinned historical C++ descriptor
# loop, not a rewritten reference approximating the former behavior.
pinned_begin=pinned.index("        for (const auto& desc : info.texture_descriptors) {")
pinned_end=pinned.index("        if constexpr (Spec::has_images) {",pinned_begin)
pinned_loop=pinned[pinned_begin:pinned_end]
assert pinned_loop.count("VideoCommon::SamplerId sampler{texture_cache.GetSamplerId(handle.second, false)};")==1
assert pinned_loop.count("samplers.push_back(sampler);")==1
assert pinned_loop.count("views.push_back({handle.first});")==1


fill_guard = "    if (!views.empty()) {"
assert native.count(fill_guard) == 1
fill_at = native.index(fill_guard)
fill_end = native.index("\n    }", fill_at) + len("\n    }")
assert "texture_cache.FillImageViews" in native[fill_at:fill_end]
assert native.index("texture_cache.UpdateRenderTargets(false)") > fill_end
assert native.index("texture_cache.CheckFeedbackLoop(") > fill_end

program = r"""
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
using u32 = std::uint32_t;
namespace VideoCommon { using SamplerId = u32; }
struct Descriptor {
    std::vector<std::pair<u32,u32>> handles;
    u32 count{};
};
struct Info { std::vector<Descriptor> texture_descriptors; };
struct TexCache {
    unsigned lookups{};
    u32 generation_offset{100};
    bool expensive_lookup{};
    std::uint64_t pressure{};
    VideoCommon::SamplerId GetSamplerId(u32 handle, bool compute) {
        assert(!compute);
        ++lookups;
        if (expensive_lookup) {
            // Fixed synthetic cost on BOTH paths. Never represent this as a
            // measurement of real GPU/driver cache lookup latency.
            std::uint64_t value = handle + generation_offset;
            for (unsigned i = 0; i < 1024; ++i)
                value = (value * 1664525ULL + 1013904223ULL) ^ (value >> 7);
            pressure += value;
        }
        return handle + generation_offset;
    }
};
struct View { u32 index{}; };
struct CaseResult {
    std::vector<View> views;
    std::vector<VideoCommon::SamplerId> samplers;
};
static CaseResult configure(const std::array<Info, 2>& stages,
                            TexCache& texture_cache) {
    CaseResult result;
    auto& views = result.views;
    auto& samplers = result.samplers;
    const auto read_handle = [](const auto& desc, u32 index) {
        return desc.handles.at(index);
    };
""" + memo + r"""
    for (const auto& info : stages) {
""" + loop + r"""
    }
    return result;
}
// Comparable direct-reference path: one sampler lookup per descriptor.
// This is an isolated fixture, not a replay of historical guest timing.
static CaseResult configure_reference(const std::array<Info, 2>& stages,
                                      TexCache& texture_cache) {
    CaseResult result;
    auto& views = result.views;
    auto& samplers = result.samplers;
    const auto read_handle = [](const auto& desc, u32 index) {
        return desc.handles.at(index);
    };
    for (const auto& info : stages) {
""" + pinned_loop + r"""
    }
    return result;
}
// Host-only same-draw lock A/B using native-extracted descriptor loops.
// Multiple medians and alternating order reduce scheduler/cache-warm-up bias.
struct LockBudget {std::uint64_t held_ns{}, wait_ns{}, checksum{}; unsigned lookups{};};
using Clock = std::chrono::steady_clock;
using Config = CaseResult(*)(const std::array<Info,2>&,TexCache&);
static LockBudget lock_budget(Config config, const std::array<Info,2>& stages) {
    TexCache cache{};
    cache.expensive_lookup = true;
    std::mutex mutex;
    std::atomic<bool> running{true};
    std::atomic<unsigned> contender_entries{};
    std::thread contender([&] {
        while (running.load(std::memory_order_relaxed)) {
            {std::lock_guard lk(mutex);++contender_entries;}
            std::this_thread::yield();
        }
    });
    LockBudget result{};
    constexpr unsigned draws = 2048;
    for (unsigned i = 0; i < draws; ++i) {
        const auto started=Clock::now();
        mutex.lock();
        const auto entered=Clock::now();
        const auto descriptors=config(stages,cache);
        const auto finished=Clock::now();
        mutex.unlock();
        result.wait_ns+=static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(entered-started).count());
        result.held_ns+=static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(finished-entered).count());
        assert((descriptors.samplers==std::vector<u32>{107,107,109,107,109,109,107}));
    }
    running.store(false,std::memory_order_relaxed);
    contender.join();
    result.lookups=cache.lookups;
    result.checksum=cache.pressure;
    assert(result.checksum != 0); // prevent benchmark optimizer eliminating lookup work
    // The waiter is a real concurrent mutex contender, not a virtual cost.
    assert(contender_entries.load(std::memory_order_relaxed)>0);
    return result;
}
static std::uint64_t median_held(std::array<std::uint64_t,5> ns) {
    std::sort(ns.begin(),ns.end());
    return ns[2];
}
int main() {
    TexCache cache{};
    std::array<Info, 2> stages{};
    auto empty = configure(stages, cache);
    assert(empty.views.empty() && empty.samplers.empty() && cache.lookups == 0);

    stages[0].texture_descriptors = {
        {{{1,7},{2,7},{3,9},{4,7},{5,9}},5},
    };
    stages[1].texture_descriptors = {
        {{{6,9},{7,7}},2},
    };
    auto a = configure(stages, cache);
    assert(cache.lookups == 2); // A,B,A,B across two shader stages.
    assert(a.views.size() == 7 && a.samplers.size() == 7);
    assert(a.views.front().index == 1 && a.views.back().index == 7);
    assert((a.samplers == std::vector<u32>{107,107,109,107,109,109,107}));

    // Quantify work eliminated on the SAME descriptor fixture. Direct lookup
    // has seven cache calls; the maintained per-draw memo has two. Equality
    // of views and IDs guards correctness instead of assuming less work is
    // always safe. No timing or FC27 frame gain is inferred from this mock.
    TexCache reference_cache{};
    const auto reference = configure_reference(stages, reference_cache);
    assert(reference.views.size() == a.views.size());
    for (std::size_t index = 0; index < a.views.size(); ++index)
        assert(reference.views[index].index == a.views[index].index);
    assert(reference.samplers == a.samplers);
    assert(reference_cache.lookups == 7 && cache.lookups == 2);
    std::printf("F01_SAMPLER_LOOKUP_FIXTURE descriptors=7 reference_calls=%u "
                "maintained_calls=%u avoided_calls=%u scope=host_mock\n",
                reference_cache.lookups, cache.lookups,
                reference_cache.lookups - cache.lookups);

    auto b = configure(stages, cache);
    assert(cache.lookups == 4); // No sampler ID outlives a draw.
    assert(b.samplers == a.samplers);

    // Colliding indices are correctness-safe cache misses, not bad IDs.
    stages[0].texture_descriptors = {{{{1,7},{2,23},{3,7}},3}};
    stages[1].texture_descriptors = {{{{4,7}},1}};
    auto conflict = configure(stages, cache);
    assert(cache.lookups == 7); // 7,23,7 miss; final 7 hit.
    assert((conflict.samplers == std::vector<u32>{107,123,107,107}));

    // Texture identity is independent of the sampler identity.
    stages[0].texture_descriptors = {{{{1,7},{1,9},{2,7}},3}};
    stages[1].texture_descriptors.clear();
    auto same_view = configure(stages, cache);
    assert(cache.lookups == 9);
    assert((same_view.samplers == std::vector<u32>{107,109,107}));
    assert(same_view.views[0].index == same_view.views[1].index);

    // A later draw must never retain the previous descriptor generation.
    cache.generation_offset = 200;
    auto refreshed = configure(stages, cache);
    assert(cache.lookups == 11);
    assert((refreshed.samplers == std::vector<u32>{207,209,207}));

    // Restore the identical cross-stage seven-descriptor workload after
    // collision/generation correctness tests changed 'stages' above.
    std::array<Info,2> budget_stages{};
    budget_stages[0].texture_descriptors = {
        {{{1,7},{2,7},{3,9},{4,7},{5,9}},5},
    };
    budget_stages[1].texture_descriptors = {
        {{{6,9},{7,7}},2},
    };
    // Real mutex contender with a fixed synthetic GetSamplerId cost.
    std::array<std::uint64_t,5> old_hold{},current_hold{};
    std::array<std::uint64_t,5> old_wait{},current_wait{};
    for (unsigned round=0;round<5;++round) {
        const auto run_old = [&] {
            auto m=lock_budget(configure_reference,budget_stages);
            assert(m.lookups==2048*7);
            old_hold[round]=m.held_ns;old_wait[round]=m.wait_ns;
        };
        const auto run_new = [&] {
            auto m=lock_budget(configure,budget_stages);
            assert(m.lookups==2048*2);
            current_hold[round]=m.held_ns;current_wait[round]=m.wait_ns;
        };
        if (round%2) {run_new();run_old();}
        else {run_old();run_new();}
    }
    const auto old_median=median_held(old_hold);
    const auto new_median=median_held(current_hold);
    assert(old_median>new_median);
    // Guard against fixture regressions, not a claim of real PS5 gains.
    assert(new_median*10 < old_median*9);
    std::sort(old_wait.begin(),old_wait.end());
    std::sort(current_wait.begin(),current_wait.end());
    std::printf("F01_NATIVE_SOURCE_LOCK_BUDGET draws=2048 descriptors=7 "
                "prior_calls=14336 maintained_calls=4096 "
                "prior_held_ns=%llu maintained_held_ns=%llu "
                "prior_wait_ns=%llu maintained_wait_ns=%llu "
                "scope=host_synthetic_lookup_and_real_contender\n",
                static_cast<unsigned long long>(old_median),
                static_cast<unsigned long long>(new_median),
                static_cast<unsigned long long>(old_wait[2]),
                static_cast<unsigned long long>(current_wait[2]));
    std::puts("F01_NATIVE_SELECTION_SOURCE_PASS ps5_real_latency_unmeasured");
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-gfx-memo-") as temp:
    path = Path(temp) / "sampler.cpp"
    path.write_text(program)
    for opt in ("-O0", "-O2"):
        exe = Path(temp) / ("sampler" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-pthread", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(path), "-o", str(exe)], check=True, timeout=45)
        result = subprocess.run([str(exe)], check=True, timeout=20,
                                capture_output=True, text=True)
        expected = ("F01_SAMPLER_LOOKUP_FIXTURE descriptors=7 "
                    "reference_calls=7 maintained_calls=2 avoided_calls=5 "
                    "scope=host_mock")
        assert expected in result.stdout, (opt, result.stdout)
        print(expected, opt, flush=True)
        budget = re.search(r"^F01_NATIVE_SOURCE_LOCK_BUDGET .*?$",
                           result.stdout, re.MULTILINE)
        assert budget, (opt, result.stdout[-2400:])
        selection = "F01_NATIVE_SELECTION_SOURCE_PASS ps5_real_latency_unmeasured"
        assert selection in result.stdout, (opt, result.stdout[-1400:])
        print(budget.group(0), opt, flush=True)
        print(selection, opt, flush=True)
        print("GPU_PER_DRAW_SAMPLER_MEMO_PASS", opt, flush=True)
