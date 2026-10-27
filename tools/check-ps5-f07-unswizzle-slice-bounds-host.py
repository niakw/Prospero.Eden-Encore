#!/usr/bin/env python3
"""F07: source-extracted bounds witness for PS5 batched 3D unswizzle.

Checks zero-size, overflowing, incomplete and insufficient-depth GPU slices,
including deferred staging release and retained guest CPU dirty state.
This is a C++20 host fixture, not a PS5 image/presentation claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
start = "#ifdef PS5_NATIVE\n        // Widen BEFORE multiplying:"
end = "        task.last_submitted_offset = 0;"
assert src.count(start) == 1
at = src.index(start)
assert end in src[at:]
block = src[at:src.index(end, at)]
assert "slice_overflow" in block and "invalid_slices" in block
assert block.index("task.bytes_per_slice == 0") < block.index(
    "task.total_size % task.bytes_per_slice")
assert block.index("task.total_size % task.bytes_per_slice") < block.index(
    "task.total_size / task.bytes_per_slice")
assert "std::numeric_limits<size_t>::max()" in block
assert "runtime.FreeDeferredStagingBuffer(task.staging_buffer);" in block
assert "image.flags |= ImageFlagBits::CpuModified;" in block
assert "unswizzle_queue.pop_front();" in block
assert "current_unswizzle_frame = 0u;" in block
assert "F07 guard 3D GPU unswizzle slices and staging bounds" in generator

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
#include <vector>
using u32 = std::uint32_t;
enum class ImageFlagBits:unsigned {CpuModified=1,Tracked=2,IsDecoding=4};
unsigned operator~(ImageFlagBits f){return ~static_cast<unsigned>(f);}
struct Flags {
    unsigned bits{};
    Flags& operator|=(ImageFlagBits f){bits|=static_cast<unsigned>(f);return *this;}
    Flags& operator&=(unsigned x){bits&=x;return *this;}
};
unsigned operator&(Flags x,ImageFlagBits f){return x.bits&static_cast<unsigned>(f);}
bool True(unsigned value){return value!=0;}
struct Image {
    struct Info{struct Size{u32 depth{};} size;} info;
    Flags flags;
};
struct Task {
    std::size_t image_id{},total_size{},bytes_per_slice{},last_submitted_offset{};
    struct Staging{bool allocated{true};} staging_buffer;
};
struct Runtime {
    unsigned deferred{};
    void FreeDeferredStagingBuffer(Task::Staging& s){
        assert(s.allocated);s.allocated=false;++deferred;
    }
};
struct Cache {
    std::deque<Task> unswizzle_queue;
    std::vector<Image> slot_images{1};
    Runtime runtime;
    unsigned untracked{},accepted{},current_unswizzle_frame{3};
    void UntrackImage(Image& img,std::size_t){
        assert(True(img.flags&ImageFlagBits::Tracked));
        img.flags&=~ImageFlagBits::Tracked;++untracked;
    }
    void Check(u32 width_blocks,u32 bytes_per_block,u32 height_blocks) {
        auto& task=unswizzle_queue.front();
        auto& image=slot_images[task.image_id];
        const auto& info=image.info;
""" + block + r"""
        ++accepted;
    }
};
void Invalid(std::size_t total,u32 width,u32 block,u32 height,u32 depth,bool tracked) {
    Cache c;
    c.unswizzle_queue.push_back({.image_id=0,.total_size=total});
    c.slot_images[0].info.size.depth=depth;
    c.slot_images[0].flags|=ImageFlagBits::IsDecoding;
    if(tracked)c.slot_images[0].flags|=ImageFlagBits::Tracked;
    c.Check(width,block,height);
    assert(c.accepted==0 && c.unswizzle_queue.empty());
    assert(c.runtime.deferred==1 && c.current_unswizzle_frame==0);
    assert(True(c.slot_images[0].flags&ImageFlagBits::CpuModified));
    assert(!True(c.slot_images[0].flags&ImageFlagBits::IsDecoding));
    assert(c.untracked==(tracked?1u:0u));
}
int main(){
    Invalid(64,0,16,1,1,true);                      // zero stride, no division
    Invalid(64,1,0,1,1,false);                      // zero block size
    Invalid(8,2,16,1,1,true);                       // slice > staging
    Invalid(65,1,16,1,1,false);                     // incomplete trailing slice
    Invalid(64,1,16,1,5,true);                      // 4 slices, depth 5
    Invalid(64,~u32{0},16,~u32{0},1,false);         // 64-bit product overflow
    Cache ok;
    ok.unswizzle_queue.push_back({.image_id=0,.total_size=64,.last_submitted_offset=9});
    ok.slot_images[0].info.size.depth=1;
    ok.Check(4,16,1);
    assert(ok.accepted==1 && ok.unswizzle_queue.size()==1);
    assert(ok.unswizzle_queue.front().bytes_per_slice==64);
    assert(ok.unswizzle_queue.front().last_submitted_offset==9);
    assert(ok.runtime.deferred==0 && ok.current_unswizzle_frame==3);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-unswizzle-bounds-") as folder:
    source = Path(folder) / "slice.cpp"
    source.write_text(cpp)
    for opt in ("-O0","-O2"):
        executable=Path(folder)/("slice"+opt[1:])
        result=subprocess.run([compiler,"-std=c++20",opt,"-DPS5_NATIVE=1",
                              "-Wall","-Wextra","-Werror",
                              "-fsanitize=undefined","-fno-sanitize-recover=all",
                              str(source),"-o",str(executable)],
                              capture_output=True,text=True,timeout=40)
        assert result.returncode==0,(opt,result.stderr[-6000:])
        run=subprocess.run([str(executable)],capture_output=True,text=True,timeout=15)
        assert run.returncode==0,(opt,run.stdout,run.stderr[-6000:])
print("F07_UNSWIZZLE_SLICE_BOUNDS_PASS zero=2 truncated=1 overflow=1"
      " oversized=1 depth=1 valid=1 deferred=1 O0=1 O2=1")
