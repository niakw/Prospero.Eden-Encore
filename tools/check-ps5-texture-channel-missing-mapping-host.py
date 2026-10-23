#!/usr/bin/env python3
"""Extract and compile the native TIC/TSC cached-mapping recovery paths."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
active=root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h"
source=active.read_text()
def extract(begin,end):
    a=source.index(begin)
    return source[a:source.index(end,a)]
sampler=extract("template <class P>\nSamplerId TextureCache<P>::GetSamplerId(",
                "template <class P>\nconst typename P::Sampler& TextureCache<P>::GetSampler(")
image=extract("template <class P>\nImageViewId TextureCache<P>::VisitImageView(",
              "template <class P>\nFramebufferId TextureCache<P>::GetFramebufferId(")
assert sampler.count("if (it == channel_state->sampler_ids.end())")==1
assert image.count("it == channel_state->image_view_ids.end()")==2
assert image.count("channel_state->image_view_ids.insert_or_assign(map_index, NULL_IMAGE_VIEW_ID);")==2
assert image.count("IsValidEntry(*gpu_memory, descriptor)")>=2
assert image.count("++texture_bindings_serial;")==1
cmake=(root/"headless/vulkan.cmake").read_text()
assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in cmake
assert 'target_include_directories(video_core BEFORE PUBLIC "${PORT_BUILD_DIR}/vulkan-cache")' in cmake
fixture=r"""
#include <cassert>
#include <cstdint>
#include <map>
#include <unordered_map>
#include <utility>
using u32=std::uint32_t;
using ImageViewId=u32;
using SamplerId=u32;
constexpr ImageViewId NULL_IMAGE_VIEW_ID=0;
constexpr SamplerId NULL_SAMPLER_ID=0;
#define LOG_DEBUG(...) ((void)0)
namespace Common { struct SlotId { static constexpr u32 TAGGED_VALUE=0x80000000u; }; }
struct GpuMemory {};
bool IsValidEntry(GpuMemory&,int descriptor) { return descriptor>0; }
struct DescTable {
    u32 current_limit=16;
    int descriptor=0;
    bool changed=false;
    std::pair<int,bool> Read(GpuMemory&,u32) const { return {descriptor,changed}; }
};
struct Channel {
    DescTable compute_sampler_table,graphics_sampler_table;
    DescTable compute_image_table,graphics_image_table;
    std::unordered_map<u32,SamplerId> sampler_ids;
    std::unordered_map<u32,ImageViewId> image_view_ids;
    std::map<int,ImageViewId> image_views;
};
template<class P> struct TextureCache {
    GpuMemory memory;
    GpuMemory* gpu_memory=&memory;
    Channel channel;
    Channel* channel_state=&channel;
    u32 texture_bindings_serial=0, prepared=0, views_created=0, samplers_found=0;
    bool fail_first_view_creation=false;
    SamplerId GetSamplerId(u32,bool);
    ImageViewId VisitImageView(u32,bool);
    SamplerId FindSampler(int descriptor,bool) { ++samplers_found;return descriptor+300; }
    ImageViewId CreateImageView(int descriptor) {
        ++views_created;
        if (fail_first_view_creation) {
            fail_first_view_creation=false;
            return NULL_IMAGE_VIEW_ID;
        }
        return descriptor+100;
    }
    void PrepareImageView(ImageViewId id,bool,bool) { if (id) ++prepared; }
};
""" + sampler + image + r"""
int main() {
    TextureCache<int> a;
    a.channel.graphics_image_table.descriptor=12;
    // TIC unchanged but mapping absent: no invalid iterator dereference.
    assert(a.VisitImageView(2,false)==112);
    assert(a.channel.image_view_ids.at(2)==112);
    assert(a.prepared==1 && a.views_created==1 && a.texture_bindings_serial==1);
    assert(a.VisitImageView(2,false)==112);
    assert(a.prepared==2 && a.views_created==1 && a.texture_bindings_serial==1);
    // Missing, nonresident TIC becomes a valid NULL entry, recovered later
    // without changing descriptor bytes.
    TextureCache<int> b;
    b.channel.graphics_image_table.descriptor=-1;
    assert(b.VisitImageView(5,false)==NULL_IMAGE_VIEW_ID);
    assert(b.channel.image_view_ids.at(5)==NULL_IMAGE_VIEW_ID);
    assert(b.views_created==0);
    b.channel.graphics_image_table.descriptor=18;
    assert(b.VisitImageView(5,false)==118);
    assert(b.prepared==1 && b.views_created==1 && b.texture_bindings_serial==1);
    // A real descriptor change still follows original new-descriptor logic.
    b.channel.graphics_image_table.changed=true;
    b.channel.graphics_image_table.descriptor=6;
    assert(b.VisitImageView(7,false)==106);
    assert(b.views_created==2);
    // Compute uses a different tagged entry and cannot replace graphics.
    b.channel.compute_image_table.descriptor=9;
    assert(b.VisitImageView(7,true)==109);
    assert(b.channel.image_view_ids.at(7)==106);
    assert(b.channel.image_view_ids.at(7|Common::SlotId::TAGGED_VALUE)==109);
    // A sampler's cached descriptor may also survive mapping replacement.
    b.channel.graphics_sampler_table.descriptor=4;
    assert(b.GetSamplerId(3,false)==304);
    assert(b.samplers_found==1);
    assert(b.GetSamplerId(3,false)==304);
    assert(b.samplers_found==1);
    b.channel.compute_sampler_table.descriptor=8;
    assert(b.GetSamplerId(3,true)==308 && b.samplers_found==2);
    // A cached descriptor can have failed to create a GPU image view
    // without any guest TIC rewrite. The NEXT lookup must retry creation,
    // publish a fresh binding serial, and avoid reusing the cached NULL.
    TextureCache<int> transient;
    transient.channel.graphics_image_table.descriptor=27;
    transient.fail_first_view_creation=true;
    assert(transient.VisitImageView(1,false)==NULL_IMAGE_VIEW_ID);
    assert(transient.channel.image_views.at(27)==NULL_IMAGE_VIEW_ID);
    assert(transient.channel.image_view_ids.at(1)==NULL_IMAGE_VIEW_ID);
    assert(transient.texture_bindings_serial==0 && transient.views_created==1);
    assert(transient.VisitImageView(1,false)==127);
    assert(transient.channel.image_view_ids.at(1)==127);
    assert(transient.texture_bindings_serial==1 && transient.views_created==2);
    assert(transient.VisitImageView(1,false)==127);
    assert(transient.views_created==2); // once live, never recreate each draw

    // A different TIC slot sharing a previously NULL descriptor must
    // also revive the original ImageView mapping with its own real view ID.
    TextureCache<int> shared;
    shared.channel.graphics_image_table.descriptor=29;
    shared.fail_first_view_creation=true;
    assert(shared.VisitImageView(1,false)==NULL_IMAGE_VIEW_ID);
    assert(shared.VisitImageView(2,false)==129);
    assert(shared.VisitImageView(1,false)==129);
    assert(shared.channel.image_view_ids.at(1)==129);
    assert(shared.channel.image_view_ids.at(2)==129);
    assert(shared.views_created==2);

    // Invalid indexes preserve the NULL return, not an out-of-range lookup.
    assert(b.VisitImageView(99,false)==NULL_IMAGE_VIEW_ID);
    assert(b.GetSamplerId(99,false)==NULL_SAMPLER_ID);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-channel-mapping-") as tmp:
    src=Path(tmp)/"test.cpp"
    src.write_text(fixture)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/opt
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror","-DPS5_NATIVE",
                        str(src),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("PS5_TEXTURE_MAPPING_RECOVERY_PASS",opt)
