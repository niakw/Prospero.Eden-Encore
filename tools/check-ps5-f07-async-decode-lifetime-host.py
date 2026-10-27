#!/usr/bin/env python3
"""F07 P0.4: execute the selected native TickAsyncDecode lifetime and byte-size guard.

Use the exact source method at O0/O2. The fixture's mutex destructor asserts
that it was unlocked before vector erase destroyed the decode context. A stale
revision must not overflow its current staging allocation or be marked clean.
This does not qualify actual PS5 Vulkan image transfer.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
start = "template <class P>\nvoid TextureCache<P>::TickAsyncDecode() {"
end = "\ntemplate <class P>\nvoid TextureCache<P>::TickAsyncUnswizzle() {"
assert active.count(start) == pinned.count(start) == 1
assert active.count(end) == pinned.count(end) == 1
method = active[active.index(start):active.index(end, active.index(start))]
old_method = pinned[pinned.index(start):pinned.index(end, pinned.index(start))]
assert "lock.unlock();" not in old_method  # original reproducible lifetime hazard
assert method.count("lock.unlock();") == 2
assert method.count("i = async_decodes.erase(i);") == 2
assert method.index("lock.unlock();") < method.index("i = async_decodes.erase(i);")
assert method.rindex("lock.unlock();") < method.rindex("i = async_decodes.erase(i);")
assert "async_decode->decoded_data.size() != expected_size" in method
assert "image.flags |= ImageFlagBits::CpuModified;" in method
assert "UntrackImage(image, async_decode->image_id);" in method
for delta in ("F07 async texture revision length guard",
              "F07 async decode unlock before context erase"):
    assert delta in generator

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <span>
#include <vector>
using ImageId=std::size_t;
struct CheckedMutex {
    bool held{};
    void lock(){assert(!held);held=true;}
    void unlock(){assert(held);held=false;}
    ~CheckedMutex(){assert(!held && "decode mutex destroyed while still locked");}
};
enum class ImageFlagBits:std::uint32_t{IsDecoding=1,CpuModified=2,Tracked=4};
struct Flags{
    std::uint32_t bits{};
    Flags& operator&=(std::uint32_t n){bits&=n;return *this;}
    Flags& operator|=(ImageFlagBits b){bits|=static_cast<std::uint32_t>(b);return *this;}
};
std::uint32_t operator~(ImageFlagBits b){return ~static_cast<std::uint32_t>(b);}
std::uint32_t operator&(Flags f,ImageFlagBits b){return f.bits&static_cast<std::uint32_t>(b);}
bool True(std::uint32_t n){return n!=0;}
struct Staging{
    std::vector<std::uint8_t> bytes;
    std::span<std::uint8_t> mapped_span;
    explicit Staging(std::size_t n):bytes(n),mapped_span(bytes){}
};
struct Image{
    Flags flags{};
    std::size_t size{};
    std::vector<std::uint8_t> result;
    unsigned uploads{};
    void UploadMemory(Staging& stage,const std::vector<int>&){
        result=stage.bytes;++uploads;
    }
};
struct AsyncDecodeContext{
    ImageId image_id{};
    std::vector<std::uint8_t> decoded_data;
    std::vector<int> copies;
    CheckedMutex mutex;
    bool complete{};
};
struct Runtime{
    unsigned staging_calls{},barriers{};
    Staging UploadStagingBuffer(std::size_t n){++staging_calls;return Staging(n);}
    void InsertUploadMemoryBarrier(){++barriers;}
};
const std::vector<int>& FixSmallVectorADL(const std::vector<int>& v){return v;}
template<class P>struct TextureCache{
    std::vector<std::unique_ptr<AsyncDecodeContext>> async_decodes;
    std::vector<Image> slot_images;
    Runtime runtime;
    unsigned untracked{};
    std::size_t MapSizeBytes(const Image& image){return image.size;}
    void UntrackImage(Image& image,ImageId){
        assert(True(image.flags&ImageFlagBits::Tracked));
        image.flags&=~ImageFlagBits::Tracked;
        ++untracked;
    }
    void TickAsyncDecode();
};
""" + method + r"""
int main(){
    TextureCache<int> cache;
    cache.slot_images.resize(3);
    for(auto& image:cache.slot_images){
        image.size=4;
        image.flags|=ImageFlagBits::IsDecoding;
        image.flags|=ImageFlagBits::Tracked;
    }
    auto pending=std::make_unique<AsyncDecodeContext>();
    pending->image_id=0; pending->complete=false;
    pending->decoded_data={1,2,3,4};
    auto stale=std::make_unique<AsyncDecodeContext>();
    stale->image_id=1; stale->complete=true;
    stale->decoded_data={9,9,9,9,9,9,9,9};
    auto ready=std::make_unique<AsyncDecodeContext>();
    ready->image_id=2; ready->complete=true;
    ready->decoded_data={5,6,7,8};
    cache.async_decodes.emplace_back(std::move(pending));
    cache.async_decodes.emplace_back(std::move(stale));
    cache.async_decodes.emplace_back(std::move(ready));
    cache.TickAsyncDecode();
    assert(cache.async_decodes.size()==1 && !cache.async_decodes[0]->complete);
    assert(True(cache.slot_images[1].flags&ImageFlagBits::CpuModified));
    assert(!True(cache.slot_images[1].flags&ImageFlagBits::Tracked));
    assert(!True(cache.slot_images[1].flags&ImageFlagBits::IsDecoding));
    assert(cache.slot_images[1].uploads==0);
    assert(cache.slot_images[2].uploads==1);
    assert((cache.slot_images[2].result==std::vector<std::uint8_t>{5,6,7,8}));
    assert(cache.runtime.staging_calls==1 && cache.runtime.barriers==1);
    assert(cache.untracked==1);
    cache.async_decodes.front()->complete=true;
    cache.TickAsyncDecode();
    assert(cache.async_decodes.empty() && cache.runtime.barriers==2);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-async-lifetime-") as directory:
    source=Path(directory)/"tick.cpp"
    source.write_text(cpp)
    for optimization in ("-O0","-O2"):
        binary=Path(directory)/("tick"+optimization[1:])
        built=subprocess.run([compiler,"-std=c++20",optimization,"-DPS5_NATIVE=1",
                              "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(source),"-o",str(binary)],
                             capture_output=True,text=True,timeout=50)
        assert built.returncode==0,(optimization,built.stderr[-5000:])
        ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
        assert ran.returncode==0,(optimization,ran.stdout,ran.stderr[-5000:])
print("F07_ASYNC_TICK_LIFETIME_HOST_PASS unlock_before_erase=1 revision_size_guard=1 pending=1 O0=1 O2=1")
