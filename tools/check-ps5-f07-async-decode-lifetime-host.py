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
assert "kMaxCompletedDecodesPerTick = 4" in method
assert "F07 skip idle native async texture decode completion machinery" in generator
assert "if (async_decodes.empty()) {" in method
assert method.index("if (async_decodes.empty()) {") < method.index("std::array<ImageId, kMaxCompletedDecodesPerTick> submitted_images{}")
assert method.index("#ifdef PS5_NATIVE") < method.index("if (async_decodes.empty()) {") < method.index("#endif")
assert "completed_decodes == kMaxCompletedDecodesPerTick" in method
assert "kMaxRetiredDecodesPerTick = 16" in method
assert "retired_decodes == kMaxRetiredDecodesPerTick" in method
assert "F07 count only accepted async HUD uploads under independent retired decode budget" in generator
assert "F07 bound completion retirements while skipping invalid async decode slots" in generator
assert "F07 increment successful async decode quota only after GPU submission" in generator
assert method.index("++completed_decodes;") > method.index("submitted_images[submitted_count++]")
assert method.index("++retired_decodes;") < method.index("std::unique_lock lock{async_decode->mutex}")
assert "F07 bounded ready decode completion under texture lock" in generator
assert "F07 gate per-HUD native decode INFO log behind detailed profile" in generator
queue=active.split("void TextureCache<P>::QueueAsyncDecode(Image& image, ImageId image_id) {",1)[1].split("\ntemplate <class P>",1)[0]
assert queue.count('LOG_INFO(HW_GPU, "Queuing async texture decode");') == 2
assert queue.index("::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed)") < queue.index('LOG_INFO(HW_GPU, "Queuing async texture decode");')
assert queue.index("#ifdef PS5_NATIVE") < queue.index("#else") < queue.index("#endif")

assert method.count("i = async_decodes.erase(i);") == 4
assert "F07 async decoded staging allocation failure and short span recovery" in generator
assert "F07 async decoded Vulkan submission failure recovery" in generator
assert method.index("image.UploadMemory(staging,") < method.index("} catch (...) {", method.index("image.UploadMemory(staging,"))
assert "if (!staging.buffer || staging.mapped_span.size() < expected_size)" in method
assert method.index("staging.mapped_span.size() < expected_size") < method.index("std::memcpy(")
assert method.count("image.flags |= ImageFlagBits::CpuModified;") == 4
assert "F07 mark entire decoded texture batch dirty after barrier failure" in generator
assert "std::array<ImageId, kMaxCompletedDecodesPerTick> submitted_images{}" in method
assert "submitted_images[submitted_count++] = async_decode->image_id" in method
assert method.index("submitted_images[submitted_count++]") < method.index("runtime.InsertUploadMemoryBarrier()")
assert "for (size_t j = 0; j < submitted_count; ++j)" in method
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
#include <array>
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
    bool buffer{};
    Staging() = default;
    explicit Staging(std::size_t n):bytes(n),mapped_span(bytes),buffer(true){}
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
    unsigned reject_on_call{},short_on_call{},null_on_call{};
    bool fail_barrier{};
    Staging UploadStagingBuffer(std::size_t n){
        ++staging_calls;
        if (reject_on_call == staging_calls) throw std::bad_alloc{};
        if (short_on_call == staging_calls) return Staging(n - 1);
        if (null_on_call == staging_calls) {auto invalid=Staging(n); invalid.buffer=false; return invalid;}
        return Staging(n);
    }
    void InsertUploadMemoryBarrier(){
        if(fail_barrier)throw std::runtime_error("mock upload barrier rejected");
        ++barriers;
    }
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
    // Idle frames must not touch decoder mutexes, staging or visibility
    // barriers, even when the texture cache still owns resident images.
    TextureCache<int> idle;
    idle.slot_images.resize(1);
    const unsigned idle_locks = CheckedMutex::lock_calls;
    idle.TickAsyncDecode();
    idle.TickAsyncDecode();
    assert(idle.runtime.staging_calls == 0 && idle.runtime.barriers == 0);
    assert(CheckedMutex::lock_calls == idle_locks);
    // The map can expose a full CPU span but contain no Vulkan VkBuffer.
    // Such an upload must keep CpuModified for the next refresh.
    TextureCache<int> invalid_handle;
    invalid_handle.slot_images.resize(1);
    invalid_handle.slot_images[0].size=4;
    invalid_handle.slot_images[0].flags|=ImageFlagBits::IsDecoding;
    invalid_handle.slot_images[0].flags|=ImageFlagBits::Tracked;
    auto invalid_ctx=std::make_unique<AsyncDecodeContext>();
    invalid_ctx->image_id=0; invalid_ctx->complete=true;
    invalid_ctx->decoded_data={1,2,3,4};
    invalid_handle.async_decodes.emplace_back(std::move(invalid_ctx));
    invalid_handle.runtime.null_on_call=1;
    invalid_handle.TickAsyncDecode();
    assert(invalid_handle.async_decodes.empty());
    assert(invalid_handle.slot_images[0].uploads==0);
    assert(invalid_handle.runtime.barriers==0);
    assert(True(invalid_handle.slot_images[0].flags&ImageFlagBits::CpuModified));
    assert(!True(invalid_handle.slot_images[0].flags&ImageFlagBits::IsDecoding));
    assert(!True(invalid_handle.slot_images[0].flags&ImageFlagBits::Tracked));
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
    // Invalid revisions and failed allocations do not take the four
    // successful-upload slots: retire all seven completed tasks at once.
    assert(CheckedMutex::lock_calls == locks_before_first_tick + 7);
    assert(cache.async_decodes.size()==1 && !cache.async_decodes[0]->complete);
    assert(cache.runtime.staging_calls==4 && cache.runtime.barriers==1);
    cache.TickAsyncDecode();
    assert(CheckedMutex::lock_calls == locks_before_first_tick + 7);
    assert(cache.async_decodes.size()==1);
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
    // A real burst of successful texture decodes must spread the upload
    // submissions and barriers over consecutive TickFrame calls. No stale
    // images and no abandoned contexts after the third tick.
    TextureCache<int> burst;
    burst.slot_images.resize(11);
    for (std::size_t id=0;id<11;++id) {
        auto& image=burst.slot_images[id];
        image.size=4;
        image.flags|=ImageFlagBits::IsDecoding;
        image.flags|=ImageFlagBits::Tracked;
        auto ctx=std::make_unique<AsyncDecodeContext>();
        ctx->image_id=id;
        ctx->complete=true;
        ctx->decoded_data={static_cast<std::uint8_t>(id),1,2,3};
        burst.async_decodes.emplace_back(std::move(ctx));
    }
    burst.TickAsyncDecode();
    assert(burst.async_decodes.size()==7 && burst.runtime.barriers==1);
    assert(burst.runtime.staging_calls==4 && burst.slot_images[3].uploads==1);
    assert(burst.slot_images[4].uploads==0);
    burst.TickAsyncDecode();
    assert(burst.async_decodes.size()==3 && burst.runtime.barriers==2);
    assert(burst.runtime.staging_calls==8 && burst.slot_images[7].uploads==1);
    assert(burst.slot_images[8].uploads==0);
    burst.TickAsyncDecode();
    assert(burst.async_decodes.empty() && burst.runtime.barriers==3);
    assert(burst.runtime.staging_calls==11);
    for (std::size_t id=0;id<11;++id) {
        assert(burst.slot_images[id].uploads==1);
        assert(burst.slot_images[id].result[0]==id);
        assert(!True(burst.slot_images[id].flags&ImageFlagBits::IsDecoding));
    }
    // A stale HUD burst must not starve valid work for four frames, and
    // retirement itself stays capped at 16 completed contexts per frame.
    TextureCache<int> mixed;
    mixed.slot_images.resize(23);
    for (std::size_t id=0;id<23;++id) {
        auto& image=mixed.slot_images[id];
        image.size=4;
        image.flags|=ImageFlagBits::IsDecoding;
        image.flags|=ImageFlagBits::Tracked;
        auto ctx=std::make_unique<AsyncDecodeContext>();
        ctx->image_id=id;
        ctx->complete=true;
        ctx->decoded_data={static_cast<std::uint8_t>(id),1,2,3};
        if (id < 19) image.flags|=ImageFlagBits::CpuModified;
        mixed.async_decodes.emplace_back(std::move(ctx));
    }
    const unsigned before_mixed = CheckedMutex::lock_calls;
    mixed.TickAsyncDecode();
    assert(mixed.async_decodes.size()==7);
    assert(CheckedMutex::lock_calls==before_mixed+16);
    assert(mixed.runtime.staging_calls==0 && mixed.runtime.barriers==0);
    mixed.TickAsyncDecode();
    assert(mixed.async_decodes.empty());
    assert(CheckedMutex::lock_calls==before_mixed+23);
    assert(mixed.runtime.staging_calls==4 && mixed.runtime.barriers==1);
    for (std::size_t id=0;id<19;++id) {
        assert(mixed.slot_images[id].uploads==0);
        assert(True(mixed.slot_images[id].flags&ImageFlagBits::CpuModified));
    }
    for (std::size_t id=19;id<23;++id) {
        assert(mixed.slot_images[id].uploads==1);
        assert(!True(mixed.slot_images[id].flags&ImageFlagBits::IsDecoding));
    }
    // Two valid uploads have been recorded but their final visibility barrier
    // fails. BOTH images must be dirty/retryable; no decoding lock may leak.
    TextureCache<int> failed_barrier;
    failed_barrier.slot_images.resize(2);
    for (std::size_t id=0;id<2;++id) {
        failed_barrier.slot_images[id].size=4;
        failed_barrier.slot_images[id].flags|=ImageFlagBits::IsDecoding;
        failed_barrier.slot_images[id].flags|=ImageFlagBits::Tracked;
        auto ctx=std::make_unique<AsyncDecodeContext>();
        ctx->image_id=id;ctx->complete=true;
        ctx->decoded_data={static_cast<std::uint8_t>(id),3,4,5};
        failed_barrier.async_decodes.emplace_back(std::move(ctx));
    }
    failed_barrier.runtime.fail_barrier=true;
    failed_barrier.TickAsyncDecode();
    assert(failed_barrier.async_decodes.empty());
    assert(failed_barrier.runtime.barriers==0 && failed_barrier.untracked==2);
    for (std::size_t id=0;id<2;++id) {
        assert(failed_barrier.slot_images[id].uploads==1);
        assert(True(failed_barrier.slot_images[id].flags&ImageFlagBits::CpuModified));
        assert(!True(failed_barrier.slot_images[id].flags&ImageFlagBits::Tracked));
        assert(!True(failed_barrier.slot_images[id].flags&ImageFlagBits::IsDecoding));
    }
    failed_barrier.runtime.fail_barrier=false;
    failed_barrier.slot_images[0].flags.bits=static_cast<std::uint32_t>(ImageFlagBits::IsDecoding);
    auto retry=std::make_unique<AsyncDecodeContext>();
    retry->image_id=0;retry->complete=true;retry->decoded_data={8,7,6,5};
    failed_barrier.async_decodes.emplace_back(std::move(retry));
    failed_barrier.TickAsyncDecode();
    assert(failed_barrier.runtime.barriers==1);
    assert(failed_barrier.slot_images[0].uploads==2);
    assert(!True(failed_barrier.slot_images[0].flags&ImageFlagBits::CpuModified));
    assert(!True(failed_barrier.slot_images[0].flags&ImageFlagBits::IsDecoding));
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
print("F07_ASYNC_TICK_LIFETIME_HOST_PASS unlock_before_erase=1 revision_size_guard=1 stale_same_size=1 stale_remapped_same_size=1 pending=1 staging_oom=1 short_span=1 failed_gpu_submission=1 retry=1 burst_quota_4=1 retired_quota_16=1 stale_budget_elision=1 burst_11_in_3_ticks=1 failed_barrier_dirty_batch=1 barrier_retry=1 O0=1 O2=1")


# Execute the source-selected native/desktop logging branch with explicit
# quiet/detailed GPU profile controls. Reproduce actual LOG_INFO side effects.
queue_gate=queue[queue.index("#ifdef PS5_NATIVE"):queue.index("#endif",queue.index("#ifdef PS5_NATIVE"))+len("#endif")]
log_cpp=r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
namespace Eden::Performance {
inline std::atomic_bool detailed_gpu_profile{false};
}
unsigned info_lines = 0;
#define HW_GPU 1
#define LOG_INFO(channel, message) do { (void)(channel); (void)(message); ++info_lines; } while (0)
static void Probe() {
__LOG_GUARD__
}
int main(){
    Probe();
#ifdef PS5_NATIVE
    assert(info_lines==0);
#else
    assert(info_lines==1);
#endif
    Eden::Performance::detailed_gpu_profile.store(true);
    Probe();
#ifdef PS5_NATIVE
    assert(info_lines==1);
#else
    assert(info_lines==2);
#endif
}
""".replace("__LOG_GUARD__",queue_gate)
with tempfile.TemporaryDirectory(prefix="eden-f07-async-quiet-") as directory:
    path=Path(directory)/"logging.cpp"
    path.write_text(log_cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            exe=Path(directory)/("logging"+opt[2:]+("ps5" if native else "desktop"))
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native else []),str(path),"-o",str(exe)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-4000:])
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert ran.returncode==0,(native,opt,ran.stderr[-4000:])
print("F07_NATIVE_QUIET_ASYNC_DECODE_LOG_PASS quiet=0 detailed=1 desktop_original=1 O0=1 O2=1")

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
#include <array>
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

# Native async decode inputs are fully overwritten by UnswizzleImage.
# The original vector(size,0) zeroed every byte on the GPU owner while holding
# texture_cache.mutex, even though it was about to be overwritten.
assert "F07 avoid zero-filling native asynchronous texture decode input" in generator
scratch_needle = "#ifdef PS5_NATIVE\n    // UnswizzleImage writes each copy's destination bytes"
assert queue.count(scratch_needle)==1
allocation_begin=queue.index(scratch_needle)
allocation_end=queue.index("    Tegra::Memory::GpuGuestMemory<u8",allocation_begin)
allocation=queue[allocation_begin:allocation_end]
assert "Common::ScratchBuffer<u8> local_unswizzle_data_buffer;" in allocation
assert "local_unswizzle_data_buffer.resize_destructive(image.unswizzled_size_bytes);" in allocation
assert 'std::vector<u8> local_unswizzle_data_buffer(image.unswizzled_size_bytes, 0);' in allocation
assert allocation.index("resize_destructive") < allocation.index("#else")
assert "input = std::move(local_unswizzle_data_buffer)" in queue
assert "texture_decode_worker.QueueWork(std::move(func));" in queue
scratch_cpp = r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <span>
#include <type_traits>
#include <utility>
#include <vector>
#include "common/scratch_buffer.h"
#include "common/unique_function.h"
using u8=std::uint8_t;
struct Image {std::size_t unswizzled_size_bytes;};
void Test(std::size_t bytes) {
    Image image{bytes};
__ACTUAL_ALLOCATION__
    assert(local_unswizzle_data_buffer.size()==bytes);
    std::span<u8> output{local_unswizzle_data_buffer};
    for(std::size_t i=0;i<output.size();++i) output[i]=static_cast<u8>(i+1);
    auto task=[input=std::move(local_unswizzle_data_buffer),bytes]() mutable {
        assert(input.size()==bytes);
        const std::span<const u8> source{input.data(),input.size()};
        for(std::size_t i=0;i<source.size();++i)
            assert(source[i]==static_cast<u8>(i+1));
    };
    Common::UniqueFunction<void> worker_job(std::move(task));
    worker_job();
}
int main() {
    Test(1); Test(9); Test(65536);
}
""".replace("__ACTUAL_ALLOCATION__",allocation)
with tempfile.TemporaryDirectory(prefix="eden-f07-async-input-buffer-") as folder:
    cpp_path=Path(folder)/"input.cpp"
    cpp_path.write_text(scratch_cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            binary=Path(folder)/(("ps5" if native else "desktop")+opt[2:])
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  "-I",str(root/"vendor/sources/eden/src"),
                                  *(["-DPS5_NATIVE=1"] if native else []),
                                  str(cpp_path),"-o",str(binary)],
                                 capture_output=True,text=True,timeout=45)
            assert build.returncode==0,(native,opt,build.stderr[-6500:])
            run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
            assert run.returncode==0,(native,opt,run.stderr[-5000:])
print("F07_ASYNC_SCRATCH_OVERWRITE_PASS scratch_nonzero_input=1 move_only_worker=1 desktop_original=1 O0=1 O2=1 UBSan=1")
