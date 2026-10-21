#!/usr/bin/env python3
"""Compile native precomputed per-stage descriptor counts, preserving view cursors."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
cpp=(root/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
hdr=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
start=cpp.index("        num_image_elements += Shader::NumDescriptors(info->texture_buffer_descriptors);")
end=cpp.index("        num_descriptor_entries += NumDescriptorEntries(*info);",start)
ctor=cpp[start:end]
assert ctor.count("stage_sampled_view_counts[stage] = sampled_views;")==1
assert ctor.count("stage_storage_view_counts[stage] = storage_views;")==1
assert ctor.count("Shader::NumDescriptors(info->texture_descriptors)")==1
assert ctor.count("Shader::NumDescriptors(info->image_descriptors)")==1
start=cpp.index("        // Stage descriptor counts were recorded during construction,")
end=cpp.index("    }};",start)
advance=cpp[start:end]
assert advance.count("stage_sampled_view_counts[stage]")==1
assert advance.count("stage_storage_view_counts[stage]")==1
assert "if constexpr (Spec::has_images)" in advance
for declaration in ("std::array<size_t, NUM_STAGES> stage_sampled_view_counts{};",
                    "std::array<size_t, NUM_STAGES> stage_storage_view_counts{};"):
    assert hdr.count(declaration)==1
gen=(root/"tools/prepare-vulkan-port.py").read_text()
assert "Pipeline construction precomputes immutable descriptor cursor" in gen
assert "stage_sampled_view_counts[stage] = sampled_views;" in gen
assert "stage_storage_view_counts[stage] = storage_views;" in gen
cmake=(root/"headless/vulkan.cmake").read_text()
assert '"${PORT_BUILD_DIR}/vk_graphics_pipeline_cost.cpp"' in cmake
host=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
struct Descriptor { unsigned count{}; };
struct Info {
    std::vector<Descriptor> texture_buffer_descriptors;
    std::vector<Descriptor> image_buffer_descriptors;
    std::vector<Descriptor> texture_descriptors;
    std::vector<Descriptor> image_descriptors;
};
namespace Shader {
    template<class V> std::size_t NumDescriptors(const V& descriptors) {
        std::size_t n=0;
        for(const auto& desc:descriptors)n+=desc.count;
        return n;
    }
}
template <bool Images>
struct Spec {
    static constexpr bool has_images=Images;
};
struct Pipeline {
    static constexpr size_t NUM_STAGES=5;
    std::array<size_t,NUM_STAGES> stage_sampled_view_counts{};
    std::array<size_t,NUM_STAGES> stage_storage_view_counts{};
    std::array<Info,NUM_STAGES> info_by_stage{};
    size_t num_image_elements=0, num_textures=0;
    int views[4096]{};
    int* texture_buffer_it=views;
    void Add(std::size_t stage,const Info* info) {
        info_by_stage[stage]=*info;
""" + ctor + r"""
    }
    template<class Spec>
    void Advance(std::size_t stage) {
""" + advance + r"""
    }
};
int main() {
    for(unsigned seed=0;seed<96;++seed) {
        Pipeline x;
        size_t expected_image_total=0, expected_textures=0;
        std::array<std::size_t,5> expected_sampled{}, expected_images{};
        for(std::size_t stage=0;stage<5;++stage) {
            Info info;
            for(unsigned k=0;k<4;++k) {
                const unsigned value=(seed*13+static_cast<unsigned>(stage)*7+k*11)%5;
                if(k==0)info.texture_buffer_descriptors.push_back({value});
                if(k==1)info.image_buffer_descriptors.push_back({value});
                if(k==2)info.texture_descriptors.push_back({value});
                if(k==3)info.image_descriptors.push_back({value});
            }
            x.Add(stage,&info);
            expected_sampled[stage]=Shader::NumDescriptors(info.texture_descriptors);
            expected_images[stage]=Shader::NumDescriptors(info.image_descriptors);
            expected_textures+=expected_sampled[stage];
            expected_image_total+=
                Shader::NumDescriptors(info.texture_buffer_descriptors)+
                Shader::NumDescriptors(info.image_buffer_descriptors)+
                expected_sampled[stage]+expected_images[stage];
        }
        assert(x.num_textures==expected_textures && x.num_image_elements==expected_image_total);
        std::size_t cursor_expected=0;
        for(std::size_t stage=0;stage<5;++stage) {
            x.Advance<Spec<true>>(stage);
            cursor_expected+=expected_sampled[stage]+expected_images[stage];
            assert(x.texture_buffer_it==x.views+cursor_expected);
        }
        x.texture_buffer_it=x.views;
        cursor_expected=0;
        for(std::size_t stage=0;stage<5;++stage) {
            x.Advance<Spec<false>>(stage);
            cursor_expected+=expected_sampled[stage];
            assert(x.texture_buffer_it==x.views+cursor_expected);
        }
    }
}
"""
with tempfile.TemporaryDirectory(prefix="encore-descriptor-stage-counts-") as tmp:
    f=Path(tmp)/"fixture.cpp";f.write_text(host)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/opt
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        str(f),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("GRAPHICS_STAGE_VIEW_CURSOR_HOST_PASS",opt)
