#!/usr/bin/env python3
"""Compile maintained native texture view/framebuffer deletion paths at O0 and O2."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
def selected(name, next_name):
    start = src.index("template <class P>\nvoid TextureCache<P>::" + name + "(")
    end = src.index("template <class P>\nvoid TextureCache<P>::" + next_name + "(", start)
    return src[start:end]
refs = selected("RemoveImageViewReferences", "RemoveFramebuffers")
fbs = selected("RemoveFramebuffers", "MarkModification")
assert refs.count("if (removed_views.empty())") == 1
assert fbs.count("if (removed_views.empty())") == 1
assert refs.index("if (removed_views.empty())") < refs.index("for (size_t c : active_channel_ids)")
assert fbs.index("if (removed_views.empty())") < fbs.index("runtime.FlushDeferredClear()")
for body in (refs,fbs):
    assert body.count("#ifdef PS5_NATIVE") == body.count("#endif") == 1
assert "RemoveImageViewReferences(image_view_ids);" in src
assert "RemoveFramebuffers(image_view_ids);" in src
gen = (root / "tools/prepare-vulkan-port.py").read_text()
assert "Retired images without a view" in gen
assert "vulkan-cache/video_core/texture_cache/texture_cache.h" in gen
assert (root / "headless/vulkan.cmake").read_text().count('file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")') == 1
# F07 P0.4: compile the exact change-notification predicate emitted by
# the active Vulkan texture cache. Stale remapped views must advance the
# generation even when the new backing is temporarily unavailable (NULL).
header="ImageViewId TextureCache<P>::VisitImageView(u32 index, bool compute) {"
assert src.count(header)==1
method=src.split(header,1)[1].split("\ntemplate <class P>",1)[0]
marker="        if (pair->second != NULL_IMAGE_VIEW_ID || remapped_cached_view)\n            ++texture_bindings_serial;"
assert method.count(marker)==1
assert method.index(marker) < method.index("channel_state->image_view_ids.insert_or_assign(map_index, pair->second);",method.index("const bool remapped_cached_view"))
assert "'F07 P0.4 remap-to-NULL view binding generation'" in gen
notification=marker

fixture = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <map>
#include <span>
#include <utility>
#include <vector>
using ImageViewId=int;
#define ASSERT(x) assert(x)
struct Key {
    int view{};
    bool Contains(std::span<const ImageViewId> removed) const {
        return std::find(removed.begin(),removed.end(),view)!=removed.end();
    }
    bool operator<(const Key& rhs) const { return view < rhs.view; }
};
struct Channel {
    std::map<int,ImageViewId> image_views;
};
struct Runtime {
    int clears{};
    void FlushDeferredClear() { ++clears; }
};
struct Sentenced {
    int pushes{};
    void Push(int&&) { ++pushes; }
};
template <class P>
struct TextureCache {
    std::array<Channel,2> channel_storage{};
    std::vector<std::size_t> active_channel_ids{0,1};
    Runtime runtime;
    std::map<Key,int> framebuffers;
    std::array<int,16> slot_framebuffers{};
    Sentenced sentenced_framebuffers;
    int last_framebuffer_id{};
    int last_framebuffer_serial{99};
    void RemoveImageViewReferences(std::span<const ImageViewId>);
    void RemoveFramebuffers(std::span<const ImageViewId>);
};
""" + refs + fbs + r"""
int main() {
    TextureCache<int> cache;
    cache.channel_storage[0].image_views={{1,15},{2,17}};
    cache.channel_storage[1].image_views={{3,18}};
    cache.framebuffers={{Key{15},1},{Key{16},2},{Key{18},3}};
    cache.last_framebuffer_id=1;
    const std::vector<ImageViewId> none;
    // Zero-view retirement: no channel traversal side effect, no render
    // target flush, no framebuffer deletion and no serial invalidation.
    cache.RemoveImageViewReferences(none);
    cache.RemoveFramebuffers(none);
    assert(cache.channel_storage[0].image_views.size()==2);
    assert(cache.channel_storage[1].image_views.size()==1);
    assert(cache.framebuffers.size()==3);
    assert(cache.runtime.clears==0 && cache.sentenced_framebuffers.pushes==0);
    assert(cache.last_framebuffer_id==1 && cache.last_framebuffer_serial==99);
    const std::vector<ImageViewId> removed{15,18};
    cache.RemoveImageViewReferences(removed);
    cache.RemoveFramebuffers(removed);
    assert(cache.channel_storage[0].image_views.size()==1);
    assert(cache.channel_storage[0].image_views.at(2)==17);
    assert(cache.channel_storage[1].image_views.empty());
    assert(cache.framebuffers.size()==1);
    assert(cache.framebuffers.begin()->first.view==16);
    assert(cache.runtime.clears==1 && cache.sentenced_framebuffers.pushes==2);
    assert(cache.last_framebuffer_id==0 && cache.last_framebuffer_serial==0);
    // A second deletion of a non-empty but already-deleted view retains
    // the ordinary deferred-clear ordering and map scan semantics.
    cache.RemoveFramebuffers(removed);
    assert(cache.runtime.clears==2 && cache.sentenced_framebuffers.pushes==2);
}
"""
# Append a source-extracted remap-notification contract to the same C++20
# witness. A normal NULL->NULL retry must not invent a new generation.
fixture=fixture.replace("int main() {", r'''
struct RemapGeneration {
    static constexpr int NULL_IMAGE_VIEW_ID=0;
    int texture_bindings_serial{};
    void Publish(int reconstructed_view, bool remapped_cached_view) {
        struct Entry { int second; };
        Entry entry{reconstructed_view};
        Entry* pair=&entry;
''' + notification + r'''
    }
};
int main() {
    RemapGeneration null_to_null;
    null_to_null.Publish(0,false);
    assert(null_to_null.texture_bindings_serial==0);
    RemapGeneration null_to_valid;
    null_to_valid.Publish(29,false);
    assert(null_to_valid.texture_bindings_serial==1);
    RemapGeneration remapped_to_null;
    remapped_to_null.Publish(0,true);
    assert(remapped_to_null.texture_bindings_serial==1);
    RemapGeneration remapped_to_valid;
    remapped_to_valid.Publish(31,true);
    assert(remapped_to_valid.texture_bindings_serial==1);
''',1)
with tempfile.TemporaryDirectory(prefix="encore-empty-image-retirement-") as tmp:
    cpp = Path(tmp) / "fixture.cpp"
    cpp.write_text(fixture)
    for opt in ("-O0", "-O2"):
        exe = Path(tmp) / opt
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-DPS5_NATIVE",str(cpp),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("PS5_EMPTY_IMAGE_VIEW_RETIREMENT_PASS",opt)
