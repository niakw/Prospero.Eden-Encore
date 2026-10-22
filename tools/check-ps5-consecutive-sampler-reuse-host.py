#!/usr/bin/env python3
"""Verify selected native sampler dedup preserves descriptor order and stage reset."""
from pathlib import Path
import subprocess
import shutil
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
start = "        bool last_sampler_valid = false;"
end = "        if constexpr (Spec::has_images) {"
assert native.count(start) == 1
begin = native.index(start)
finish = native.index(end, begin)
loop = native[begin:finish]
assert loop.count("texture_cache.GetSamplerId(handle.second, false)") == 1
assert loop.index("last_sampler_handle != handle.second") < loop.index("samplers.push_back(last_sampler_id)")
assert loop.count("views.push_back({handle.first});") == 1
assert loop.count("samplers.push_back(last_sampler_id);") == 1

fill_guard = "    if (!views.empty()) {"
assert native.count(fill_guard) == 1
fill_at = native.index(fill_guard)
fill_end = native.index("\n    }", fill_at) + len("\n    }")
selected_fill = native[fill_at:fill_end]
assert "texture_cache.FillImageViews" in selected_fill
assert native.index("texture_cache.CheckFeedbackLoop(") > fill_end
assert native.index("texture_cache.UpdateRenderTargets(false)") > fill_end

program = r"""
#include <cassert>
#include <cstdint>
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
    VideoCommon::SamplerId GetSamplerId(u32 handle, bool compute) {
        assert(!compute);
        ++lookups;
        return handle + 100;
    }
};
struct View { u32 index{}; };
struct CaseResult {
    std::vector<View> views;
    std::vector<VideoCommon::SamplerId> samplers;
};
static CaseResult configure(const Info& info, TexCache& texture_cache) {
    CaseResult result;
    auto& views = result.views;
    auto& samplers = result.samplers;
    const auto read_handle = [](const auto& desc, u32 index) {
        return desc.handles.at(index);
    };
""" + loop + r"""
    return result;
}
static unsigned fill_calls = 0;
static void fill_views(const std::vector<View>& views) {
    if (!views.empty()) {
        ++fill_calls;
    }
}
int main() {
    TexCache texture_cache{};
    Info info{};
    auto empty = configure(info, texture_cache);
    fill_views(empty.views);
    assert(fill_calls == 0 && texture_cache.lookups == 0);
    info.texture_descriptors = {
        {{{1,7},{2,7},{3,9},{4,9}},4},
        {{{5,7},{6,7}},2},
    };
    auto a = configure(info, texture_cache);
    fill_views(a.views);
    assert(fill_calls == 1);
    assert(texture_cache.lookups == 3);
    assert(a.views.size() == 6 && a.samplers.size() == 6);
    assert(a.views[0].index == 1 && a.views[5].index == 6);
    assert((a.samplers == std::vector<u32>{107,107,109,109,107,107}));
    // No cross-draw state survives: same handles are resolved anew.
    auto b = configure(info, texture_cache);
    assert(texture_cache.lookups == 6 && b.samplers == a.samplers);
    // Different handles resolve separately, even if they target the same view.
    info.texture_descriptors = {{{{1,7},{1,9},{1,7}},3}};
    auto c = configure(info, texture_cache);
    assert(texture_cache.lookups == 9);
    assert((c.samplers == std::vector<u32>{107,109,107}));
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-gfx-sampler-") as tmp:
    source = Path(tmp) / "sampler.cpp"
    source.write_text(program)
    for opt in ("-O0", "-O2"):
        exe = Path(tmp) / ("sampler" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", str(source), "-o", str(exe)],
                       check=True, timeout=45)
        subprocess.run([str(exe)], check=True, timeout=20)
        print("GPU_CONSECUTIVE_SAMPLER_REUSE_PASS", opt)
