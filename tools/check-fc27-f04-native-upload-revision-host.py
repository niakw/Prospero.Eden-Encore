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
assert "swizzle_chunk_size != 0 && swizzle_slices_per_batch != 0" in method
assert "F07 reject uninitialized BCn 3D async queue budgets" in (
    ROOT/"tools/prepare-vulkan-port.py").read_text()
assert "staging.mapped_span.size_bytes() < upload_size" in method
assert method.index("staging.mapped_span.size_bytes() < upload_size") < method.index("UploadImageContents(image, staging);")
assert "F07 reject short native sync upload staging" in (ROOT/"tools/prepare-vulkan-port.py").read_text()

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <span>
#include <type_traits>
#include <utility>
#include <vector>
// The source-extracted F07 upload guard uses the same RAII unwind contract
// as the production cache. Keep this fixture's image flags and page counter real.
struct HostScopeExitMaker {};
template<class F> struct HostScopeExit {
    F f;
    ~HostScopeExit() { f(); }
};
template<class F>
HostScopeExit<std::decay_t<F>> operator+(HostScopeExitMaker, F&& f) {
    return {std::forward<F>(f)};
}
#define SCOPE_EXIT auto _f07_upload_scope = HostScopeExitMaker{} + [&]
using u8 = std::uint8_t;
using u64 = std::uint64_t;
using GPUVAddr = u64;
using ImageId = std::size_t;
enum class ImageFlagBits : unsigned {
    CpuModified=1,AsynchronousDecode=2,GpuModified=4,AcceleratedUpload=8,
    Converted=16,Tracked=32,IsDecoding=64
};
struct Flags {
    unsigned bits{};
    Flags& operator&=(unsigned mask){bits &= mask;return *this;}
    Flags& operator|=(ImageFlagBits bit){bits|=static_cast<unsigned>(bit);return *this;}
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
    bool reject_staging{};
    bool short_staging{};
    Staging UploadStagingBuffer(std::size_t n) {
        ++allocations;
        if(reject_staging)throw std::bad_alloc{};
        Staging s{short_staging?n-1:n};
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
    TextureCpuRefresh, TextureAliasScan, TextureAliasCopy,
    TextureUploadStaging, TextureUploadContents, TextureUploadBarrier
};
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase) {}
    void Stop() noexcept {}
};
}
#define LOG_WARNING(...) ((void)0)
#define HW_GPU 0
bool IsPixelFormatBCn(unsigned fmt){return fmt==42;}
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
    std::size_t swizzle_chunk_size{}, swizzle_slices_per_batch{};
    unsigned tracked=0,async_decode=0,async_unswizzle=0,untrack_count=0;
    bool fail_track=false;
    void TrackImage(Image& img,ImageId){
        ++tracked;
        img.flags |= ImageFlagBits::Tracked;
        if(fail_track)throw std::runtime_error("tracked registration failure");
    }
    void UntrackImage(Image& img,ImageId){
        assert(True(img.flags & ImageFlagBits::Tracked));
        img.flags.bits &= ~static_cast<unsigned>(ImageFlagBits::Tracked);
        ++untrack_count;
    }
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
    // An older async job owns this texture. A new guest CPU revision must
    // stay dirty and must not queue a competing stale decode.
    image.flags |= ImageFlagBits::IsDecoding;
    Changed(image);
    const unsigned queued_before=cache.async_decode;
    const unsigned tracked_before=cache.tracked;
    cache.RefreshContents(image,0);
    assert(cache.async_decode==queued_before);
    assert(cache.tracked==tracked_before);
    assert(True(image.flags & ImageFlagBits::CpuModified));
    // After that job completes, the pending revision can be admitted.
    image.flags.bits&=~static_cast<unsigned>(ImageFlagBits::IsDecoding);
    cache.RefreshContents(image,0);
    assert(cache.async_decode==queued_before+1);
    assert(False(image.flags & ImageFlagBits::CpuModified));
    image.flags.bits&=~static_cast<unsigned>(ImageFlagBits::AsynchronousDecode);
    // Unsupported MSAA uploads must transition without pretending pixels changed.
    image.info.num_samples=4;
    cache.runtime.can_upload_msaa=false;
    Changed(image);
    cache.RefreshContents(image,0);
    assert(cache.runtime.transitions==1 && image.uploads==4);
    assert(cache.runtime.barriers==4 && cache.runtime.allocations==4);
    // Failure registering a CPU revision must not hide it from a later upload.
    image.info.num_samples=1;
    Changed(image);
    cache.fail_track=true;
    bool threw=false;
    try { cache.RefreshContents(image,0); }
    catch(const std::runtime_error&) { threw=true; }
    assert(threw && True(image.flags & ImageFlagBits::CpuModified));
    assert(False(image.flags & ImageFlagBits::Tracked));
    assert(image.uploads==4 && cache.runtime.barriers==4);
    cache.fail_track=false;
    cache.runtime.expected=Data(m,image.gpu_addr);
    cache.RefreshContents(image,0);
    assert(image.uploads==5 && cache.runtime.barriers==5);
    assert(False(image.flags & ImageFlagBits::CpuModified));
    for(unsigned i=0;i<64;++i)m.bytes[image.gpu_addr+i]=static_cast<u8>(0x60+i);
    Changed(image);
    cache.runtime.expected=Data(m,image.gpu_addr);
    cache.runtime.reject_staging=true;
    const auto before_uploads=image.uploads;
    const auto before_barriers=cache.runtime.barriers;
    cache.RefreshContents(image,0);
    assert(image.uploads==before_uploads && cache.runtime.barriers==before_barriers);
    assert(True(image.flags & ImageFlagBits::CpuModified));
    assert(False(image.flags & ImageFlagBits::Tracked));
    cache.runtime.reject_staging=false;
    cache.RefreshContents(image,0);
    assert(image.uploads==6 && cache.runtime.barriers==6);
    assert(image.device_bytes==cache.runtime.expected);
    assert(False(image.flags & ImageFlagBits::CpuModified));
    for(unsigned i=0;i<64;++i)m.bytes[image.gpu_addr+i]=static_cast<u8>(0x70+i);
    Changed(image);
    cache.runtime.expected=Data(m,image.gpu_addr);
    cache.runtime.short_staging=true;
    const auto prior_uploads=image.uploads;
    const auto prior_barriers=cache.runtime.barriers;
    cache.RefreshContents(image,0);
    assert(image.uploads==prior_uploads && cache.runtime.barriers==prior_barriers);
    assert(True(image.flags & ImageFlagBits::CpuModified));
    assert(False(image.flags & ImageFlagBits::Tracked));
    cache.runtime.short_staging=false;
    cache.RefreshContents(image,0);
    assert(image.uploads==7 && cache.runtime.barriers==7);
    assert(image.device_bytes==cache.runtime.expected);
    assert(False(image.flags & ImageFlagBits::CpuModified));
    // Enabling GPU 3D unswizzle after constructing a CPU-only cache must not
    // queue a zero-progress task: use the ordinary synchronous refresh.
    image.info.type=ImageType::e3D;
    image.info.format=42;
    cache.gpu_unswizzle_maxsize=0;
    Settings::values.gpu_unswizzle_enabled.value=true;
    Changed(image);
    cache.runtime.expected=Data(m,image.gpu_addr);
    cache.RefreshContents(image,0);
    assert(cache.async_unswizzle==0 && image.uploads==8);
    assert(cache.runtime.barriers==8);
    cache.swizzle_chunk_size=16;
    cache.swizzle_slices_per_batch=128;
    Changed(image);
    cache.RefreshContents(image,0);
    assert(cache.async_unswizzle==1 && image.uploads==8);
    Settings::values.gpu_unswizzle_enabled.value=false;
    std::puts("F04_NATIVE_TEXTURE_UPLOAD_REVISION_PASS ordinary=2 converted=1 "
              "accelerated=1 async=1 msaa_transition=1 barriers=4 "
              "registration_failure_recovered=1 staging_oom_recovered=1 short_mapping_recovered=1 runtime_unswizzle_toggle_guard=1 scope=source_extracted_host_mock_staging_no_gpu");
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
