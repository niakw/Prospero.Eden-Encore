#!/usr/bin/env python3
"""Compile the actual untextured graphics descriptor gate with cache doubles."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
path=root/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp"
src=path.read_text()
sig="bool GraphicsPipeline::ConfigureImpl(bool is_indexed)"
assert src.count(sig)==1
body=src[src.index(sig):src.index("    ::Eden::Performance::CachePhaseTimer stage_texture_phase",src.index(sig))]
begin=body.index("    if (num_image_elements != 0) {")
gate=body[begin:].rstrip()
assert gate=='''    if (num_image_elements != 0) {
        ::Eden::Performance::CachePhaseTimer cost{
            ::Eden::Performance::CachePhase::TextureDescriptorSync};
        texture_cache.SynchronizeDescriptors(false);
    }'''
# Guarding this table sync is legal only when the descriptor count covers
# every texture, texture buffer, image buffer, and read/write image.
constructor=src[src.index("GraphicsPipeline::GraphicsPipeline("):src.index("    fragment_has_color0_output",src.index("GraphicsPipeline::GraphicsPipeline("))]
for kind in ("texture_buffer_descriptors","image_buffer_descriptors"):
    assert "num_image_elements += Shader::NumDescriptors(info->"+kind+");" in constructor
# Sampled and storage-image counts are now recorded once at pipeline
# construction and reused both for TIC gate accounting and per-stage cursors.
assert "const size_t sampled_views = Shader::NumDescriptors(info->texture_descriptors);" in constructor
assert "const size_t storage_views = Shader::NumDescriptors(info->image_descriptors);" in constructor
assert "stage_sampled_view_counts[stage] = sampled_views;" in constructor
assert "stage_storage_view_counts[stage] = storage_views;" in constructor
assert "num_image_elements += sampled_views;" in constructor
assert "num_image_elements += storage_views;" in constructor
# A nontextured pipeline must still proceed into state setup, buffer work,
# guest descriptor queue handling, and render-target/feedback processing.
after=src[src.index(sig):src.index("bool GraphicsPipeline::ConfigureDraw(",src.index(sig))]
for required in ("texture_cache.FillImageViews(", "buffer_cache.UpdateGraphicsBuffers(",
                 "texture_cache.UpdateRenderTargets(", "texture_cache.CheckFeedbackLoop("):
    assert after.count(required)==1
cmake=(root/"headless/vulkan.cmake").read_text()
assert '"${PORT_BUILD_DIR}/vk_graphics_pipeline_cost.cpp"' in cmake
oracle=(root/"tools/prepare-vulkan-port.py").read_text()
assert "phase == 'TextureDescriptorSync'" in oracle
sample=r'''
#include <cassert>
#include <cstddef>
namespace Eden::Performance {
enum class CachePhase { TextureDescriptorSync };
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase) {}
};
}
struct TextureCache {
    unsigned synchronizations=0;
    void SynchronizeDescriptors(bool compute) {
        assert(!compute);
        ++synchronizations;
    }
};
struct GraphicsPipeline {
    std::size_t num_image_elements=0;
    TextureCache texture_cache;
    void Configure() {
''' + gate + r'''
    }
};
int main() {
    GraphicsPipeline plain;
    plain.Configure();
    assert(plain.texture_cache.synchronizations == 0);
    GraphicsPipeline textured;
    textured.num_image_elements=1;
    textured.Configure();
    textured.Configure();
    assert(textured.texture_cache.synchronizations == 2);
    // Descriptor counts may differ between successive pipelines; a
    // later textured draw must not inherit a skipped sync from the last.
    plain.num_image_elements=3;
    plain.Configure();
    assert(plain.texture_cache.synchronizations == 1);
}
'''
# F07 P0.3: native selected stage host buffer gate is replayed verbatim.
header=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
assert "std::array<bool, NUM_STAGES> stage_has_host_buffer_bindings{};" in header
assert "stage_has_host_buffer_bindings[stage] = info->constant_buffer_mask != 0 ||" in constructor
for kind in ("storage_buffers_descriptors", "texture_buffer_descriptors",
             "image_buffer_descriptors"):
    assert "!info->"+kind+".empty()" in constructor
assert "stage_has_image_bindings[stage]" in constructor
assert "PushImageDescriptors(texture_cache, guest_descriptor_queue" in after
start=after.index("        if (stage_has_host_buffer_bindings[stage]) {")
stop=after.index("        const auto& info{stage_infos[stage]};",start)
host_gate=after[start:stop]
assert host_gate.count("buffer_cache.BindHostStageBuffers(stage);")==1
assert "CachePhase::StageHostBuffers" in host_gate
assert oracle.count("'F07 P0.3 omit empty host buffer stage walks'")==1

host_fixture=r'''
#include <array>
#include <cassert>
#include <cstddef>
namespace Eden::Performance {
enum class CachePhase { StageHostBuffers };
struct CachePhaseTimer { explicit CachePhaseTimer(CachePhase) {} };
}
struct BufferCache {
    std::array<unsigned,5> calls{};
    void BindHostStageBuffers(std::size_t stage) { ++calls[stage]; }
};
struct Pipeline {
    std::array<bool,5> stage_has_host_buffer_bindings{};
    BufferCache buffer_cache;
    void Run(std::size_t stage) {
'''+host_gate+r'''
    }
};
int main() {
    Pipeline p;
    for(std::size_t i=0;i<5;++i) p.Run(i);
    for(unsigned v:p.buffer_cache.calls) assert(v==0);
    p.stage_has_host_buffer_bindings={true,true,true,false,false};
    for(std::size_t i=0;i<5;++i) p.Run(i);
    assert(p.buffer_cache.calls[0]==1);
    assert(p.buffer_cache.calls[1]==1);
    assert(p.buffer_cache.calls[2]==1);
    assert(p.buffer_cache.calls[3]==0);
    assert(p.buffer_cache.calls[4]==0);
    p.stage_has_host_buffer_bindings={false,false,false,false,false};
    for(std::size_t i=0;i<5;++i) p.Run(i);
    assert(p.buffer_cache.calls[0]==1);
}
'''
with tempfile.TemporaryDirectory(prefix="encore-f07-stage-buffers-") as tmp:
    cpp=Path(tmp)/"stage.cpp"
    cpp.write_text(host_fixture)
    for optimization in ("-O0","-O2"):
        exe=Path(tmp)/optimization
        subprocess.run(["c++","-std=c++20",optimization,"-Wall","-Wextra",
                        "-Werror",str(cpp),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        print("ENCORE_F07_EMPTY_STAGE_HOST_BUFFERS_PASS",optimization)

with tempfile.TemporaryDirectory(prefix="encore-nontexture-tic-") as tmp:
    cpp=Path(tmp)/"test.cpp"
    cpp.write_text(sample)
    for optimization in ("-O0","-O2"):
        exe=Path(tmp)/optimization
        subprocess.run(["c++","-std=c++20",optimization,"-Wall","-Wextra","-Werror",
                        str(cpp),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        print("ENCORE_UNTEXTURED_GRAPHICS_TIC_SKIP_PASS",optimization)
