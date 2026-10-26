#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F04: execute native CPU-modified texture refresh and upload-byte handoff.

Extract RefreshContents and UploadImageContents from the CMake-selected Vulkan
texture cache. Mock the GPU image/staging allocator and elementary format
decoder to verify ordering, byte revisions and branches under UBSan at O0/O2.
This does not verify a hardware Vulkan transfer, image formats or FC27 pixels.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
path = ROOT/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h"
src = path.read_text()
cmake = (ROOT/"headless/vulkan.cmake").read_text()
fast = (ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre = (ROOT/".github/workflows/encore-core-preflight.yml").read_text()
invocation = "python3 -B tools/check-fc27-f04-native-upload-revision-host.py"
assert invocation in fast and invocation in pre
assert 'EDEN_ACTIVE_VULKAN' in cmake and 'vulkan-cache' in cmake
start = "template <class P>\nvoid TextureCache<P>::RefreshContents("
end = "\ntemplate <class P>\nImageViewId TextureCache<P>::CreateImageView("
assert src.count(start) == src.count(end) == 1
method = src[src.index(start):src.index(end,src.index(start))]
assert "UploadImageContents(image, staging);" in method
assert "runtime.InsertUploadMemoryBarrier();" in method
assert "gpu_memory->ReadBlock" in method
assert "ConvertImage(unswizzle_data_buffer" in method
assert "image.UploadMemory(staging, copies);" in method
assert method.count("image.flags &= ~ImageFlagBits::CpuModified;")==1
assert "QueueAsyncDecode(image, image_id);" in method

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <span>
#include <utility>
#include <vector>
using u8 = std::uint8_t;
using u64 = std::uint64_t;
using GPUVAddr = u64;
using ImageId = std::size_t;
enum class ImageFlagBits : unsigned {
    CpuModified=1,AsynchronousDecode=2,GpuModified=4,AcceleratedUpload=8,
    Converted=16
};
struct Flags {
    unsigned bits{};
    Flags& operator&=(unsigned mask){bits &= mask;return *this;}
};
constexpr unsigned operator~(ImageFlagBits b){return ~static_cast<unsigned>(b);}
inline bool True(Flags f,ImageFlagBits bit){return (f.bits&static_cast<unsigned>(bit))!=0;}
inline bool False(Flags f,ImageFlagBits bit){return !True(f,bit);}
inline bool True(unsigned b){return b!=0;}
inline bool False(unsigned b){return b==0;}
constexpr unsigned operator&(Flags f,ImageFlagBits b) {
    return f.bits & static_cast<unsigned>(b);
}
constexpr unsigned operator&(Flags f,unsigned b){return f.bits&b;}
struct Info {
    unsigned num_samples=1;
    unsigned format=0;
    enum class Type{e2D,e3D} type=Type::e2D;
    struct Resources {int levels=1,layers=1;} resources;
};
using ImageType = Info::Type;
struct Buffer {
    std::vector<u8> values;
    void resize_destructive(std::size_t size){values.resize(size);}
    operator std::span<u8>(){return values;}
};
struct Staging {
    std::shared_ptr<std::vector<u8>> data;
    std::span<u8> mapped_span;
    explicit Staging(std::size_t n):data(std::make_shared<std::vector<u8>>(n)),mapped_span(*data){}
};
struct Image {
    Flags flags{};
    Info info{};
    GPUVAddr gpu_addr=128;
    std::size_t guest_size_bytes=64,unswizzled_size_bytes=64;
    std::array<u8,64> device_bytes{};
    unsigned uploads=0;
    template<class Copies>
    void UploadMemory(Staging& staging, const Copies& copies) {
        assert(copies.size()==1);
        assert(staging.mapped_span.size_bytes()==device_bytes.size());
        std::copy(staging.mapped_span.begin(),staging.mapped_span.end(),device_bytes.begin());
        ++uploads;
    }
};
namespace Settings {
struct Toggle {bool value=false;bool GetValue()const{return value;}};
struct Values {Toggle gpu_unswizzle_enabled;};
inline Values values{};
}
namespace VideoCommon { enum class CacheType {NoTextureCache}; }
struct Memory {
    std::array<u8,256> bytes{};
    unsigned read_calls=0;
    void ReadBlock(GPUVAddr at,void* dst,std::size_t length,VideoCommon::CacheType) {
        assert(at<=bytes.size() && length<=bytes.size()-at);
        std::memcpy(dst,bytes.data()+at,length);
        ++read_calls;
    }
};
namespace Tegra::Memory {
enum class GuestMemoryFlags {UnsafeRead};
template<class T,GuestMemoryFlags F> struct GpuGuestMemory {
    std::span<const T> data;
    GpuGuestMemory(::Memory& m,GPUVAddr at,std::size_t length,Buffer*) {
        assert(at<=m.bytes.size() && length<=m.bytes.size()-at);
        data={m.bytes.data()+at,length};
    }
    operator std::span<const T>()const{return data;}
};
}
struct Runtime {
    unsigned allocations=0,barriers=0,accelerated=0,transitions=0;
    Image* image_to_verify=nullptr;
    std::shared_ptr<std::vector<u8>> last_stage;
    std::array<u8,64> expected{};
    bool can_upload_msaa=true;
    Staging UploadStagingBuffer(std::size_t n) {
        ++allocations;
        Staging s{n};
        last_stage=s.data;
        return s;
    }
    bool CanUploadMSAA()const{return can_upload_msaa;}
    void TransitionImageLayout(Image&){++transitions;}
    template<class Copies> void AccelerateImageUpload(Image& image,Staging& staging,
                                                      const Copies& copies,int,int) {
        assert(copies.size()==1);
        std::copy(staging.mapped_span.begin(),staging.mapped_span.end(),
                  image.device_bytes.begin());
        ++accelerated;
        ++image.uploads;
    }
    void InsertUploadMemoryBarrier() {
        assert(image_to_verify);
        assert(image_to_verify->device_bytes==expected);
        assert(image_to_verify->uploads==barriers+1);
        ++barriers;
    }
};
namespace Eden::Performance {
// Keep the host upload fixture compatible with the shipping F07 sampled
// diagnostics. These stand-ins intentionally preserve the same no-op effects:
// image bytes, barriers and cache ownership are validated independently.
enum class CachePhase {
    TextureCpuRefresh, TextureUploadStaging, TextureUploadContents,
    TextureUploadBarrier
};
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase) {}
    void Stop() noexcept {}
};
}
#define LOG_WARNING(...) ((void)0)
#define HW_GPU 0
bool IsPixelFormatBCn(unsigned){return false;}
std::size_t MapSizeBytes(const Image& image){return image.unswizzled_size_bytes;}
std::vector<int> FullUploadSwizzles(const Info&){return {1};}
template<class T> T FixSmallVectorADL(T t){return t;}
template<class Reader,class Dst>
std::vector<int> UnswizzleImage(Memory&,GPUVAddr,const Info&,const Reader& in,Dst& output){
    const std::span<const u8> input=in;
    std::span<u8> dest=output;
    assert(input.size()==dest.size());
    std::copy(input.begin(),input.end(),dest.begin());
    return {1};
}
void ConvertImage(Buffer& buf,const Info&,std::span<u8> staging,const std::vector<int>& copies) {
    assert(copies.size()==1);
    assert(buf.values.size()==staging.size());
    for(std::size_t i=0;i<staging.size();++i)staging[i]=buf.values[i]^u8{0xff};
}
template<class P> struct TextureCache {
    Memory memory{};
    Memory* gpu_memory=&memory;
    Runtime runtime{};
    Buffer swizzle_data_buffer,unswizzle_data_buffer;
    std::size_t gpu_unswizzle_maxsize=65536;
    unsigned tracked=0,async_decode=0,async_unswizzle=0;
    void TrackImage(Image&,ImageId){++tracked;}
    void QueueAsyncDecode(Image&,ImageId){++async_decode;}
    void QueueAsyncUnswizzle(Image&,ImageId){++async_unswizzle;}
    void RefreshContents(Image&,ImageId);
    template<class StagingBuffer> void UploadImageContents(Image&,StagingBuffer&);
};
__METHODS__
static void Changed(Image& image){image.flags.bits|=static_cast<unsigned>(ImageFlagBits::CpuModified);}
static std::array<u8,64> Data(const Memory& m,GPUVAddr addr,bool converted=false){
    std::array<u8,64> out{};
    for(std::size_t i=0;i<out.size();++i)
        out[i]=converted ? m.bytes[addr+i]^u8{0xff} : m.bytes[addr+i];
    return out;
}
int main(){
    TextureCache<int> cache;
    Image image;
    cache.runtime.image_to_verify=&image;
    for(std::size_t i=0;i<cache.memory.bytes.size();++i)
        cache.memory.bytes[i]=static_cast<u8>((i*43+7)%251);
    auto& m=cache.memory;
    // Clean view has no upload, staging allocation, nor barrier.
    cache.RefreshContents(image,0);
    assert(cache.runtime.allocations==0 && cache.tracked==0);
    // CPU writes: a real image revision must reach staging and the GPU image
    // before the barrier announces that the revision is visible to sampling.
    Changed(image);
    cache.runtime.expected=Data(m,image.gpu_addr);
    cache.RefreshContents(image,0);
    assert(image.device_bytes==cache.runtime.expected);
    assert(image.uploads==1 && cache.runtime.barriers==1);
    assert(cache.runtime.allocations==1 && cache.tracked==1);
    assert(False(image.flags & ImageFlagBits::CpuModified));
    cache.RefreshContents(image,0);
    assert(image.uploads==1);
    // Later CPU content must replace the old texture instead of reusing a
    // previously valid TIC/view with stale bytes.
    for(unsigned i=0;i<64;++i)m.bytes[image.gpu_addr+i]=static_cast<u8>(0x90+i);
    Changed(image);
    cache.runtime.expected=Data(m,image.gpu_addr);
    cache.RefreshContents(image,0);
    assert(image.uploads==2 && cache.runtime.barriers==2);
    assert(cache.runtime.allocations==2 && cache.tracked==2);
    // Converted texture path must upload *converted* data, not original guest bytes.
    for(unsigned i=0;i<64;++i)m.bytes[image.gpu_addr+i]=static_cast<u8>(0x20+i);
    Changed(image);
    image.flags.bits|=static_cast<unsigned>(ImageFlagBits::Converted);
    cache.runtime.expected=Data(m,image.gpu_addr,true);
    cache.RefreshContents(image,0);
    assert(image.uploads==3 && cache.runtime.barriers==3);
    assert(image.device_bytes==cache.runtime.expected);
    image.flags.bits&=~static_cast<unsigned>(ImageFlagBits::Converted);
    // Accelerated upload must receive the source payload and publish it before barrier.
    for(unsigned i=0;i<64;++i)m.bytes[image.gpu_addr+i]=static_cast<u8>(0x40+i);
    Changed(image);
    image.flags.bits|=static_cast<unsigned>(ImageFlagBits::AcceleratedUpload);
    cache.runtime.expected=Data(m,image.gpu_addr);
    cache.RefreshContents(image,0);
    assert(cache.runtime.accelerated==1 && m.read_calls==1);
    assert(image.uploads==4 && cache.runtime.barriers==4);
    // Deferred async image has no immediate barrier or staging reuse.
    image.flags.bits&=~static_cast<unsigned>(ImageFlagBits::AcceleratedUpload);
    image.flags.bits|=static_cast<unsigned>(ImageFlagBits::AsynchronousDecode);
    Changed(image);
    cache.RefreshContents(image,0);
    assert(cache.async_decode==1 && image.uploads==4);
    assert(cache.runtime.barriers==4 && cache.runtime.allocations==4);
    image.flags.bits&=~static_cast<unsigned>(ImageFlagBits::AsynchronousDecode);
    // Unsupported MSAA uploads must transition without pretending pixels changed.
    image.info.num_samples=4;
    cache.runtime.can_upload_msaa=false;
    Changed(image);
    cache.RefreshContents(image,0);
    assert(cache.runtime.transitions==1 && image.uploads==4);
    assert(cache.runtime.barriers==4 && cache.runtime.allocations==4);
    std::puts("F04_NATIVE_TEXTURE_UPLOAD_REVISION_PASS ordinary=2 converted=1 "
              "accelerated=1 async=1 msaa_transition=1 barriers=4 "
              "scope=source_extracted_host_mock_staging_no_gpu");
}
""".replace("__METHODS__",method)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f04-upload-") as td:
    path=Path(td)/"upload.cpp"
    path.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(td)/("upload"+opt)
        built=subprocess.run([compiler,"-std=c++20",opt,"-DPS5_NATIVE",
                              "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(path),"-o",str(exe)],
                             text=True,capture_output=True,timeout=75)
        assert built.returncode==0,(opt,built.stderr[-6000:])
        ran=subprocess.run([str(exe)],text=True,capture_output=True,timeout=20)
        assert ran.returncode==0,(opt,ran.stdout,ran.stderr[-5000:])
        assert "F04_NATIVE_TEXTURE_UPLOAD_REVISION_PASS" in ran.stdout
        print(ran.stdout.strip(),opt,flush=True)
print("F04_REAL_VULKAN_TRANSFER_FORMATS_AND_PIXELS_NOT_PROVEN")
