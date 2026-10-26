#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F04: one C++20 remap/DMA/cache-alias/upload content-lifetime replay.

Reuse the existing selected Vulkan refresh host fixture, injecting the actual
selected MaxwellDMA contiguous-pitch body plus TextureCache::WriteMemory,
UnmapGPUMemory and SynchronizeAliases. The SAME mock guest bytes feed DMA,
cache invalidation and upload into one image. A simulated guest address rebind
after the native UnmapGPUMemory call must deliver a new image revision, not
the old GPU view contents. The mapping transport, GPU, WSI and formats beyond
the existing unswizzle mock are NOT device verified.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
cache=(ROOT/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
dma=(ROOT/"vendor/encore-active/eden-core/src/video_core/engines/maxwell_dma.cpp").read_text()
base=(ROOT/"tools/check-fc27-f04-native-upload-revision-host.py").read_text()
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
ci="python3 -B tools/check-fc27-f04-native-remap-dma-upload-chain-host.py"
assert ci in fast and ci in pre
assert "vulkan-cache" in (ROOT/"headless/vulkan.cmake").read_text()

def extract(text,start,end):
    assert text.count(start)==1,(start,text.count(start))
    pos=text.index(start)
    assert end in text[pos:],end
    return text[pos:text.index(end,pos)]

methods=extract(cache,
    "template <class P>\nvoid TextureCache<P>::RefreshContents(",
    "\ntemplate <class P>\nImageViewId TextureCache<P>::CreateImageView(")
write=extract(cache,"void TextureCache<P>::WriteMemory(DAddr cpu_addr, size_t size) {",
              "\ntemplate <class P>\nbool TextureCache<P>::IsDownloadable(")
unmap=extract(cache,"void TextureCache<P>::UnmapGPUMemory(size_t as_id, GPUVAddr gpu_addr, size_t size) {",
              "\ntemplate <class P>\nbool TextureCache<P>::BlitImage(")
alias=extract(cache,"void TextureCache<P>::SynchronizeAliases(ImageId image_id) {",
              "\ntemplate <class P>\nvoid TextureCache<P>::PrepareImage(")
coalesce=extract(dma,"constexpr bool CanCoalescePitchDma(","\n}\n} // namespace")+"\n}"
launch=extract(dma,"void MaxwellDMA::Launch() {","\nvoid MaxwellDMA::CopyBlockLinearToPitch()")
pitch=extract(launch,"            u64 contiguous_bytes = 0;\n            if (CanCoalescePitchDma(",
             "        } else {\n            if (!is_src_pitch && is_dst_pitch)")
assert 'image.flags |= ImageFlagBits::Remapped;' in unmap
assert 'image.flags |= ImageFlagBits::CpuModified;' in write
assert 'CopyImage(image_id, aliased->id, aliased->copies);' in alias
assert 'runtime.InsertUploadMemoryBarrier();' in methods
assert 'memory_manager.CopyBlock(regs.offset_out, regs.offset_in' in pitch

# This existing fixture has already compiled both selected upload methods at
# O0 and O2; retain its mocks and assertions to catch fixture drift.
prefix='cpp = r"""'
suffix='""".replace("__METHODS__",method)'
assert base.count(prefix)==base.count(suffix)==1
cpp=base.split(prefix,1)[1].split(suffix,1)[0]
def replace_once(old,new,label):
    global cpp
    n=cpp.count(old)
    assert n==1,(label,n)
    cpp=cpp.replace(old,new)

replace_once('#include <memory>\n','#include <memory>\n#include <ranges>\n',"headers")
replace_once('using u8 = std::uint8_t;\nusing u64 = std::uint64_t;',
             'using u8 = std::uint8_t;\nusing u32 = std::uint32_t;\nusing u64 = std::uint64_t;\nusing s64 = std::int64_t;\nusing DAddr = u64;\nusing ImageViewId = std::size_t;\nconstexpr ImageViewId NULL_IMAGE_VIEW_ID = 0;\nconstexpr std::size_t NUM_RT = 4;\nnamespace Dirty {constexpr std::size_t ZetaBuffer=0,ColorBuffer0=1,RenderTargets=10;}\nnamespace boost::container {template<class T,std::size_t N> using small_vector=std::vector<T>;}',
             "types")
replace_once('    Converted=16\n};',
             '    Converted=16,Tracked=32,Rescaled=64,Remapped=128\n};',
             "flags enum")
replace_once('    Flags& operator&=(unsigned mask){bits &= mask;return *this;}\n};',
             '    Flags& operator&=(unsigned mask){bits &= mask;return *this;}\n    Flags& operator|=(ImageFlagBits bit){bits|=static_cast<unsigned>(bit);return *this;}\n};',
             "flags op")
replace_once('struct Image {\n',
             '''struct ImageCopy {std::size_t dst_offset{},src_offset{},length{};};
struct AliasedImage {ImageId id{};std::vector<ImageCopy> copies{};};
struct Image {
''',"image alias")
replace_once('    GPUVAddr gpu_addr=128;\n',
             '    GPUVAddr gpu_addr=128;\n    DAddr cpu_addr=0;\n    u64 modification_tick=0;\n    std::vector<ImageViewId> image_view_ids;\n    std::vector<AliasedImage> aliased_images;\n',
             "image fields")
replace_once('};\nnamespace Settings {\n',
             '};\nusing ImageBase=Image;\nstruct Maxwell {struct DirtyState {std::array<bool,16> flags{};} dirty;};\nstruct FramebufferState {ImageViewId depth_buffer_id{};std::array<ImageViewId,NUM_RT> color_buffer_ids{};};\nnamespace Settings {\n',"maxwell")
replace_once('struct Values {Toggle gpu_unswizzle_enabled;};',
             'struct Resolution {bool active=false;};\nstruct Values {Toggle gpu_unswizzle_enabled;Resolution resolution_info;};',
             "resolution")
replace_once('    std::array<u8,256> bytes{};\n    unsigned read_calls=0;',
             '''    std::array<u8,4096> bytes{};
    unsigned read_calls=0, dma_calls=0;
    void CopyBlock(u64 dst,u64 src,std::size_t count) {
        assert(dst<=bytes.size() && src<=bytes.size());
        assert(count<=bytes.size()-dst && count<=bytes.size()-src);
        std::memmove(bytes.data()+dst,bytes.data()+src,count);
        ++dma_calls;
    }''',"gpu bytes")
# Reuse the same diagnostics-aware upload fixture as the F04 upload test.
# TextureCpuRefresh, alias counters and the three new F07 upload stages are
# all no-op host counters; do not rewrite the fixture's timer vocabulary.
assert "TextureAliasScan" in cpp and "TextureUploadStaging" in cpp
assert "void Stop() noexcept {}" in cpp
replace_once('    Runtime runtime{};\n',
             '''    Runtime runtime{};
    std::vector<Image> slot_images{3};
    Maxwell maxwell_instance{};
    Maxwell* maxwell3d=&maxwell_instance;
    FramebufferState render_targets{};
    u64 modification_tick=0;
    unsigned copy_count=0,untrack_count=0;
    std::vector<ImageId> copy_order;
    template<class F> void ForEachImageInRegion(DAddr cpu,size_t size,F visit){
        for(ImageId i=0;i<slot_images.size();++i) {
            Image& img=slot_images[i];
            if(size && cpu<img.cpu_addr+64 && img.cpu_addr<cpu+size)visit(i,img);
        }
    }
    template<class F> void ForEachImageInRegionGPU(std::size_t,GPUVAddr gpu,size_t size,F visit){
        for(ImageId i=0;i<slot_images.size();++i){
            Image& img=slot_images[i];
            if(size && gpu<img.gpu_addr+64 && img.gpu_addr<gpu+size)visit(i,img);
        }
    }
    bool ImageCanRescale(Image&){return true;}
    void ScaleUp(Image&){}
    void ScaleDown(Image&){}
    void CopyImage(ImageId dst_id,ImageId src_id,std::vector<ImageCopy> spans){
        assert(src_id<slot_images.size() && dst_id<slot_images.size());
        auto& dst=slot_images[dst_id].device_bytes;
        const auto& src=slot_images[src_id].device_bytes;
        for(const auto& span:spans){
            assert(span.dst_offset<=dst.size() && span.src_offset<=src.size());
            assert(span.length<=dst.size()-span.dst_offset);
            assert(span.length<=src.size()-span.src_offset);
            std::copy_n(src.begin()+span.src_offset,span.length,dst.begin()+span.dst_offset);
        }
        ++copy_count;
        copy_order.push_back(src_id);
    }
    void UntrackImage(Image& img,ImageId){
        img.flags.bits &= ~static_cast<unsigned>(ImageFlagBits::Tracked);
        ++untrack_count;
    }
''',"cache methods")
replace_once('    void TrackImage(Image&,ImageId){++tracked;}',
             '    void TrackImage(Image& img,ImageId){++tracked;img.flags |= ImageFlagBits::Tracked;}',
             "tracked")
replace_once('    void RefreshContents(Image&,ImageId);\n',
             '    void RefreshContents(Image&,ImageId);\n    void WriteMemory(DAddr,size_t);\n    void UnmapGPUMemory(size_t,GPUVAddr,size_t);\n    void SynchronizeAliases(ImageId);\n',"declarations")
replace_once('__METHODS__\n',
             '''__METHODS__
struct DmaRegs {
    u64 offset_in{},offset_out{};
    u32 line_length_in{},line_count{};
    s64 pitch_in{},pitch_out{};
};
__COALESCE__
struct MockDma {
    DmaRegs regs{};
    Memory& memory_manager;
    explicit MockDma(Memory& m):memory_manager(m){}
    void PitchCopy(){
__PITCH__
    }
};
template<class P>
__ALIAS__
template<class P>
__WRITE__
template<class P>
__UNMAP__
''',"integrated methods")
# Use a single source-extracted end-to-end path, then keep all earlier
# standalone upload assertions as regressions in the same compiled fixture.
replace_once('int main(){\n    TextureCache<int> cache;',
             '''static void IntegratedRemapDmaUpload(){
    TextureCache<int> cache;
    Image& img=cache.slot_images[0];
    img.cpu_addr=0x1000;
    img.gpu_addr=128;
    cache.slot_images[1].cpu_addr=0x2000;
    cache.slot_images[1].gpu_addr=1536;
    cache.slot_images[2].cpu_addr=0x3000;
    cache.slot_images[2].gpu_addr=1664;
    cache.runtime.image_to_verify=&img;
    for(std::size_t i=0;i<cache.memory.bytes.size();++i)
        cache.memory.bytes[i]=static_cast<u8>((i*19+41)%251);
    MockDma dma{cache.memory};
    dma.regs={768,128,16,4,16,16};
    dma.PitchCopy();
    assert(cache.memory.dma_calls==1);
    cache.WriteMemory(img.cpu_addr,64);
    assert(True(img.flags & ImageFlagBits::CpuModified));
    cache.runtime.expected=Data(cache.memory,128);
    cache.RefreshContents(img,0);
    assert(img.device_bytes==cache.runtime.expected);
    assert(img.uploads==1 && cache.runtime.barriers==1);
    // Two GPU-side aliases, published in modification order. The regions
    // not covered by either alias must retain bytes from this same DMA upload.
    img.modification_tick=1;
    cache.modification_tick=7;
    auto& a=cache.slot_images[1];
    auto& b=cache.slot_images[2];
    a.modification_tick=4;b.modification_tick=7;
    a.flags |= ImageFlagBits::GpuModified;
    b.flags |= ImageFlagBits::GpuModified;
    a.device_bytes.fill(0x59);
    b.device_bytes.fill(0xD7);
    img.aliased_images={{2,{{48,0,8}}},{1,{{0,0,32}}}};
    const auto base_contents=img.device_bytes;
    cache.SynchronizeAliases(0);
    assert((cache.copy_order==std::vector<ImageId>{1,2}));
    assert(img.modification_tick==7 && cache.copy_count==2);
    for(std::size_t i=0;i<32;++i)assert(img.device_bytes[i]==0x59);
    for(std::size_t i=32;i<48;++i)assert(img.device_bytes[i]==base_contents[i]);
    for(std::size_t i=48;i<56;++i)assert(img.device_bytes[i]==0xD7);
    for(std::size_t i=56;i<64;++i)assert(img.device_bytes[i]==base_contents[i]);
    cache.SynchronizeAliases(0);
    assert(cache.copy_count==2);
    // The native unmapped-image path must retire the old GPU view, mark
    // its CPU contents for refresh and dirty any attached depth/color RT.
    img.image_view_ids={1,2};
    cache.render_targets.depth_buffer_id=1;
    cache.render_targets.color_buffer_ids[0]=2;
    cache.UnmapGPUMemory(0,128,64);
    assert(True(img.flags & ImageFlagBits::Remapped));
    assert(True(img.flags & ImageFlagBits::CpuModified));
    assert(cache.untrack_count==1);
    assert(cache.maxwell3d->dirty.flags[Dirty::RenderTargets]);
    assert(cache.maxwell3d->dirty.flags[Dirty::ZetaBuffer]);
    assert(cache.maxwell3d->dirty.flags[Dirty::ColorBuffer0]);
    // Mock address-rebind transport: its subsequent guest data comes from a
    // different GPU backing, never from old aliased GPU image bytes.
    img.gpu_addr=256;
    dma.regs={896,256,16,4,16,16};
    dma.PitchCopy();
    assert(cache.memory.dma_calls==2);
    cache.runtime.expected=Data(cache.memory,256);
    cache.RefreshContents(img,0);
    assert(img.device_bytes==cache.runtime.expected);
    assert(img.uploads==2 && cache.runtime.barriers==2);
    assert(cache.runtime.expected!=base_contents);
    // Repeated write to the same guest address must invalidate that same
    // cached mapping and publish the latest DMA revision, not the old view.
    dma.regs={1024,256,16,4,16,16};
    dma.PitchCopy();
    cache.WriteMemory(img.cpu_addr,64);
    cache.runtime.expected=Data(cache.memory,256);
    cache.RefreshContents(img,0);
    assert(cache.memory.dma_calls==3);
    assert(img.device_bytes==cache.runtime.expected);
    assert(img.uploads==3 && cache.runtime.barriers==3);
    assert(cache.copy_count==2); // remap did not secretly reuse stale aliases
    std::puts("F04_NATIVE_REMAP_DMA_UPLOAD_CHAIN_PASS dma_copies=3 "
              "alias_copies=2 remaps=1 revisions=3 barriers=3 "
              "scope=source_extracted_host_mock_address_rebind_and_gpu_bytes");
}
int main(){
    IntegratedRemapDmaUpload();
    TextureCache<int> cache;''',"call main")
cpp=cpp.replace("__METHODS__",methods).replace("__COALESCE__",coalesce)
cpp=cpp.replace("__PITCH__",pitch).replace("__ALIAS__",alias)
cpp=cpp.replace("__WRITE__",write).replace("__UNMAP__",unmap)
assert not any(v in cpp for v in ("__METHODS__","__COALESCE__","__PITCH__","__ALIAS__","__WRITE__","__UNMAP__"))
assert cpp.count("void TextureCache<P>::UnmapGPUMemory(")==1
assert cpp.count("void TextureCache<P>::RefreshContents(")==1
assert cpp.count("void TextureCache<P>::SynchronizeAliases(")==1

compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f04-fullchain-") as work:
    source=Path(work)/"chain.cpp"
    source.write_text(cpp)
    for level in ("-O0","-O2"):
        binary=Path(work)/("chain"+level)
        compiled=subprocess.run([compiler,"-std=c++20",level,
            "-DPS5_NATIVE=1","-Wall","-Wextra","-Werror",
            "-fsanitize=undefined","-fno-sanitize-recover=all",str(source),
            "-o",str(binary)],capture_output=True,text=True,timeout=80)
        assert compiled.returncode==0,(level,compiled.stderr[-7000:])
        run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
        assert run.returncode==0,(level,run.stdout,run.stderr[-7000:])
        assert "F04_NATIVE_REMAP_DMA_UPLOAD_CHAIN_PASS" in run.stdout
        assert "F04_NATIVE_TEXTURE_UPLOAD_REVISION_PASS" in run.stdout
        print(run.stdout.strip(),level,flush=True)
print("F04_REAL_VULKAN_PIXELS_AND_GPU_ADDRESS_REBIND_UNVERIFIED")
