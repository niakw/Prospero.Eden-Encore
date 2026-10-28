#!/usr/bin/env python3
"""F07 P0.4: source-extracted stale multi-frame unswizzle cancellation.

The test compiles the actual queue/cancel/throttle prefix of TickAsyncUnswizzle.
It proves deferred release of initialized staging, preservation of pending CPU
revisions, rejection of remapped bytes, and desktop's unchanged cooldown.
No claim is made about GPU command completion or console frame latency.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
method_start = "void TextureCache<P>::TickAsyncUnswizzle() {"
method_end = "\n    if (!task.initialized) {"
assert active.count(method_start) == pinned.count(method_start) == 1
start = active.index(method_start)
end = active.index(method_end, start)
fragment = active[start:end]
# The extracted prefix ends before the desktop branch consumes its image.
# Keep -Werror in BOTH builds: the mock source may mark that local as unused,
# without changing the production C++ source or suppressing other diagnostics.
compiled_fragment = fragment.replace(
    "Image& image = slot_images[task.image_id];",
    "[[maybe_unused]] Image& image = slot_images[task.image_id];")
assert compiled_fragment != fragment
pinned_prefix = pinned[pinned.index(method_start):pinned.index(method_end, pinned.index(method_start))]
assert fragment.count("FreeDeferredStagingBuffer(task.staging_buffer);") == 1
assert fragment.index("ImageFlagBits::CpuModified | ImageFlagBits::Remapped") < fragment.index(
    "#ifdef PS5_NATIVE\n    if(current_unswizzle_frame > 0)")
assert fragment.count("unswizzle_queue.pop_front();") == 1
assert fragment.index("unswizzle_queue.pop_front();") < fragment.index(
    "#ifdef PS5_NATIVE\n    if(current_unswizzle_frame > 0)")
assert fragment.count("#ifndef PS5_NATIVE") == 1
assert "FreeDeferredStagingBuffer(task.staging_buffer)" not in pinned_prefix
assert "F07 cancel stale GPU unswizzle with deferred staging and native cooldown" in generator
assert "F07 reset idle unswizzle cooldown" in generator
assert "F07 throttle only queued unswizzle batches" in generator
assert "current_unswizzle_frame = 0u;" in fragment.split("return;", 1)[0]
finish_start = "    if (is_final_batch && all_slices_submitted) {"
finish_end = "\n}\n\ntemplate <class P>\nbool TextureCache<P>::ScaleUp"
src_finish = active.find(finish_start, active.find(method_start))
assert src_finish >= 0
assert finish_end in active[src_finish:]
finish_fragment = active[src_finish:active.index(finish_end,src_finish)]
assert "unswizzle_queue.empty() ? 0u : 4u" in finish_fragment

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <vector>
using ImageId = std::size_t;
enum class ImageFlagBits : unsigned {
    CpuModified=1, Remapped=2, Tracked=4, IsDecoding=8
};
unsigned operator~(ImageFlagBits f) {return ~static_cast<unsigned>(f);}
unsigned operator|(ImageFlagBits a,ImageFlagBits b) {
    return static_cast<unsigned>(a)|static_cast<unsigned>(b);
}
struct Flags {
    unsigned bits{};
    Flags& operator|=(ImageFlagBits f){bits|=static_cast<unsigned>(f);return *this;}
    Flags& operator&=(unsigned m){bits&=m;return *this;}
};
unsigned operator&(Flags a,unsigned b){return a.bits & b;}
unsigned operator&(Flags a,ImageFlagBits b){return a.bits & static_cast<unsigned>(b);}
bool True(unsigned b){return b!=0;}
struct PendingUnswizzle {
    ImageId image_id{};
    bool initialized{};
    struct Staging {bool allocated{};} staging_buffer{};
};
struct Image {Flags flags{};};
struct Runtime {
    unsigned deferred_free{};
    void FreeDeferredStagingBuffer(PendingUnswizzle::Staging& stage){
        assert(stage.allocated);
        stage.allocated=false;
        ++deferred_free;
    }
};
template<class P> struct TextureCache {
    std::deque<PendingUnswizzle> unswizzle_queue;
    std::vector<Image> slot_images;
    unsigned current_unswizzle_frame{}, reached_normal{}, untracked{};
    Runtime runtime;
    void UntrackImage(Image& img,ImageId){
        assert(True(img.flags & ImageFlagBits::Tracked));
        img.flags &= ~ImageFlagBits::Tracked;
        ++untracked;
    }
    void TickAsyncUnswizzle();
    void CompleteUnswizzle(bool is_final_batch,bool all_slices_submitted);
};
template<class P>
""" + compiled_fragment + r"""
    ++reached_normal;
}
template <class P>
void TextureCache<P>::CompleteUnswizzle(bool is_final_batch,bool all_slices_submitted) {
    PendingUnswizzle& task=unswizzle_queue.front();
    Image& image=slot_images[task.image_id];
""" + finish_fragment + r"""
}
void Submit(TextureCache<int>& c,ImageId id,bool allocated,bool dirty,bool remapped,bool tracked) {
    c.unswizzle_queue.push_back({id,allocated,{allocated}});
    auto& flags=c.slot_images[id].flags;
    flags.bits=0;
    flags|=ImageFlagBits::IsDecoding;
    if(dirty)flags|=ImageFlagBits::CpuModified;
    if(remapped)flags|=ImageFlagBits::Remapped;
    if(tracked)flags|=ImageFlagBits::Tracked;
}
int main(){
    TextureCache<int> c;
    c.slot_images.resize(5);
#ifdef PS5_NATIVE
    // An obsolete first task cancels immediately, even during a 4-frame
    // cooldown. Submitted GPU batches keep their staging until deferred free.
    Submit(c,0,true,true,false,true);
    c.current_unswizzle_frame=3;
    c.TickAsyncUnswizzle();
    assert(c.unswizzle_queue.empty() && c.runtime.deferred_free==1);
    assert(c.current_unswizzle_frame==0 && c.untracked==1);
    assert(True(c.slot_images[0].flags&ImageFlagBits::CpuModified));
    assert(!True(c.slot_images[0].flags&ImageFlagBits::IsDecoding));
    // Admission failed before allocating staging: never free default handle.
    Submit(c,1,false,true,false,false);
    c.TickAsyncUnswizzle();
    assert(c.unswizzle_queue.empty() && c.runtime.deferred_free==1);
    // Remapping invalidates old bytes even without an explicit CPU dirty flag.
    Submit(c,2,true,false,true,false);
    c.TickAsyncUnswizzle();
    assert(c.unswizzle_queue.empty() && c.runtime.deferred_free==2);
    assert(True(c.slot_images[2].flags&ImageFlagBits::CpuModified));
    // A clean replacement is admitted without inheriting the cancelled
    // task's cooldown. A separately active cooldown still operates normally.
    Submit(c,3,true,false,false,false);
    c.TickAsyncUnswizzle();
    assert(c.current_unswizzle_frame==0 && c.reached_normal==1);
    c.current_unswizzle_frame=2;
    c.TickAsyncUnswizzle();
    assert(c.current_unswizzle_frame==1 && c.reached_normal==1);
    c.current_unswizzle_frame=0;
    c.TickAsyncUnswizzle();
    assert(c.reached_normal==2 && c.unswizzle_queue.size()==1);
    c.unswizzle_queue.clear();
    c.current_unswizzle_frame=4;
    c.TickAsyncUnswizzle();
    assert(c.current_unswizzle_frame==0);
    Submit(c,4,true,false,false,false);
    c.TickAsyncUnswizzle();
    assert(c.reached_normal==3);
#else
    Submit(c,0,true,true,false,true);
    c.current_unswizzle_frame=3;
    c.TickAsyncUnswizzle();
    assert(c.current_unswizzle_frame==2);
    assert(c.unswizzle_queue.size()==1 && c.runtime.deferred_free==0);
    c.current_unswizzle_frame=0;
    c.TickAsyncUnswizzle();
    assert(c.reached_normal==1);
    c.unswizzle_queue.clear();
    c.current_unswizzle_frame=4;
    c.TickAsyncUnswizzle();
    assert(c.current_unswizzle_frame==4);
#endif
    TextureCache<int> finished;
    finished.slot_images.resize(2);
    Submit(finished,0,true,false,false,false);
    Submit(finished,1,true,false,false,false);
    finished.CompleteUnswizzle(true,true);
    assert(finished.unswizzle_queue.size()==1);
    assert(finished.current_unswizzle_frame==4);
    finished.CompleteUnswizzle(true,true);
    assert(finished.unswizzle_queue.empty());
    assert(finished.runtime.deferred_free==2);
#ifdef PS5_NATIVE
    assert(finished.current_unswizzle_frame==0);
#else
    assert(finished.current_unswizzle_frame==4);
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-stale-unswizzle-") as d:
    source_file=Path(d)/"unswizzle.cpp"
    source_file.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            exe=Path(d)/("unswizzle"+opt[1:]+("-native" if native else "-desktop"))
            command=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all"]
            if native: command.append("-DPS5_NATIVE=1")
            result=subprocess.run([*command,str(source_file),"-o",str(exe)],
                                  capture_output=True,text=True,timeout=40)
            assert result.returncode==0,(opt,native,result.stderr[-5000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(opt,native,run.stdout,run.stderr[-5000:])
print("F07_UNSWIZZLE_STALE_HOST_PASS native_cancel=1 uninitialized=1"
      " remap=1 deferred_staging=1 desktop_unchanged=1 idle_reset=1 queued_throttle=1 O0=1 O2=1")

# P0.4: compile the actual native batch-submit branch, including exceptions.
method = active[active.index(method_start):active.index(
    "\n}\n\ntemplate <class P>\nbool TextureCache<P>::ScaleUp", active.index(method_start))]
tag = "        if (z_count > 0) {"
begin = method.index(tag)
close = "        }\n    }\n\n    // Check if complete"
assert close in method[begin:]
block = method[begin:method.index(close, begin)+len("        }\n")]
assert "F07 failed 3D GPU upload dispatch recovery" in generator
assert "runtime.FreeDeferredStagingBuffer(task.staging_buffer);" in block
assert block.index("runtime.AccelerateImageUpload") < block.index("catch (...)")
assert block.index("image.flags |= ImageFlagBits::CpuModified;") < block.index(
    "unswizzle_queue.pop_front();")
cpp_failure = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <stdexcept>
#include <vector>
using u32 = std::uint32_t;
enum class ImageFlagBits : unsigned {CpuModified=1, Tracked=2, IsDecoding=4};
unsigned operator~(ImageFlagBits f){return ~static_cast<unsigned>(f);}
struct Flags {
    unsigned bits{};
    Flags& operator|=(ImageFlagBits f){bits|=static_cast<unsigned>(f);return *this;}
    Flags& operator&=(unsigned bits_){bits&=bits_;return *this;}
};
unsigned operator&(Flags f,ImageFlagBits b){return f.bits&static_cast<unsigned>(b);}
bool True(unsigned a){return a!=0;}
struct Image {Flags flags{};};
struct Staging {bool allocated{true};};
struct Task {
    std::size_t image_id{},last_submitted_offset{},bytes_per_slice{16};
    int info{};
    Staging staging_buffer{};
};
struct Runtime {
    bool fail{};
    unsigned submissions{},frees{};
    void FreeDeferredStagingBuffer(Staging& s) {
        assert(s.allocated);s.allocated=false;++frees;
    }
    void AccelerateImageUpload(Image&,Staging&,const std::vector<int>&,u32,u32) {
        ++submissions;
        if(fail)throw std::runtime_error("mock GPU record rejected");
    }
};
const std::vector<int>& FixSmallVectorADL(const std::vector<int>& v) {return v;}
struct Cache {
    std::deque<Task> unswizzle_queue;
    std::vector<Image> slot_images{1};
    Runtime runtime;
    unsigned current_unswizzle_frame{3},untracked{};
    std::vector<int> FullUploadSwizzles(int) {return {1};}
    void UntrackImage(Image& image,std::size_t) {
        assert(True(image.flags&ImageFlagBits::Tracked));
        image.flags &= ~ImageFlagBits::Tracked;++untracked;
    }
    void Submit(u32 z_start,u32 z_count) {
        auto& task=unswizzle_queue.front();
        auto& image=slot_images[task.image_id];
""" + block + r"""
    }
};
int main() {
    Cache failed;
    failed.unswizzle_queue.push_back({});
    failed.slot_images[0].flags|=ImageFlagBits::IsDecoding;
    failed.slot_images[0].flags|=ImageFlagBits::Tracked;
    failed.runtime.fail=true;
    failed.Submit(0,4);
    assert(failed.unswizzle_queue.empty() && failed.runtime.frees==1);
    assert(failed.runtime.submissions==1 && failed.current_unswizzle_frame==0);
    assert(failed.untracked==1);
    assert(True(failed.slot_images[0].flags & ImageFlagBits::CpuModified));
    assert(!True(failed.slot_images[0].flags & ImageFlagBits::IsDecoding));
    assert(!True(failed.slot_images[0].flags & ImageFlagBits::Tracked));
    Cache recovered;
    recovered.unswizzle_queue.push_back({});
    recovered.slot_images[0].flags|=ImageFlagBits::IsDecoding;
    recovered.Submit(2,3);
    assert(recovered.unswizzle_queue.front().last_submitted_offset==48);
    assert(recovered.runtime.submissions==1 && recovered.runtime.frees==0);
    assert(recovered.current_unswizzle_frame==3);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-3d-dispatch-failure-") as d:
    p=Path(d)/"batch.cpp"
    p.write_text(cpp_failure)
    for opt in ("-O0","-O2"):
        exe=Path(d)/("batch"+opt[1:])
        built=subprocess.run([compiler,"-std=c++20",opt,"-DPS5_NATIVE=1",
                              "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(p),"-o",str(exe)],
                             capture_output=True,text=True,timeout=40)
        assert built.returncode==0,(opt,built.stderr[-5000:])
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
        assert ran.returncode==0,(opt,ran.stderr[-5000:])
print("F07_3D_UPLOAD_FAILURE_RECOVERY_PASS freed=1 dirty=1 pending_cleared=1 retry=1 O0=1 O2=1")
