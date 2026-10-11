#!/usr/bin/env python3
"""R314: actual pinned Eden ViewImageView C++ replay/late GPU map regression."""
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pin = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
rel = "src/video_core/texture_cache/texture_cache.h"
git_blob = "640bd38407b772d52701c22b81b3189adb17bed8"
patch_rel = "headless/backports/eden-ps5-texture-null-view-remap.patch"
apply = (root / "tools/apply-eden-backports.sh").read_text()
assert "expected=" + pin in apply
assert apply.count('apply_one "$root/' + patch_rel + '"') == 1

url = "https://raw.githubusercontent.com/eden-emulator/mirror/" + pin + "/" + rel
with urlopen(Request(url, headers={"User-Agent": "Eden-Encore-R314-pinned-source"}), timeout=25) as resp:
    data = resp.read(400000)
sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
assert sha == git_blob, (sha, git_blob)
with tempfile.TemporaryDirectory(prefix="eden-r314-null-TIC-") as d:
    target = Path(d) / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    patch = root / patch_rel
    subprocess.run(["git", "apply", "--check", str(patch)], check=True, cwd=d, timeout=10)
    subprocess.run(["git", "apply", str(patch)], check=True, cwd=d, timeout=10)
    text = target.read_text()
    start = text.index("ImageViewId TextureCache<P>::VisitImageView(")
    end = text.index("\ntemplate <class P>", start)
    fn = text[start:end]
    assert fn.count("#ifdef PS5_NATIVE") == 1
    assert "if (it->second == NULL_IMAGE_VIEW_ID && IsValidEntry(*gpu_memory, descriptor))" in fn
    assert "if (is_new_tc || pair->second == NULL_IMAGE_VIEW_ID)" in fn
    recovered = fn[fn.index("if (it->second == NULL_IMAGE_VIEW_ID"):
                   fn.index("#endif", fn.index("if (it->second == NULL_IMAGE_VIEW_ID"))]
    assert "if (pair->second != NULL_IMAGE_VIEW_ID)\n            ++texture_bindings_serial;" in recovered
    assert recovered.index("++texture_bindings_serial") < recovered.index(
        "channel_state->image_view_ids.insert_or_assign")
    assert fn.index("channel_state->image_view_ids.insert_or_assign(map_index, pair->second);") < fn.index("return pair->second;", fn.index("if (it->second == NULL_IMAGE_VIEW_ID"))

    # Compile the EXACT C++ function from production patch against a tiny
    # texture-cache harness: no manually reimplemented decision flow.
    head = r"""
#include <cassert>
#include <cstdint>
#include <functional>
#include <unordered_map>
#include <utility>
#define LOG_DEBUG(...) ((void)0)
using u32 = std::uint32_t;
using ImageViewId = int;
constexpr ImageViewId NULL_IMAGE_VIEW_ID = 0;
namespace Common { struct SlotId {static constexpr u32 TAGGED_VALUE=0x80000000;}; }
struct TICEntry {
    int value{};
    bool operator==(TICEntry const& rhs) const {return rhs.value==value;}
};
namespace std {template<> struct hash<TICEntry> {
    size_t operator()(TICEntry x) const noexcept {return std::hash<int>{}(x.value);}
};}
struct MemoryManager { bool mapped{}; };
bool IsValidEntry(MemoryManager& memory, TICEntry t) {
    return memory.mapped && t.value > 0;
}
struct DescriptorTable {
    u32 current_limit{15};
    TICEntry descriptor{3};
    bool changed{true};
    std::pair<TICEntry,bool> Read(MemoryManager const&,u32) {
        return {descriptor,changed};
    }
};
struct Channel {
    DescriptorTable compute_image_table, graphics_image_table;
    std::unordered_map<TICEntry,ImageViewId> image_views;
    std::unordered_map<u32,ImageViewId> image_view_ids;
};
struct Dummy{};
template<class P> struct TextureCache {
    Channel* channel_state;
    MemoryManager* gpu_memory;
    int next_id{1};
    int prepared{};
    u32 texture_bindings_serial{};
    int transient_create_failures{};
    ImageViewId VisitImageView(u32 index,bool compute);
    ImageViewId CreateImageView(TICEntry) {
        if (transient_create_failures > 0) {
            --transient_create_failures;
            return NULL_IMAGE_VIEW_ID;
        }
        return next_id++;
    }
    void PrepareImageView(ImageViewId id,bool,bool) {
        if (!id) return; // actual TextureCache::PrepareImageView short-circuits
        ++prepared;
    }
};
"""
    tail = r"""
int main() {
    Channel c{};
    MemoryManager gm{};
    TextureCache<Dummy> tc{&c,&gm};
    // Initially the descriptor is valid but its GPU pages are absent.
    assert(tc.VisitImageView(5,false)==NULL_IMAGE_VIEW_ID);
    assert(c.image_view_ids.at(5)==NULL_IMAGE_VIEW_ID);
    assert(tc.next_id==1);
    c.graphics_image_table.changed=false;
    gm.mapped=true; // Guest maps GPU pages; descriptor bytes do NOT change.
#ifdef PS5_NATIVE
    assert(tc.VisitImageView(5,false)==1);
    assert(c.image_view_ids.at(5)==1);
    assert(tc.prepared==1 && tc.texture_bindings_serial==1);
    assert(tc.VisitImageView(5,false)==1);
    assert(tc.prepared==2 && tc.texture_bindings_serial==1);
    assert(tc.next_id==2); // normal cached draw path never recreates
#else
    assert(tc.VisitImageView(5,false)==NULL_IMAGE_VIEW_ID);
    assert(tc.next_id==1); // original upstream behavior preserved
#endif
    // A sparse/compute texture shares the TIC bytes but NOT the slot key.
    c.compute_image_table.changed=true;
    assert(tc.VisitImageView(5,true)==1);
    assert(c.image_view_ids.at(5|Common::SlotId::TAGGED_VALUE)==1);
    // Invalid format stays null even after remapping.
    c.graphics_image_table.changed=true;
    c.graphics_image_table.descriptor.value=0;
    assert(tc.VisitImageView(5,false)==NULL_IMAGE_VIEW_ID);
    c.graphics_image_table.changed=false;
    assert(tc.VisitImageView(5,false)==NULL_IMAGE_VIEW_ID);
#ifdef PS5_NATIVE
    // A valid mapped TIC can nevertheless produce a null view if image
    // allocation fails temporarily. The descriptor stays identical afterward.
    Channel retry_state{};
    MemoryManager retry_mem{true};
    TextureCache<Dummy> retry{&retry_state, &retry_mem};
    retry.transient_create_failures=1;
    assert(retry.VisitImageView(5,false)==NULL_IMAGE_VIEW_ID);
    assert(retry_state.image_views.at(TICEntry{3})==NULL_IMAGE_VIEW_ID);
    assert(retry.texture_bindings_serial==0);
    retry_state.graphics_image_table.changed=false;
    assert(retry.VisitImageView(5,false)==1);
    assert(retry_state.image_views.at(TICEntry{3})==1);
    assert(retry.texture_bindings_serial==1);
    assert(retry.VisitImageView(5,false)==1);
    assert(retry.prepared==2 && retry.next_id==2);
    assert(retry.texture_bindings_serial==1);
#endif
}
"""
    cpp = Path(d) / "view.cpp"
    cpp.write_text(head + "template<class P>\n" + fn + tail)
    for label,flags in (("ps5", ["-DPS5_NATIVE"]),("upstream", [])):
        binary = Path(d)/label
        subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",*flags,
                        str(cpp),"-o",str(binary)],check=True,timeout=30)
        subprocess.run([str(binary)],check=True,timeout=10)
        print("PASS R314 actual C++ null texture recovery",label)
print("PASS R314 pinned exact git blob replay and GPU remap view recovery")
