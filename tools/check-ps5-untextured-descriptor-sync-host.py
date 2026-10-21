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
for kind in ("texture_buffer_descriptors","image_buffer_descriptors",
             "texture_descriptors","image_descriptors"):
    assert "num_image_elements += Shader::NumDescriptors(info->"+kind+");" in constructor
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
with tempfile.TemporaryDirectory(prefix="encore-nontexture-tic-") as tmp:
    cpp=Path(tmp)/"test.cpp"
    cpp.write_text(sample)
    for optimization in ("-O0","-O2"):
        exe=Path(tmp)/optimization
        subprocess.run(["c++","-std=c++20",optimization,"-Wall","-Wextra","-Werror",
                        str(cpp),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        print("ENCORE_UNTEXTURED_GRAPHICS_TIC_SKIP_PASS",optimization)
