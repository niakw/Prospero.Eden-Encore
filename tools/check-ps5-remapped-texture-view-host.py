#!/usr/bin/env python3
"""F03/F04 source-extracted TIC view remap recovery without stale textures.

The live cached TIC may point at a view whose ImageBase is Remapped. Exercise
normal reuse, remap/recreation, missing backing, new descriptor, buffer views
and per-slot mapping reconstruction. This is not a full PS5 GPU driver test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
p = "src/video_core/texture_cache/texture_cache.h"
shipping = (root / "vendor/encore-active/eden-backports" / p).read_text()
native = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
installer = (root / "tools/apply-eden-backports.sh").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
patch = root / "headless/backports/eden-ps5-texture-remapped-view-rebind.patch"
slot_patch = root / "headless/backports/eden-ps5-texture-missing-channel-slot-guard.patch"
assert "validate_ps5_texture_remapped_view_rebind" in installer
assert "is_remapped_view(pair->second)" in native
assert "is_remapped_view(pair->second)" in shipping

def method(text):
    start = text.index("ImageViewId TextureCache<P>::VisitImageView(")
    return text[start:text.index("\ntemplate <class P>", start)]

shipping_method = method(shipping)
native_method = method(native)
for content in (shipping_method, native_method):
    assert content.count("is_remapped_view(pair->second)") == 2
    assert content.count("ImageFlagBits::Remapped") == 1
    assert "if (remapped_cached_view)" in content
    assert content.index("is_remapped_view(pair->second)") < content.index(
        "PrepareImageView(pair->second, false, false);")
    assert "channel_state->image_view_ids.insert_or_assign(map_index, NULL_IMAGE_VIEW_ID);" in content
assert "image_view_ids.end() && is_remapped_view(it->second)" in native_method
assert "image_view_ids.end() && is_remapped_view(it->second)" in shipping_method
assert "validate_ps5_texture_missing_channel_slot_guard" in installer
assert "F04 native TIC layer view safety" in generator

with tempfile.TemporaryDirectory(prefix="encore-remap-replay-") as td:
    stage = Path(td)
    target = stage / p
    target.parent.mkdir(parents=True)
    target.write_text(shipping)
    # The missing-slot patch is ordered after remapped-view recovery.
    # Reverse the last layer first, then replay the full native stack.
    for args in (["git","apply","--reverse","--check",str(slot_patch)],
                 ["git","apply","--reverse",str(slot_patch)],
                 ["git","apply","--reverse","--check",str(patch)],
                 ["git","apply","--reverse",str(patch)],
                 ["git","apply","--check",str(patch)],
                 ["git","apply",str(patch)],
                 ["git","apply","--check",str(slot_patch)],
                 ["git","apply",str(slot_patch)]):
        result = subprocess.run(args, cwd=stage, capture_output=True,
                                text=True, timeout=18)
        assert result.returncode == 0, (args, result.stderr[-3000:])
    assert target.read_text() == shipping, "remap patch does not roundtrip"
print("ENCORE_REMAP_VIEW_PATCH_ROUNDTRIP_PASS")

prologue = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <unordered_map>
#include <utility>
// The source-extracted function retains the production invalid-index trace.
#define LOG_DEBUG(...) ((void)0)
#define HW_GPU 0
using u32=std::uint32_t;
using ImageViewId=u32;
constexpr ImageViewId NULL_IMAGE_VIEW_ID=0;
namespace Common {
struct SlotId {static constexpr u32 TAGGED_VALUE = 0x80000000U;};
}
enum class ImageFlagBits : u32 { Remapped=1 };
struct ImageFlags {bool remapped{};};
bool operator&(const ImageFlags& flags,ImageFlagBits) {return flags.remapped;}
bool True(bool yes) {return yes;}
struct ImageBase {ImageFlags flags{};};
struct ImageViewBase {
    u32 image_id{};
    bool buffer{};
    bool IsBuffer() const {return buffer;}
};
struct FakeMemory {bool valid=true;};
bool IsValidEntry(const FakeMemory& m,int) {return m.valid;}
struct DescriptorTable {
    u32 current_limit=128;
    int descriptor=17;
    bool is_new=true;
    std::pair<int,bool> Read(FakeMemory&,u32) const {return {descriptor,is_new};}
};
struct ChannelState {
    DescriptorTable graphics_image_table{};
    DescriptorTable compute_image_table{};
    std::unordered_map<int,ImageViewId> image_views;
    std::unordered_map<u32,ImageViewId> image_view_ids;
};
template<class P>struct TextureCache {
    FakeMemory mem{};
    FakeMemory* gpu_memory=&mem;
    ChannelState channel{};
    ChannelState* channel_state=&channel;
    std::array<ImageViewBase,40> slot_image_views{};
    std::array<ImageBase,40> slot_images{};
    u32 texture_bindings_serial{};
    int created{};
    int prepared{};
    int prepared_remapped{};
    ImageViewId CreateImageView(int descriptor) {
        const auto id = static_cast<ImageViewId>(++created);
        assert(id<slot_image_views.size());
        slot_image_views[id] = {.image_id=id,.buffer=descriptor==11};
        return id;
    }
    void PrepareImageView(ImageViewId id,bool,bool) {
        if (!id) return;
        ++prepared;
        if (slot_images[slot_image_views[id].image_id].flags.remapped)
            ++prepared_remapped;
    }
    ImageViewId VisitImageView(u32,bool);
};
"""
epilogue = r"""
int main() {
    TextureCache<int> tc;
    auto& table=tc.channel.graphics_image_table;
    const u32 slot=2;
    const auto first=tc.VisitImageView(slot,false);
    assert(first==1 && tc.created==1 && tc.prepared==1);
    table.is_new=false;
    assert(tc.VisitImageView(slot,false)==first);
    assert(tc.created==1 && tc.prepared==2);
    assert(tc.texture_bindings_serial==0);
#ifdef PS5_NATIVE
    // Guest remapping changes image backing, NOT the TIC bytes.
    tc.slot_images[first].flags.remapped=true;
    const auto second=tc.VisitImageView(slot,false);
    assert(second==2 && tc.created==2 && tc.prepared_remapped==0);
    assert(tc.texture_bindings_serial==1);
    assert(tc.VisitImageView(slot,false)==second && tc.created==2);
    // Remap again, but residency has not returned: invalidate the old ID.
    tc.slot_images[second].flags.remapped=true;
    tc.mem.valid=false;
    const auto prepared=tc.prepared;
    const auto serial=tc.texture_bindings_serial;
    assert(tc.VisitImageView(slot,false)==NULL_IMAGE_VIEW_ID);
    assert(tc.prepared==prepared && tc.created==2);
    assert(tc.texture_bindings_serial==serial+1);
    tc.mem.valid=true;
    const auto third=tc.VisitImageView(slot,false);
    assert(third==3 && tc.created==3 && tc.prepared_remapped==0);
    // Descriptor gets invalidated and re-read but has unchanged bytes;
    // the shared descriptor-to-view mapping must reject the remapped ID.
    tc.slot_images[third].flags.remapped=true;
    table.is_new=true;
    const auto fourth=tc.VisitImageView(slot,false);
    assert(fourth==4 && tc.created==4 && tc.prepared_remapped==0);
    table.is_new=false;
    assert(tc.VisitImageView(slot,false)==fourth && tc.created==4);
    // Invalidated per-slot entry must be reconstructed without .end() UB.
    tc.channel.image_view_ids.erase(slot);
    assert(tc.VisitImageView(slot,false)==fourth);
    // Buffer texture views have no ImageBase dependency.
    table.descriptor=11;
    table.is_new=true;
    const auto buffer=tc.VisitImageView(slot,false);
    assert(buffer==5);
    tc.slot_images[buffer].flags.remapped=true;
    table.is_new=false;
    assert(tc.VisitImageView(slot,false)==buffer && tc.created==5);
    // Recovery of a NULL view is also required without a TIC rewrite.
    tc.channel.image_view_ids[slot]=NULL_IMAGE_VIEW_ID;
    assert(tc.VisitImageView(slot,false)==buffer && tc.created==5);
#else
    // The non-native upstream path is deliberately unchanged.
    tc.slot_images[first].flags.remapped=true;
    assert(tc.VisitImageView(slot,false)==first);
#endif
}
"""
compilers=list(dict.fromkeys(filter(None,(
    shutil.which("clang++"),shutil.which("g++"),shutil.which("c++")))))
assert compilers, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-view-remap-host-") as td:
    cpp=Path(td)/"view.cpp"
    # The shipping implementation also runs on PS5 and must tolerate
    # missing per-channel slots, not only the native Vulkan overlay.
    for owner, selected_method in (("shipping",shipping_method),("native",native_method)):
        cpp.write_text(prologue + "\ntemplate<class P>\n" + selected_method + epilogue)
        for compiler in compilers:
            for opt in ("-O0","-O2"):
                for label, flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
                    exe=Path(td)/(Path(compiler).name+opt+label+owner)
                    built=subprocess.run(
                        [compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                         "-fsanitize=undefined","-fno-sanitize-recover=all",
                         *flags,str(cpp),"-o",str(exe)],
                        text=True,capture_output=True,timeout=60)
                    assert built.returncode==0,(compiler,opt,label,owner,built.stderr[-5000:])
                    ran=subprocess.run([str(exe)],text=True,capture_output=True,timeout=20)
                    assert ran.returncode==0,(compiler,opt,label,owner,ran.stderr[-5000:])
                    print("ENCORE_REMAP_TIC_VIEW_PASS",owner,Path(compiler).name,opt,label)
