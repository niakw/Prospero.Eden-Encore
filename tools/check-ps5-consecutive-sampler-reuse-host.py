#!/usr/bin/env python3
"""Execute selected graphics sampler memo across stages with bounded conflicts."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
memo_marker = "    // Sampler table mapping is stable while the paired guest cache locks are"
assert native.count(memo_marker) == 1
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

fill_guard = "    if (!views.empty()) {"
assert native.count(fill_guard) == 1
fill_at = native.index(fill_guard)
fill_end = native.index("\n    }", fill_at) + len("\n    }")
assert "texture_cache.FillImageViews" in native[fill_at:fill_end]
assert native.index("texture_cache.UpdateRenderTargets(false)") > fill_end
assert native.index("texture_cache.CheckFeedbackLoop(") > fill_end

program = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
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
    VideoCommon::SamplerId GetSamplerId(u32 handle, bool compute) {
        assert(!compute);
        ++lookups;
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
    for (const auto& info : stages) {
        for (const auto& desc : info.texture_descriptors) {
            for (u32 index = 0; index < desc.count; ++index) {
                const auto [view, sampler] = desc.handles.at(index);
                result.views.push_back({view});
                result.samplers.push_back(texture_cache.GetSamplerId(sampler, false));
            }
        }
    }
    return result;
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
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-gfx-memo-") as temp:
    path = Path(temp) / "sampler.cpp"
    path.write_text(program)
    for opt in ("-O0", "-O2"):
        exe = Path(temp) / ("sampler" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(path), "-o", str(exe)], check=True, timeout=45)
        result = subprocess.run([str(exe)], check=True, timeout=20,
                                capture_output=True, text=True)
        expected = ("F01_SAMPLER_LOOKUP_FIXTURE descriptors=7 "
                    "reference_calls=7 maintained_calls=2 avoided_calls=5 "
                    "scope=host_mock")
        assert expected in result.stdout, (opt, result.stdout)
        print(expected, opt, flush=True)
        print("GPU_PER_DRAW_SAMPLER_MEMO_PASS", opt)
