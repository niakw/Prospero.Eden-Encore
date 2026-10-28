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
assert method.count("lock.unlock();") == 4
assert method.count("i = async_decodes.erase(i);") == 4
assert "F07 async decoded staging allocation failure and short span recovery" in generator
assert "F07 async decoded Vulkan submission failure recovery" in generator
assert method.index("image.UploadMemory(staging,") < method.index("} catch (...) {", method.index("image.UploadMemory(staging,"))
assert "staging.mapped_span.size() < expected_size" in method
assert method.index("staging.mapped_span.size() < expected_size") < method.index("std::memcpy(")
assert method.count("image.flags |= ImageFlagBits::CpuModified;") == 3
assert method.index("lock.unlock();") < method.index("i = async_decodes.erase(i);")
assert method.rindex("lock.unlock();") < method.rindex("i = async_decodes.erase(i);")
assert "async_decode->decoded_data.size() != expected_size" in method
assert "F07 atomic unfinished texture decode polling" in generator
assert "async_decode->complete.load(std::memory_order_acquire)" in method
assert method.index("async_decode->complete.load(std::memory_order_acquire)") < method.index(
    "std::unique_lock lock{async_decode->mutex};")
assert "True(image.flags & ImageFlagBits::CpuModified)" in method
assert "True(image.flags & ImageFlagBits::Remapped)" in method
assert method.index("True(image.flags & ImageFlagBits::Remapped)") < method.index("std::memcpy(")
assert method.index("True(image.flags & ImageFlagBits::CpuModified)") < method.index("std::memcpy(")
assert "image.flags |= ImageFlagBits::CpuModified;" in method
assert "UntrackImage(image, async_decode->image_id);" in method
for delta in ("F07 async texture revision length guard",
              "F07 async decode unlock before context erase",
              "F07 discard stale decoded HUD revision after CPU write",
              "F07 discard same-size async texture after guest remap"):
    assert delta in generator

cpp = r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <span>
#include <vector>
using ImageId=std::size_t;
struct CheckedMutex {
    inline static unsigned lock_calls{};
    bool held{};
    void lock(){assert(!held);held=true;++lock_calls;}
    void unlock(){assert(held);held=false;}
    ~CheckedMutex(){assert(!held && "decode mutex destroyed while still locked");}
};
enum class ImageFlagBits:std::uint32_t{IsDecoding=1,CpuModified=2,Tracked=4,Remapped=8};
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
    Staging() = default;
    explicit Staging(std::size_t n):bytes(n),mapped_span(bytes){}
};
struct Image{
    Flags flags{};
    std::size_t size{};
    std::vector<std::uint8_t> result;
    unsigned uploads{};
    bool reject_upload{};
    void UploadMemory(Staging& stage,const std::vector<int>&){
        if (reject_upload) throw std::runtime_error("mock Vulkan record failure");
        result=stage.bytes;++uploads;
    }
};
struct AsyncDecodeContext{
    ImageId image_id{};
    std::vector<std::uint8_t> decoded_data;
    std::vector<int> copies;
    CheckedMutex mutex;
    std::atomic_bool complete{false};
};
struct Runtime{
    unsigned staging_calls{},barriers{};
    unsigned reject_on_call{},short_on_call{};
    Staging UploadStagingBuffer(std::size_t n){
        ++staging_calls;
        if (reject_on_call == staging_calls) throw std::bad_alloc{};
        if (short_on_call == staging_calls) return Staging(n - 1);
        return Staging(n);
    }
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
    cache.slot_images.resize(8);
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
    auto stale_same_size=std::make_unique<AsyncDecodeContext>();
    stale_same_size->image_id=3; stale_same_size->complete=true;
    stale_same_size->decoded_data={1,1,1,1};
    // A later CPU modification invalidates the decoded bytes while retaining
    // exactly the same dimensions: a common HUD update.
    cache.slot_images[3].flags|=ImageFlagBits::CpuModified;
    auto stale_remapped=std::make_unique<AsyncDecodeContext>();
    stale_remapped->image_id=4; stale_remapped->complete=true;
    stale_remapped->decoded_data={8,8,8,8};
    cache.slot_images[4].flags|=ImageFlagBits::Remapped;
    cache.async_decodes.emplace_back(std::move(pending));
    cache.async_decodes.emplace_back(std::move(stale));
    cache.async_decodes.emplace_back(std::move(ready));
    cache.async_decodes.emplace_back(std::move(stale_same_size));
    cache.async_decodes.emplace_back(std::move(stale_remapped));
    auto allocation_failed=std::make_unique<AsyncDecodeContext>();
    allocation_failed->image_id=5; allocation_failed->complete=true;
    allocation_failed->decoded_data={1,2,3,4};
    auto short_staging=std::make_unique<AsyncDecodeContext>();
    short_staging->image_id=6; short_staging->complete=true;
    short_staging->decoded_data={1,2,3,4};
    cache.async_decodes.emplace_back(std::move(allocation_failed));
    cache.async_decodes.emplace_back(std::move(short_staging));
    auto failed_submission=std::make_unique<AsyncDecodeContext>();
    failed_submission->image_id=7; failed_submission->complete=true;
    failed_submission->decoded_data={1,2,3,4};
    cache.slot_images[7].reject_upload=true;
    cache.async_decodes.emplace_back(std::move(failed_submission));
    cache.runtime.reject_on_call=2;
    cache.runtime.short_on_call=3;
    const unsigned locks_before_first_tick = CheckedMutex::lock_calls;
    cache.TickAsyncDecode();
    // Seven completed tasks consume the mutex; the pending one does not.
    assert(CheckedMutex::lock_calls == locks_before_first_tick + 7);
    assert(cache.async_decodes.size()==1 && !cache.async_decodes[0]->complete);
    assert(True(cache.slot_images[1].flags&ImageFlagBits::CpuModified));
    assert(!True(cache.slot_images[1].flags&ImageFlagBits::Tracked));
    assert(!True(cache.slot_images[1].flags&ImageFlagBits::IsDecoding));
    assert(cache.slot_images[1].uploads==0);
    assert(cache.slot_images[3].uploads==0);
    assert(True(cache.slot_images[3].flags&ImageFlagBits::CpuModified));
    assert(!True(cache.slot_images[3].flags&ImageFlagBits::Tracked));
    assert(!True(cache.slot_images[3].flags&ImageFlagBits::IsDecoding));
    assert(cache.slot_images[4].uploads==0);
    assert(True(cache.slot_images[4].flags&ImageFlagBits::CpuModified));
    assert(!True(cache.slot_images[4].flags&ImageFlagBits::Tracked));
    assert(!True(cache.slot_images[4].flags&ImageFlagBits::IsDecoding));
    assert(cache.slot_images[2].uploads==1);
    assert((cache.slot_images[2].result==std::vector<std::uint8_t>{5,6,7,8}));
    assert(cache.runtime.staging_calls==4 && cache.runtime.barriers==1);
    assert(cache.untracked==6);
    assert(cache.slot_images[7].uploads==0);
    assert(True(cache.slot_images[7].flags&ImageFlagBits::CpuModified));
    assert(!True(cache.slot_images[7].flags&ImageFlagBits::Tracked));
    assert(!True(cache.slot_images[7].flags&ImageFlagBits::IsDecoding));
    for (std::size_t id : {5u, 6u}) {
        assert(cache.slot_images[id].uploads==0);
        assert(True(cache.slot_images[id].flags & ImageFlagBits::CpuModified));
        assert(!True(cache.slot_images[id].flags & ImageFlagBits::Tracked));
        assert(!True(cache.slot_images[id].flags & ImageFlagBits::IsDecoding));
    }
    cache.async_decodes.front()->complete=true;
    cache.TickAsyncDecode();
    assert(CheckedMutex::lock_calls == locks_before_first_tick + 8);
    assert(cache.async_decodes.empty() && cache.runtime.barriers==2);
    // A later successful staging allocation accepts a fresh texture revision.
    auto recovered=std::make_unique<AsyncDecodeContext>();
    recovered->image_id=5; recovered->complete=true;
    recovered->decoded_data={7,8,9,10};
    cache.slot_images[5].flags.bits=static_cast<std::uint32_t>(ImageFlagBits::IsDecoding);
    cache.async_decodes.emplace_back(std::move(recovered));
    cache.TickAsyncDecode();
    assert(cache.async_decodes.empty() && cache.runtime.barriers==3);
    assert(cache.slot_images[5].uploads==1);
    assert((cache.slot_images[5].result==std::vector<std::uint8_t>{7,8,9,10}));
    auto retried_submission=std::make_unique<AsyncDecodeContext>();
    retried_submission->image_id=7; retried_submission->complete=true;
    retried_submission->decoded_data={11,12,13,14};
    cache.slot_images[7].reject_upload=false;
    cache.slot_images[7].flags.bits=static_cast<std::uint32_t>(ImageFlagBits::IsDecoding);
    cache.async_decodes.emplace_back(std::move(retried_submission));
    cache.TickAsyncDecode();
    assert(cache.async_decodes.empty() && cache.runtime.barriers==4);
    assert(cache.slot_images[7].uploads==1);
    assert((cache.slot_images[7].result==std::vector<std::uint8_t>{11,12,13,14}));
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
print("F07_ASYNC_TICK_LIFETIME_HOST_PASS unlock_before_erase=1 revision_size_guard=1 stale_same_size=1 stale_remapped_same_size=1 pending=1 staging_oom=1 short_span=1 failed_gpu_submission=1 retry=1 O0=1 O2=1")


# Extract the real queued native conversion lambda and execute both branches.
# Conversions can throw after QueueWork has succeeded; the worker must publish
# a completed failure instead of leaving the guest image IsDecoding forever.
queue_start = active.index("void TextureCache<P>::QueueAsyncDecode(")
worker_begin = active.index("    auto func = [out_size, copies, info = image.info,", queue_start)
worker_end = active.index("    texture_decode_worker.QueueWork(std::move(func));", worker_begin)
worker_source = active[worker_begin:worker_end]
assert worker_source.count("catch (...)") == 1
assert worker_source.count("async_decode->complete = true;") == 2
assert "async_decode->decoded_data.resize_destructive(0);" in worker_source
assert "F07 async decode worker exception handoff" in generator
assert "F07 reject zero-length failed decode completion" in generator
assert "async_decode->decoded_data.size() == 0 ||" in method

worker_cpp = r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>
using u8 = std::uint8_t;
struct Scratch {
    std::vector<u8> data;
    void resize_destructive(std::size_t n) { data.resize(n); }
    std::size_t size() const { return data.size(); }
};
struct ImageInfo {};
struct Image { ImageInfo info{}; };
struct AsyncDecodeContext {
    Scratch decoded_data;
    std::vector<int> copies;
    std::mutex mutex;
    std::atomic_bool complete{false};
};
bool throw_conversion = false;
void ConvertImage(const std::vector<u8>& src, const ImageInfo&,
                  Scratch& dst, std::span<int> copy_spans) {
    assert(src.size() == 4 && copy_spans.size() == 1);
    if (throw_conversion) {
        if (!dst.data.empty()) dst.data[0] = 99; // partial old bytes
        throw std::runtime_error("mock conversion failure");
    }
    dst.data = src;
}
static void run_case(bool fail) {
    throw_conversion = fail;
    Image image{};
    AsyncDecodeContext decode{};
    AsyncDecodeContext* decode_ptr = &decode;
    std::size_t out_size = 4;
    std::vector<int> copies{1};
    std::vector<u8> local_unswizzle_data_buffer{3, 4, 5, 6};
""" + worker_source + r"""
    func();
    assert(decode.complete.load(std::memory_order_acquire));
    if (fail) {
        // TickAsyncDecode's size=0 sentinel must reject the partial revision.
        assert(decode.decoded_data.size() == 0);
    } else {
        assert(decode.decoded_data.size() == 4);
        assert((decode.decoded_data.data == std::vector<u8>{3,4,5,6}));
        assert((decode.copies == std::vector<int>{1}));
    }
}
int main() {
    run_case(false);
    run_case(true);
    run_case(false); // a subsequent decode is not poisoned by the failure
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-async-worker-recovery-") as directory:
    worker_path=Path(directory)/"worker.cpp"
    worker_path.write_text(worker_cpp)
    for optimization in ("-O0","-O2"):
        binary=Path(directory)/("worker"+optimization[1:])
        built=subprocess.run([compiler, "-std=c++20", optimization, "-DPS5_NATIVE=1",
                              "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                              "-fno-sanitize-recover=all", str(worker_path), "-o", str(binary)],
                             capture_output=True,text=True,timeout=50)
        assert built.returncode==0,(optimization,built.stderr[-4500:])
        ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
        assert ran.returncode==0,(optimization,ran.stdout,ran.stderr[-4500:])
print("F07_ASYNC_WORKER_FAILURE_HOST_PASS normal=1 failed=1 resumed=1 O0=1 O2=1")
