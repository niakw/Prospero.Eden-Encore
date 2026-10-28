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
assert "task.total_size / task.bytes_per_slice != static_cast<size_t>(info.size.depth)" in block
assert block.index("task.bytes_per_slice == 0") < block.index(
    "task.total_size % task.bytes_per_slice")
assert block.index("task.total_size % task.bytes_per_slice") < block.index(
    "task.total_size / task.bytes_per_slice")
assert "std::numeric_limits<size_t>::max()" in block
assert "runtime.FreeDeferredStagingBuffer(task.staging_buffer);" not in block
assert "task.staging_buffer = staging;" in block
assert "staging.mapped_span.size() < task.total_size" in block
assert "runtime.FreeDeferredStagingBuffer(staging);" in block
assert "F07 3D unswizzle staging OOM and short mapping recovery" in generator
assert "image.flags |= ImageFlagBits::CpuModified;" in block
assert "unswizzle_queue.pop_front();" in block
assert "current_unswizzle_frame = 0u;" in block
assert "F07 guard 3D GPU unswizzle slices and staging bounds" in generator
assert "F07 allocate GPU unswizzle staging after native bounds validation" in generator
assert "F07 reject invalid unswizzle geometry without staged allocation" in generator
assert "F07 commit native 3D staging only after validation" in generator

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
#include <new>
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
    struct Staging{
        bool allocated{false};
        struct Mapped{std::size_t bytes{};std::size_t size() const{return bytes;}} mapped_span{};
        bool buffer{false};
    } staging_buffer;
};
struct Runtime {
    unsigned deferred{},allocations{};
    bool fail{},short_mapping{};
    Task::Staging UploadStagingBuffer(std::size_t size,bool deferred_){
        assert(size!=0 && deferred_);
        ++allocations;
        if(fail) throw std::bad_alloc{};
        return {true,{short_mapping?size-1:size},true};
    }
    void FreeDeferredStagingBuffer(Task::Staging& s){
        assert(s.allocated && s.buffer);
        s.allocated=false;s.buffer=false;++deferred;
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
void StagingFailure(bool short_mapping) {
    Cache c;
    c.unswizzle_queue.push_back({.image_id=0,.total_size=64,.staging_buffer={false}});
    c.slot_images[0].info.size.depth=1;
    c.slot_images[0].flags|=ImageFlagBits::IsDecoding;
    c.slot_images[0].flags|=ImageFlagBits::Tracked;
    c.runtime.fail=!short_mapping;
    c.runtime.short_mapping=short_mapping;
    c.Check(4,16,1);
    assert(c.accepted==0 && c.unswizzle_queue.empty());
    assert(c.runtime.allocations==1);
    assert(c.runtime.deferred==(short_mapping?1u:0u));
    assert(c.current_unswizzle_frame==0u && c.untracked==1);
    assert(True(c.slot_images[0].flags&ImageFlagBits::CpuModified));
    assert(!True(c.slot_images[0].flags&ImageFlagBits::IsDecoding));
    assert(!True(c.slot_images[0].flags&ImageFlagBits::Tracked));
}
void Invalid(std::size_t total,u32 width,u32 block,u32 height,u32 depth,bool tracked) {
    Cache c;
    c.unswizzle_queue.push_back({.image_id=0,.total_size=total,.staging_buffer={false}});
    c.slot_images[0].info.size.depth=depth;
    c.slot_images[0].flags|=ImageFlagBits::IsDecoding;
    if(tracked)c.slot_images[0].flags|=ImageFlagBits::Tracked;
    c.Check(width,block,height);
    assert(c.accepted==0 && c.unswizzle_queue.empty());
    assert(c.runtime.deferred==0 && c.runtime.allocations==0 && c.current_unswizzle_frame==0);
    assert(True(c.slot_images[0].flags&ImageFlagBits::CpuModified));
    assert(!True(c.slot_images[0].flags&ImageFlagBits::IsDecoding));
    assert(c.untracked==(tracked?1u:0u));
}
int main(){
    StagingFailure(false);
    StagingFailure(true);
    Invalid(64,0,16,1,1,true);                      // zero stride, no division
    Invalid(64,1,0,1,1,false);                      // zero block size
    Invalid(8,2,16,1,1,true);                       // slice > staging
    Invalid(65,1,16,1,1,false);                     // incomplete trailing slice
    Invalid(64,1,16,1,5,true);                      // 4 slices, depth 5
    Invalid(128,1,16,1,1,false);                   // 8 slices, depth 1
    Invalid(64,1,16,1,0,true);                     // nonempty GPU data, zero depth
    Invalid(64,~u32{0},16,~u32{0},1,false);         // 64-bit product overflow
    Cache ok;
    ok.unswizzle_queue.push_back({.image_id=0,.total_size=64,.last_submitted_offset=9,.staging_buffer={false}});
    ok.slot_images[0].info.size.depth=1;
    ok.Check(4,16,1);
    assert(ok.accepted==1 && ok.unswizzle_queue.size()==1);
    assert(ok.unswizzle_queue.front().bytes_per_slice==64);
    assert(ok.unswizzle_queue.front().last_submitted_offset==9);
    assert(ok.runtime.deferred==0 && ok.runtime.allocations==1 &&
           ok.unswizzle_queue.front().staging_buffer.allocated &&
           ok.current_unswizzle_frame==3);
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
      " oversized=1 depth=3 valid=1 allocation_order=1 oom=1 short_span=1 O0=1 O2=1")

# F07 P0.4: a missing image-format-list extension must not disable the
# unrelated native BCn-3D storage-buffer compute pass. Extract the exact
# constructor branch, not a hand-authored approximation.
runtime_src = (root / "vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
constructor = runtime_src[runtime_src.index("TextureCacheRuntime::TextureCacheRuntime("):
                          runtime_src.index("void TextureCacheRuntime::Finish()")]
fallback_start = constructor.index("    if (!device.IsKhrImageFormatListSupported()) {")
fallback_end = constructor.index("    for (size_t index_a", fallback_start)
fallback = constructor[fallback_start:fallback_end]
assert "#ifdef PS5_NATIVE" in fallback
assert fallback.index("bl3d_unswizzle_pass.emplace") < fallback.index("        return;")
assert "VK_KHR_image_format_list" in fallback
late_start = constructor.rindex("    if (Settings::values.gpu_unswizzle_enabled.GetValue()) {")
late = constructor[late_start:constructor.index("\n}", late_start)]
assert late.count("bl3d_unswizzle_pass.emplace") == 1
assert constructor.count("bl3d_unswizzle_pass.emplace") == 2
oracle = (root / "tools/check-vendored-vulkan-fork.py").read_text()
assert "BCn 3D compute-buffer pass" in oracle
fixture = r"""
#include <cassert>
#include <optional>
namespace Settings {
struct Bool { bool enabled{}; bool GetValue() const {return enabled;} };
struct Values { Bool gpu_unswizzle_enabled; };
inline Values values{};
}
struct Device { bool extension{}; bool IsKhrImageFormatListSupported() const {return extension;} };
struct Pass {
    Pass(Device&,int&,int&,int&,int&) {++instances;}
    inline static unsigned instances{};
};
struct Probe {
    Device device{};
    int scheduler{}, descriptor_pool{}, staging_buffer_pool{}, compute_pass_descriptor_queue{};
    std::optional<Pass> bl3d_unswizzle_pass;
    void Init() {
""" + fallback + late + r"""
    }
};
int main() {
    for (bool extension: {false,true}) {
        for (bool enabled: {false,true}) {
            Settings::values.gpu_unswizzle_enabled.enabled=enabled;
            Pass::instances=0;
            Probe p; p.device.extension=extension; p.Init();
            unsigned expected=enabled && (
#ifdef PS5_NATIVE
                true
#else
                extension
#endif
            ) ? 1u:0u;
            assert(Pass::instances==expected);
            assert(p.bl3d_unswizzle_pass.has_value()==(expected!=0));
        }
    }
}
"""
# C++ initializer-list range for(bool) needs initializer_list explicitly.
fixture = fixture.replace("#include <optional>", "#include <optional>\n#include <initializer_list>")
with tempfile.TemporaryDirectory(prefix="eden-f07-bcn3d-constructor-") as folder:
    source = Path(folder)/"ctor.cpp"
    source.write_text(fixture)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe = Path(folder)/("bcn3d"+opt[1:]+("-ps5" if native else "-desktop"))
            built = subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                    *(['-DPS5_NATIVE=1'] if native else []),
                                    str(source),"-o",str(exe)],
                                   capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-5000:])
            ran = subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-5000:])
print("F07_BCN3D_PASS_UNSUPPORTED_IMAGE_FORMAT_LIST_PASS native=1 desktop=1 extension_on_off=1 setting_on_off=1 O0=1 O2=1")


# BCn 3D: never mark an unavailable GPU compute upload as complete.
# Compile the production runtime function, including PS5 and desktop branches.
accel_start="void TextureCacheRuntime::AccelerateImageUpload("
accel_end="\n}\n\nvoid TextureCacheRuntime::TransitionImageLayout("
assert runtime_src.count(accel_start)==1
assert accel_end in runtime_src[runtime_src.index(accel_start):]
accel=runtime_src[runtime_src.index(accel_start):
                  runtime_src.index(accel_end,runtime_src.index(accel_start))+2]
assert "F07 native BCn 3D unavailable pass retry signal" in (
    root/"tools/prepare-vulkan-port.py").read_text()
assert "throw std::runtime_error" in accel
assert accel.index("throw std::runtime_error") < accel.index(
    "ASSERT(false &&", accel.index("if (!Settings::values.gpu_unswizzle_enabled"))
accelerated_cpp=r"""
#include <cassert>
#include <cstdint>
#include <optional>
#include <span>
#include <stdexcept>
using u32=std::uint32_t;
enum class ImageType {e2D,e3D};
struct Image {
    struct Info {int format{};ImageType type{ImageType::e3D};
        struct Resources {int levels{1},layers{1};} resources;} info{};
};
struct StagingBufferRef {};
namespace VideoCommon {struct SwizzleParameters {};}
bool IsPixelFormatASTC(int fmt){return fmt==2;}
bool IsPixelFormatBCn(int fmt){return fmt==1;}
#define ASSERT(...) ((void)0)
namespace Settings {
struct Toggle {bool value{};bool GetValue()const{return value;}};
struct Values {Toggle gpu_unswizzle_enabled;};
inline Values values{};
}
struct Pass {
    unsigned calls{};
    void Assemble(Image&,const StagingBufferRef&,std::span<const VideoCommon::SwizzleParameters>) {
        ++calls;
    }
    void Unswizzle(Image&,const StagingBufferRef&,
                   std::span<const VideoCommon::SwizzleParameters>,u32,u32) {
        ++calls;
    }
};
struct TextureCacheRuntime {
    std::optional<Pass> astc_decoder_pass;
    std::optional<Pass> bl3d_unswizzle_pass;
    void AccelerateImageUpload(Image&,const StagingBufferRef&,
                               std::span<const VideoCommon::SwizzleParameters>,u32,u32);
};
""" + accel + r"""
int main(){
    Image image;image.info.format=1;
    StagingBufferRef staging{};
    TextureCacheRuntime cache;
    Settings::values.gpu_unswizzle_enabled.value=true;
    bool rejected=false;
    try{cache.AccelerateImageUpload(image,staging,{},0,1);}
    catch(const std::runtime_error&){rejected=true;}
#ifdef PS5_NATIVE
    assert(rejected);
#else
    assert(!rejected);
#endif
    cache.bl3d_unswizzle_pass.emplace();
    cache.AccelerateImageUpload(image,staging,{},0,1);
    assert(cache.bl3d_unswizzle_pass->calls==1);
    Settings::values.gpu_unswizzle_enabled.value=false;
    rejected=false;
    try{cache.AccelerateImageUpload(image,staging,{},0,1);}
    catch(const std::runtime_error&){rejected=true;}
#ifdef PS5_NATIVE
    assert(rejected);
#else
    assert(!rejected);
#endif
    Settings::values.gpu_unswizzle_enabled.value=true;
    Image astc;astc.info.format=2;
    cache.astc_decoder_pass.emplace();
    cache.AccelerateImageUpload(astc,staging,{},0,0);
    assert(cache.astc_decoder_pass->calls==1);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-bcn3d-unavailable-") as folder:
    source=Path(folder)/"unavailable.cpp"
    source.write_text(accelerated_cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            binary=Path(folder)/("unavailable"+opt[1:]+("-ps5" if native else "-desktop"))
            command=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                     *(['-DPS5_NATIVE=1'] if native else []),
                     str(source),"-o",str(binary)]
            built=subprocess.run(command,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-5000:])
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
            assert result.returncode==0,(native,opt,result.stderr[-5000:])
print("F07_BCN3D_PASS_UNAVAILABLE_SIGNAL_PASS missing_pass=1 settings_changed=1 valid_bc3d=1 astc=1 ps5=1 desktop=1 O0=1 O2=1")
