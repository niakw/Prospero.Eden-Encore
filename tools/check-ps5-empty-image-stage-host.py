#!/usr/bin/env python3
"""Compile the native graphics stage fast path with real extracted code, O0/O2."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
hdr=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
constructor=src[src.index("        stage_infos[stage] = *info;"):src.index("        enabled_uniform_buffer_masks[stage]",src.index("        stage_infos[stage] = *info;"))]
b=src.index("    const auto prepare_stage{[&](size_t stage) LAMBDA_FORCEINLINE {")
e=src.index("    }};",b)+len("    }};")
stage_code=src[b:e]
assert src.count("if (stage_has_image_bindings[stage]) {")==1
assert hdr.count("std::array<bool, NUM_STAGES> stage_has_image_bindings{};")==1
assert hdr.count("std::array<bool, NUM_STAGES> stage_has_host_buffer_bindings{};")==1
assert "stage_has_host_buffer_bindings[stage] = info->constant_buffer_mask != 0 ||" in constructor
for desc in ("storage_buffers_descriptors", "texture_buffer_descriptors", "image_buffer_descriptors"):
    assert "!info->"+desc+".empty()" in constructor
assert "if (stage_has_host_buffer_bindings[stage]) {" in stage_code
for desc in ("texture_buffer_descriptors","image_buffer_descriptors","texture_descriptors","image_descriptors"):
    assert "info->"+desc+".empty()" in constructor
assert stage_code.index("buffer_cache.BindHostStageBuffers(stage);") < stage_code.index("if (stage_has_image_bindings[stage])")
assert stage_code.index("const auto& info{stage_infos[stage]};") < stage_code.index("PushImageDescriptors(")
assert "PushImageDescriptors(texture_cache, guest_descriptor_queue, info, rescaling," in stage_code
assert stage_code.count("CachePhase::StageHostBuffers") == 1
assert stage_code.count("CachePhase::StageImageDescriptors") == 1
oracle=(root/"tools/prepare-vulkan-port.py").read_text()
assert "Source-proven no-image stage fast path" in oracle
assert "std::array<bool, NUM_STAGES> stage_has_image_bindings{};" in oracle
assert "F07 P0.3 host stage mask in pipeline header" in oracle
assert "F07 P0.3 omit empty host buffer stage walks" in oracle
cpp=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <vector>
#define LAMBDA_FORCEINLINE
struct Info {
    unsigned constant_buffer_mask=0;
    std::vector<int> storage_buffers_descriptors;
    std::vector<int> texture_buffer_descriptors;
    std::vector<int> image_buffer_descriptors;
    std::vector<int> texture_descriptors;
    std::vector<int> image_descriptors;
    bool uses_render_area=false;
};
namespace Shader { using Info=::Info; }
struct BufferCache {
    unsigned calls{};
    void BindHostStageBuffers(std::size_t) { ++calls; }
};
struct Clip { int width=1920,height=1080; };
struct Registers { Clip surface_clip; };
struct Engine { Registers regs; };
struct RenderArea { bool uses_render_area=false; std::array<float,2> words{}; };
struct Rescaling {};
struct TextureCache {};
struct GuestDescriptorQueue {};
// The shipping source uses detailed-only phase timers. The extracted stage
// fixture tests binding order/semantics, so provide a no-op timer for it.
namespace Eden::Performance {
enum class CachePhase { StageHostBuffers, StageImageDescriptors };
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase) noexcept {}
};
}
using SamplerId=int;
using ViewId=int;
inline unsigned push_calls=0;
void PushImageDescriptors(TextureCache&,GuestDescriptorQueue&,const Info& info,
                          Rescaling&,const SamplerId*& samplers_it,const ViewId*& views_it) {
    ++push_calls;
    views_it += info.texture_buffer_descriptors.size()+info.image_buffer_descriptors.size()+
                info.texture_descriptors.size()+info.image_descriptors.size();
    samplers_it += info.texture_descriptors.size();
}
struct Pipeline {
    static constexpr std::size_t NUM_STAGES=5;
    std::array<Info,NUM_STAGES> stage_infos{};
    std::array<bool,NUM_STAGES> stage_has_image_bindings{};
    std::array<bool,NUM_STAGES> stage_has_host_buffer_bindings{};
    BufferCache buffer_cache;
    TextureCache texture_cache;
    GuestDescriptorQueue guest_descriptor_queue;
    Engine engine;
    Engine* maxwell3d=&engine;
    RenderArea render_area;
    Rescaling rescaling;
    std::array<SamplerId,16> samplers{};
    std::array<ViewId,16> views{};
    const SamplerId* samplers_it=samplers.data();
    const ViewId* views_it=views.data();
    void Init(std::size_t stage, const Info* info) {
""" + constructor + r"""
    }
    void DrawStage(std::size_t stage) {
        const auto& regs=maxwell3d->regs;
""" + stage_code + r"""
        prepare_stage(stage);
    }
};
int main() {
    Pipeline p;
    Info empty;
    empty.uses_render_area=true;
    p.Init(0,&empty);
    assert(!p.stage_has_image_bindings[0]);
    assert(!p.stage_has_host_buffer_bindings[0]);
    p.DrawStage(0);
    assert(p.buffer_cache.calls==0 && push_calls==0);
    assert(p.views_it==p.views.data() && p.samplers_it==p.samplers.data());
    assert(p.render_area.uses_render_area);
    Info buffer_only;
    buffer_only.texture_buffer_descriptors={1,2};
    p.Init(1,&buffer_only);
    assert(p.stage_has_image_bindings[1]);
    assert(p.stage_has_host_buffer_bindings[1]);
    p.DrawStage(1);
    assert(p.buffer_cache.calls==1 && push_calls==1);
    assert(p.views_it==p.views.data()+2 && p.samplers_it==p.samplers.data());
    Info sampled;
    sampled.texture_descriptors={1,2,3};
    p.Init(2,&sampled);
    assert(p.stage_has_image_bindings[2]);
    assert(!p.stage_has_host_buffer_bindings[2]);
    p.DrawStage(2);
    assert(p.buffer_cache.calls==1 && push_calls==2);
    assert(p.views_it==p.views.data()+5 && p.samplers_it==p.samplers.data()+3);
    Info images;
    images.image_descriptors={1};
    p.Init(3,&images);
    assert(!p.stage_has_host_buffer_bindings[3]);
    p.DrawStage(3);
    assert(p.buffer_cache.calls==1 && p.views_it==p.views.data()+6 && push_calls==3);
    Info image_buffers;
    image_buffers.image_buffer_descriptors={1,2};
    p.Init(4,&image_buffers);
    assert(p.stage_has_host_buffer_bindings[4]);
    p.DrawStage(4);
    assert(p.buffer_cache.calls==2 && p.views_it==p.views.data()+8 && push_calls==4);
    // Uniform-only and SSBO-only shaders must keep host bindings active.
    Info uniform;
    uniform.constant_buffer_mask=1;
    p.Init(0,&uniform);
    assert(p.stage_has_host_buffer_bindings[0] && !p.stage_has_image_bindings[0]);
    p.DrawStage(0);
    assert(p.buffer_cache.calls==3 && push_calls==4);
    Info ssbo;
    ssbo.storage_buffers_descriptors={1};
    p.Init(2,&ssbo);
    assert(p.stage_has_host_buffer_bindings[2] && !p.stage_has_image_bindings[2]);
    p.DrawStage(2);
    assert(p.buffer_cache.calls==4 && push_calls==4);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-empty-graphics-stage-") as tmp:
    p=Path(tmp)/"main.cpp"
    p.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/opt
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        str(p),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("ENCORE_EMPTY_GRAPHICS_STAGE_HOST_PASS",opt)


# F07 P0.4: unlike a pure loop, FillImageViews() resets the global
# deletion/retry latch on *every* call, including an empty graphics pass.
# Compute preserves this contract already. Use the exact selected graphics
# call block and compile zero/populated/zero transitions at O0 and O2.
texture_header=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
fill_start=texture_header.index("void TextureCache<P>::FillImageViews(")
fill_end=texture_header.index("void TextureCache<P>::CheckFeedbackLoop(",fill_start)
fill_source=texture_header[fill_start:fill_end]
assert fill_source.index("has_deleted_images = false;") < fill_source.index("for (ImageViewInOut& view : views)")
draw_start=src.index("bool GraphicsPipeline::ConfigureImpl(")
draw_end=src.index("bool GraphicsPipeline::ConfigureDraw(",draw_start)
draw_source=src[draw_start:draw_end]
image_start=draw_source.index("    // FillImageViews resets the image-deletion/retry latch")
image_end=draw_source.index("\n\n    ::Eden::Performance::CachePhaseTimer bind_texture_phase",image_start)
image_call=draw_source[image_start:image_end]
assert image_call.count("texture_cache.FillImageViews(")==1
assert "if (!views.empty())" not in image_call
assert "CachePhase::TextureFillImageViews" in image_call
assert "FillImageViews resets the image-deletion/retry latch" in (root/"tools/check-vendored-vulkan-fork.py").read_text()
empty_views_cpp=r"""
#include <cassert>
#include <span>
#include <vector>
struct ImageViewInOut { int id{}; };
namespace Eden::Performance {
enum class CachePhase { TextureFillImageViews };
struct CachePhaseTimer { explicit CachePhaseTimer(CachePhase) noexcept {} };
}
struct TextureCache {
    bool has_deleted_images{true};
    unsigned calls{}, lookups{};
    void FillImageViews(std::span<ImageViewInOut> views, bool compute, bool blacklist) {
        assert(!compute && !blacklist);
        ++calls;
        has_deleted_images = false;
        for (auto& view : views) { ++lookups; view.id = 11; }
    }
};
struct Spec { static constexpr bool has_images = false; };
struct Graphics {
    TextureCache texture_cache;
    std::vector<ImageViewInOut> views;
    void Configure() {
""" + image_call + r"""
    }
};
int main() {
    Graphics g;
    g.Configure();
    assert(!g.texture_cache.has_deleted_images && g.texture_cache.calls==1);
    g.texture_cache.has_deleted_images=true;
    g.views.resize(2);
    g.Configure();
    assert(!g.texture_cache.has_deleted_images && g.texture_cache.calls==2);
    assert(g.texture_cache.lookups==2 && g.views[0].id==11);
    g.texture_cache.has_deleted_images=true;
    g.views.clear();
    g.Configure();
    assert(!g.texture_cache.has_deleted_images && g.texture_cache.calls==3);
    assert(g.texture_cache.lookups==2);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-graphics-empty-latch-") as tmp:
    p=Path(tmp)/"view.cpp"
    p.write_text(empty_views_cpp)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/("view"+opt[1:])
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined",str(p),"-o",str(exe)],
                       check=True,timeout=30,capture_output=True,text=True)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("ENCORE_F07_EMPTY_GRAPHICS_VIEW_LATCH_PASS",opt)
