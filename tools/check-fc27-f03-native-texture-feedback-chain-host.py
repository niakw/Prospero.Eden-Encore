#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F03: source-extracted TIC/TSC -> graphic descriptor -> feedback-barrier replay.

Compile the actual maintained GetSamplerId, VisitImageView, CheckFeedbackLoop
and GraphicsPipeline descriptor/memo loops in one C++ executable. Exercise
a transient NULL texture, stable HUD draws, remap with unchanged TIC bytes,
depth feedback transitions and an untextured frame. No Vulkan submission,
real GPU fence, image storage, or game frame freshness is certified here.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
tex=(ROOT/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
pipeline=(ROOT/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
old=(ROOT/"tools/check-ps5-texture-channel-missing-mapping-host.py").read_text()
cmake=(ROOT/"headless/vulkan.cmake").read_text()
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
invocation="python3 -B tools/check-fc27-f03-native-texture-feedback-chain-host.py"
assert invocation in fast and invocation in pre
assert 'EDEN_ACTIVE_VULKAN' in cmake and 'vulkan-cache' in cmake
assert 'vk_graphics_pipeline' in cmake and '_cost.cpp' in cmake
def excerpt(src,a,b):
    assert src.count(a)==1,a
    p=src.index(a)
    return src[p:src.index(b,p)]
sampler=excerpt(tex,"template <class P>\nSamplerId TextureCache<P>::GetSamplerId(",
                "\ntemplate <class P>\nconst typename P::Sampler& TextureCache<P>::GetSampler(")
image=excerpt(tex,"template <class P>\nImageViewId TextureCache<P>::VisitImageView(",
              "\ntemplate <class P>\nFramebufferId TextureCache<P>::GetFramebufferId(")
feedback=excerpt(tex,"template <class P>\nvoid TextureCache<P>::CheckFeedbackLoop(",
                 "\ntemplate <class P>\ntypename P::Sampler* TextureCache<P>::GetSampler(")
memo_start=pipeline.index("    // Sampler table mapping is stable while the paired guest cache locks are")
memo_end=pipeline.index("    const auto config_stage{[&](size_t stage)",memo_start)
memo=pipeline[memo_start:memo_end]
loop_start=pipeline.index("        for (const auto& desc : info.texture_descriptors)",memo_end)
loop_end=pipeline.index("        if constexpr (Spec::has_images) {",loop_start)
loop=pipeline[loop_start:loop_end]
assert "++texture_bindings_serial" in image
assert "last_feedback_view_ids[i] != views[i].id" in feedback
assert "runtime.BarrierFeedbackLoop();" in feedback
assert "views.push_back({handle.first});" in loop
# Reuse the existing SOURCE-EXTRACTED mapping fixture's ABI declarations
# and extend them with the actual selected feedback-loop method.
prefix=old.split('fixture=r"""',1)[1].split('""" + sampler + image + r"""',1)[0]
assert 'template<class P> struct TextureCache {' in prefix
prefix=prefix.replace("#include <array>","#include <array>\n#include <span>\n#include <vector>")
prefix=prefix.replace("using u32=std::uint32_t;","using u32=std::uint32_t;\nusing u64=std::uint64_t;\nusing ImageId=u32;\nconstexpr unsigned NUM_RT=8;\nnamespace VideoCommon {using SamplerId=u32;}")
before="template<class P> struct TextureCache {"
add="""struct ImageViewInOut {ImageViewId id{};};
struct RenderTargets {
    std::array<ImageViewId,NUM_RT> color_buffer_ids{};
    ImageViewId depth_buffer_id{};
};
struct Runtime {unsigned calls{};void BarrierFeedbackLoop(){++calls;}};
namespace Settings {
struct Toggle {bool GetValue()const{return true;}};
struct Values {Toggle barrier_feedback_loops;};
inline Values values{};
}
"""
prefix=prefix.replace(before,add+before)
anchor="    u32 texture_bindings_serial=0, prepared=0, views_created=0, samplers_found=0;"
assert prefix.count(anchor)==1
extra="""    u64 render_targets_serial{1},last_feedback_loop_serial{},last_feedback_texture_serial{};
    u32 rt_active_mask{1u<<NUM_RT};
    std::array<ImageId,NUM_RT> rt_image_id{};
    ImageId rt_depth_image_id{127};
    RenderTargets render_targets;
    Runtime runtime;
    bool last_feedback_loop_result{};
    std::vector<ImageViewId> last_feedback_view_ids;
"""
prefix=prefix.replace(anchor,anchor+"\n"+extra)
declaration="    ImageViewId VisitImageView(u32,bool);"
assert prefix.count(declaration)==1
prefix=prefix.replace(declaration,declaration+"\n    void CheckFeedbackLoop(std::span<const ImageViewInOut>);")
# Mock GPU allocator must give a distinct view identity after a remap.
original="const ImageViewId view = static_cast<ImageViewId>(descriptor+100);"
assert prefix.count(original)==1
prefix=prefix.replace(original,"const ImageViewId view = static_cast<ImageViewId>(descriptor+100+(views_created>2?views_created-2:0));")
assign="slot_image_views[view]={.image_id=view,.buffer=false};"
assert prefix.count(assign)==1
prefix=prefix.replace(assign,assign+"\n        slot_images[view].flags.remapped=false;")
# Full selected graphics loop follows the live TIC recovery. Its output feeds
# the selected feedback-loop decision immediately, not a stand-alone oracle.
tail=r"""
struct Descriptor {
    std::vector<std::pair<u32,u32>> handles;
    u32 count{};
};
struct Info {std::vector<Descriptor> texture_descriptors;};
struct Output {
    std::vector<ImageViewInOut> views;
    std::vector<u32> samplers;
};
static Output BuildDraw(TextureCache<int>& texture_cache,const Info& info){
    Output output;
    auto& views=output.views;
    auto& samplers=output.samplers;
    const auto read_handle=[](const Descriptor& d,u32 i){return d.handles.at(i);};
__MEMO__
__LOOP__
    return output;
}
int main(){
    TextureCache<int> cache;
    cache.channel.graphics_sampler_table.descriptor=4;
    cache.channel.graphics_image_table.descriptor=27;
    constexpr u32 hud_slot=5;
    cache.fail_first_view_creation=true;
    // TIC unchanged, initial backing absent, then resident on next draw.
    assert(cache.VisitImageView(hud_slot,false)==NULL_IMAGE_VIEW_ID);
    cache.CheckFeedbackLoop(std::span<const ImageViewInOut>{});
    assert(cache.runtime.calls==0);
    assert(cache.VisitImageView(hud_slot,false)==127);
    assert(cache.texture_bindings_serial==1);
    Info draw{{Descriptor{{{127,3},{127,3}},2}}};
    for(unsigned tick=0;tick<60;++tick){
        auto output=BuildDraw(cache,draw);
        assert(output.views.size()==2 && output.samplers.size()==2);
        assert(output.views[0].id==127 && output.views[1].id==127);
        assert(output.samplers[0]==304 && output.samplers[1]==304);
        assert(cache.samplers_found==1);
        cache.CheckFeedbackLoop(output.views);
        assert(cache.runtime.calls==tick+1);
    }
    assert(cache.views_created==2);
    // A remap retires the backing image without changing guest TIC bytes.
    cache.slot_images[127].flags.remapped=true;
    assert(cache.VisitImageView(hud_slot,false)==128);
    assert(cache.texture_bindings_serial==2);
    cache.rt_depth_image_id=128;
    draw.texture_descriptors[0].handles={{128,3},{128,3}};
    const auto revived=BuildDraw(cache,draw);
    cache.CheckFeedbackLoop(revived.views);
    assert(cache.runtime.calls==61);
    assert(cache.VisitImageView(hud_slot,false)==128);
    assert(cache.views_created==3);
    // Same TIC/TSC serial, different bound view -> discard cached true
    // feedback decision, then restore the depth view in the next draw.
    cache.slot_image_views[44].image_id=44;
    draw.texture_descriptors[0].handles={{44,3},{44,3}};
    const auto unrelated=BuildDraw(cache,draw);
    cache.CheckFeedbackLoop(unrelated.views);
    assert(cache.runtime.calls==61);
    draw.texture_descriptors[0].handles={{128,3},{128,3}};
    const auto restored=BuildDraw(cache,draw);
    cache.CheckFeedbackLoop(restored.views);
    assert(cache.runtime.calls==62);
    cache.CheckFeedbackLoop(std::span<const ImageViewInOut>{});
    cache.CheckFeedbackLoop(restored.views);
    assert(cache.runtime.calls==63);
    assert(cache.samplers_found==1);
    std::printf("F03_NATIVE_TIC_DESCRIPTOR_BARRIER_CHAIN_PASS "
                "frames=60 transient_recoveries=1 remapped_recoveries=1 "
                "sampler_lookups=1 barriers=63 native_functions=3 "
                "scope=source_extracted_host_no_gpu_present\n");
}
"""
source=(prefix+sampler+image+feedback+
        tail.replace("__MEMO__",memo).replace("__LOOP__",loop))
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f03-native-chain-") as folder:
    src=Path(folder)/"hud.cpp"
    src.write_text(source)
    for mode in ("-O0","-O2"):
        exe=Path(folder)/("hud"+mode)
        built=subprocess.run([compiler,"-std=c++20",mode,"-DPS5_NATIVE",
                              "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(src),"-o",str(exe)],
                             capture_output=True,text=True,timeout=70)
        assert built.returncode==0,(mode,built.stderr[-5500:])
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        assert result.returncode==0,(mode,result.stdout,result.stderr[-2800:])
        assert "F03_NATIVE_TIC_DESCRIPTOR_BARRIER_CHAIN_PASS" in result.stdout
        print(result.stdout.strip(),mode,flush=True)
print("F03_VULKAN_PRESENT_AND_REAL_HUD_FRESHNESS_UNVERIFIED")
