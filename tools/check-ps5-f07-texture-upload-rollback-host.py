#!/usr/bin/env python3
"""F07: negative-control/positive-control for native CPU-image upload rollback."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
s = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
start = "void TextureCache<P>::RefreshContents(Image& image, ImageId image_id) {"
end = "\ntemplate <class P>\ntemplate <typename StagingBuffer>"
assert s.count(start) == 1
body = s[s.index(start):s.index(end, s.index(start))]
assert body.index("image.flags &= ~ImageFlagBits::CpuModified;") < body.index("TrackImage(image, image_id);")
tag = "#ifdef PS5_NATIVE\n    // Synchronous upload failure must not"
i = body.index(tag)
guard = body[i:body.index("#endif\n", i) + len("#endif\n")]
assert "if (!upload_completed)" in guard
assert body.index("bool upload_completed = false;") < body.index("TrackImage(image, image_id);")
assert body.count("upload_completed = true;") == 4
assert "F07 contain native sync texture allocation failure at upload entry" in gen
assert "F07 dirty native sync texture retry after bad allocation" in gen
assert body.count("catch (const std::bad_alloc&)") == 1
assert body.index("try {", body.index("::Eden::Performance::CachePhaseTimer staging_phase")) < body.index(
    "const size_t upload_size = MapSizeBytes(image);")
assert "if (!staging.buffer || staging.mapped_span.size_bytes() < upload_size)" in body
assert body.index("staging.mapped_span.size_bytes() < upload_size") < body.index(
    "UploadImageContents(image, staging);")
assert body.index("upload_completed = true;",body.index("runtime.InsertUploadMemoryBarrier();")) < body.index(
    "catch (const std::bad_alloc&)")
for branch in ("runtime.TransitionImageLayout(image);",
               "QueueAsyncDecode(image, image_id);",
               "QueueAsyncUnswizzle(image, image_id);"):
    first = body.index(branch)
    early_return = body.index("return;", first)
    assert "upload_completed = true;" in body[first:early_return]
for label in ("MSAA","decode","unswizzle"):
    assert f"F07 complete {label} image handoff" in gen
assert "UntrackImage(image, image_id);" in guard
assert "image.flags |= ImageFlagBits::CpuModified;" in guard
# Earlier explicit acknowledgements belong to accepted async/MSAA paths.
# The LAST acknowledgement commits the synchronous GPU upload only after
# the mandatory barrier. Keep this ordering assertion source-extracted.
assert body.index("runtime.InsertUploadMemoryBarrier();") < body.rindex("upload_completed = true;")
assert "F07 restore failed texture upload dirty state" in gen
assert "F07 completed texture upload marker" in gen
assert "F07 defer CPU revision while decode is in flight" in gen
assert body.index("if (True(image.flags & ImageFlagBits::IsDecoding))") < body.index("image.flags &= ~ImageFlagBits::CpuModified;")
cpp = r"""
#include <cassert>
#include <cstdio>
#include <stdexcept>
#include <type_traits>
#include <utility>
struct Maker {};
template<class F> struct Guard { F f; ~Guard(){ f(); } };
template<class F> Guard<std::decay_t<F>> operator+(Maker, F&& f) {
    return {std::forward<F>(f)};
}
#define SCOPE_EXIT auto exit_guard = Maker{} + [&]
enum class ImageFlagBits: unsigned { CpuModified=1, Tracked=2 };
unsigned operator~(ImageFlagBits x){return ~static_cast<unsigned>(x);}
unsigned operator&(unsigned a, ImageFlagBits b){return a & static_cast<unsigned>(b);}
unsigned& operator|=(unsigned& a, ImageFlagBits b){a |= static_cast<unsigned>(b);return a;}
bool True(unsigned a){return a != 0;}
struct Image {unsigned flags{2};};
struct Cache {
    int untracks{};
    void UntrackImage(Image& image, int) {
        assert(True(image.flags & ImageFlagBits::Tracked));
        image.flags &= ~ImageFlagBits::Tracked;
        ++untracks;
    }
    void Refresh([[maybe_unused]] Image& image, int fail) {
        [[maybe_unused]] int image_id = 1;
#ifndef OLD
GUARD
#else
        [[maybe_unused]] bool upload_completed = false;
#endif
        if(fail == 1) throw std::runtime_error("staging");
        if(fail == 2) throw std::runtime_error("pixels");
        if(fail == 3) throw std::runtime_error("barrier");
        upload_completed = true;
    }
};
void Case(int fail) {
    Cache cache;
    Image image;
    bool threw{};
    try {cache.Refresh(image, fail);}
    catch(const std::runtime_error&) {threw = true;}
    assert(threw == (fail != 0));
#ifdef OLD
    assert(fail != 0);
    assert(image.flags == 2 && cache.untracks == 0);
#else
    if(fail == 0) assert(image.flags == 2 && cache.untracks == 0);
    else assert(image.flags == 1 && cache.untracks == 1);
#endif
}
int main(){
#ifndef OLD
    for(int n=0;n<128;++n)for(int f=0;f<=3;++f)Case(f);
    std::puts("NEW_PATH_OK");
#else
    for(int f=1;f<=3;++f)Case(f);
    std::puts("OLD_STALE_REPRODUCED");
#endif
}
"""
cpp = cpp.replace("\nGUARD\n", "\n"+guard)
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-upload-rollback-") as temp:
    path = Path(temp)/"check.cpp"
    path.write_text(cpp)
    for opt in ("-O0","-O2"):
        for old in (False,True):
            out = Path(temp)/(opt[1:]+("old" if old else "new"))
            result = subprocess.run([compiler,"-std=c++20",opt,"-DPS5_NATIVE=1",
                                     "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                                     "-fno-sanitize-recover=all",*(["-DOLD=1"] if old else []),
                                     str(path),"-o",str(out)],
                                    capture_output=True,text=True,timeout=40)
            assert result.returncode == 0,result.stderr
            result = subprocess.run([str(out)],capture_output=True,text=True,timeout=15)
            assert result.returncode == 0 and ("OLD_STALE_REPRODUCED" if old else "NEW_PATH_OK") in result.stdout,(result.stdout,result.stderr)
# Source-extract the native asynchronous decode admission/rollback clauses.
# Throw from pixel preparation, worker enqueue and unswizzle queue admission.
async_start="void TextureCache<P>::QueueAsyncDecode(Image& image, ImageId image_id) {"
async_end="\ntemplate <class P>\nvoid TextureCache<P>::QueueAsyncUnswizzle("
unswizzle_end="\ntemplate <class P>\nvoid TextureCache<P>::TickAsyncDecode()"
assert s.count(async_start)==s.count(async_end)==s.count(unswizzle_end)==1
decode=s[s.index(async_start):s.index(async_end,s.index(async_start))]
unswizzle=s[s.index(async_end)+1:s.index(unswizzle_end,s.index(async_end))]
guard_begin="#ifdef PS5_NATIVE\n    // Never strand IsDecoding"
assert decode.count(guard_begin)==1
guard=decode[decode.index(guard_begin):decode.index("    auto decode = std::make_unique<AsyncDecodeContext>();")]
pointer=decode[decode.index("    auto* decode_ptr = decode.get();")+len("    auto* decode_ptr = decode.get();\n"):decode.index("    decode->image_id = image_id;")]
queue=decode[decode.index("    texture_decode_worker.QueueWork(std::move(func));"):decode.rindex("\n}")]
assert "const bool was_decoding" in guard
assert "async_decodes.pop_back();" in guard
assert "decode_admitted = true;" in queue
assert "incomplete_decode = decode_ptr;" in pointer
assert unswizzle.index("unswizzle_queue.push_back") < unswizzle.rindex("image.flags |= ImageFlagBits::IsDecoding;")
for name in ("F07 decode rollback on admission", "F07 decode rollback pointer",
             "F07 decode successful admission marker",
             "F07 unswizzle queue before pending flag"):
    assert name in gen
native_cpp=r"""
#include <cassert>
#include <cstdint>
#include <functional>
#include <memory>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <vector>
struct Maker {};
template<class F> struct Guard{F fn;~Guard(){fn();}};
template<class F> Guard<std::decay_t<F>> operator+(Maker,F&& f){return {std::forward<F>(f)};}
#define SCOPE_EXIT auto scope_exit_guard = Maker{} + [&]
using ImageId = std::size_t;
enum class ImageFlagBits:unsigned {IsDecoding=1};
struct Flags {
    unsigned bits{};
    Flags& operator|=(ImageFlagBits b){bits|=static_cast<unsigned>(b);return *this;}
    Flags& operator&=(unsigned n){bits&=n;return *this;}
};
unsigned operator~(ImageFlagBits b){return ~static_cast<unsigned>(b);}
unsigned operator&(Flags f,ImageFlagBits b){return f.bits&static_cast<unsigned>(b);}
bool True(unsigned n){return n!=0;}
struct Image{Flags flags{};struct Info{int code{};} info{};};
struct AsyncDecodeContext{};
struct Worker {
    bool fail{};
    unsigned admitted{};
    void QueueWork(std::function<void()> fn) {
        if(fail) throw std::runtime_error("enqueue failure");
        ++admitted;
        fn();
    }
};
struct UnswizzleQueue {
    bool fail{};
    struct Pending{ImageId image_id;Image::Info info;};
    std::vector<Pending> pending;
    void push_back(Pending p){
        if(fail)throw std::runtime_error("push failure");
        pending.push_back(p);
    }
};
template<class P> struct TextureCache {
    std::vector<std::unique_ptr<AsyncDecodeContext>> async_decodes;
    Worker texture_decode_worker;
    UnswizzleQueue unswizzle_queue;
    void ProbeAdmission(Image& image,bool fail_prepare){
__GUARD__
        auto decode=std::make_unique<AsyncDecodeContext>();
        auto* decode_ptr=decode.get();
__POINTER__
        async_decodes.push_back(std::move(decode));
        if(fail_prepare)throw std::runtime_error("preparation failure");
        auto func=[]{};
__QUEUE__
    }
    void QueueAsyncUnswizzle(Image&,ImageId);
};
__UNSWIZZLE__
int main(){
    TextureCache<int> cache;
    Image image;
    bool caught=false;
    try{cache.ProbeAdmission(image,true);}
    catch(const std::runtime_error&){caught=true;}
    assert(caught && !True(image.flags&ImageFlagBits::IsDecoding));
    assert(cache.async_decodes.empty());
    caught=false;
    cache.texture_decode_worker.fail=true;
    try{cache.ProbeAdmission(image,false);}
    catch(const std::runtime_error&){caught=true;}
    assert(caught && !True(image.flags&ImageFlagBits::IsDecoding));
    assert(cache.async_decodes.empty() && cache.texture_decode_worker.admitted==0);
    cache.texture_decode_worker.fail=false;
    cache.ProbeAdmission(image,false);
    assert(True(image.flags&ImageFlagBits::IsDecoding));
    assert(cache.async_decodes.size()==1 && cache.texture_decode_worker.admitted==1);
    // If an older job already owns the flag, a later failed admission
    // must not clear it or erase the older decode's allocation.
    cache.texture_decode_worker.fail=true;
    caught=false;
    try{cache.ProbeAdmission(image,false);}
    catch(const std::runtime_error&){caught=true;}
    assert(caught && True(image.flags&ImageFlagBits::IsDecoding));
    assert(cache.async_decodes.size()==1);
    Image another;
    cache.unswizzle_queue.fail=true;
    caught=false;
    try{cache.QueueAsyncUnswizzle(another,3);}
    catch(const std::runtime_error&){caught=true;}
    assert(caught && !True(another.flags&ImageFlagBits::IsDecoding));
    assert(cache.unswizzle_queue.pending.empty());
    cache.unswizzle_queue.fail=false;
    cache.QueueAsyncUnswizzle(another,3);
    assert(True(another.flags&ImageFlagBits::IsDecoding));
    assert(cache.unswizzle_queue.pending.size()==1);
}
""".replace("__GUARD__",guard).replace("__POINTER__",pointer).replace("__QUEUE__",queue).replace("__UNSWIZZLE__",unswizzle)
with tempfile.TemporaryDirectory(prefix="eden-f07-async-decode-") as directory:
    fixture=Path(directory)/"async.cpp"
    fixture.write_text(native_cpp)
    for opt in ("-O0","-O2"):
        exe=Path(directory)/("async"+opt[1:])
        built=subprocess.run([compiler,"-std=c++20",opt,"-DPS5_NATIVE=1",
                              "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(fixture),"-o",str(exe)],
                             capture_output=True,text=True,timeout=50)
        assert built.returncode==0,(opt,built.stderr[-6000:])
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        assert ran.returncode==0,(opt,ran.stdout,ran.stderr[-6000:])
print("F07_ASYNC_DECODE_ADMISSION_PASS prepare=1 enqueue=1 previous_decode=1 unswizzle=1 O0=1 O2=1")

print("F07_UPLOAD_ROLLBACK_HOST_PASS O0=1 O2=1 exception_stages=3 success=1")

# The native staging guard below is extracted verbatim from RefreshContents,
# compiled in both optimization modes, and exercised with a Vulkan-null
# buffer whose CPU mapping appears full (as well as short/valid mappings).
native_start = "    const size_t upload_size = MapSizeBytes(image);"
native_stop = "#else\n    auto staging = runtime.UploadStagingBuffer"
native_block = body[body.index(native_start):
                    body.index(native_stop, body.index(native_start))]
assert "if (!staging.buffer || staging.mapped_span.size_bytes() < upload_size)" in native_block
staging_cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>
struct Image {std::size_t size{8};};
std::size_t MapSizeBytes(const Image& image){return image.size;}
struct Map {std::size_t buffer{};std::span<std::uint8_t> mapped_span{};};
struct Runtime {
    Map next{};
    Map UploadStagingBuffer(std::size_t){return next;}
};
struct Cache {
    Runtime runtime{};
    unsigned uploads{};
    void Refresh(Image& image) {
__NATIVE_BLOCK__
        ++uploads;
    }
};
int main() {
    std::vector<std::uint8_t> bytes(8);
    Image image{};
    Cache cache{};
    cache.runtime.next = {0,{bytes.data(),bytes.size()}};
    cache.Refresh(image);
    assert(cache.uploads==0);
    cache.runtime.next = {1,{bytes.data(),bytes.size()-1}};
    cache.Refresh(image);
    assert(cache.uploads==0);
    cache.runtime.next = {};
    cache.Refresh(image);
    assert(cache.uploads==0);
    cache.runtime.next = {1,{bytes.data(),bytes.size()}};
    cache.Refresh(image);
    assert(cache.uploads==1);
}
""".replace("__NATIVE_BLOCK__",native_block)
with tempfile.TemporaryDirectory(prefix="eden-f07-native-staging-handle-") as directory:
    path=Path(directory)/"staging.cpp"
    path.write_text(staging_cpp)
    for opt in ("-O0","-O2"):
        exe=Path(directory)/("staging"+opt[1:])
        built=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra",
                              "-Werror","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(path),"-o",str(exe)],
                             capture_output=True,text=True,timeout=40)
        assert built.returncode==0,(opt,built.stderr[-6000:])
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        assert ran.returncode==0,(opt,ran.stderr[-5000:])
print("F07_SYNC_STAGING_HANDLE_PASS null_full=1 short=1 empty=1 valid=1 O0=1 O2=1")

# The Vulkan staging pool gives stream uploads exact subspans but
# power-of-two pooled buffers return their WHOLE mapped allocation. Read
# exactly MapSizeBytes(image), never its rounded staging capacity on PS5.
upload_method_start = "void TextureCache<P>::UploadImageContents(Image& image, StagingBuffer& staging) {"
upload_method_end = "\ntemplate <class P>\nImageViewId TextureCache<P>::CreateImageView("
assert s.count(upload_method_start) == s.count(upload_method_end) == 1
upload_method = s[s.index(upload_method_start):s.index(upload_method_end,s.index(upload_method_start))]
accelerated_start = "    if (True(image.flags & ImageFlagBits::AcceleratedUpload)) {"
accelerated_end = "        const auto uploads = FullUploadSwizzles(image.info);"
accelerated = upload_method[upload_method.index(accelerated_start):
                            upload_method.index(accelerated_end)]
assert "F07 bound native accelerated texture guest read to requested upload size" in gen
assert accelerated.count("gpu_memory->ReadBlock(") == 2
assert accelerated.count("MapSizeBytes(image)") == 1
assert accelerated.index("#ifdef PS5_NATIVE") < accelerated.index("MapSizeBytes(image)") < accelerated.index("#else")
assert accelerated.index("mapped_span.size_bytes()") > accelerated.index("#else")
assert body.index("staging.mapped_span.size_bytes() < upload_size") < body.index("UploadImageContents(image, staging);")
read_branch = accelerated[accelerated.index("#ifdef PS5_NATIVE"):]
cpp_accelerated = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>
using GPUVAddr=std::uint64_t;
using u8=std::uint8_t;
namespace VideoCommon {enum class CacheType { NoTextureCache }; }
struct Image {std::size_t upload_bytes{};};
std::size_t MapSizeBytes(const Image& image) {return image.upload_bytes;}
struct Memory {
    std::size_t size_read{};
    unsigned calls{};
    void ReadBlock(GPUVAddr, u8* target, std::size_t size, VideoCommon::CacheType) {
        assert(target); size_read=size; ++calls;
    }
};
struct Cache {
    Memory* gpu_memory;
    void Upload(Image& image, std::span<u8> mapped_span) {
        // The historical desktop read uses the pooled span, not image size.
        // Retain the parameter for the native size-bound source extraction.
        static_cast<void>(image);
        GPUVAddr gpu_addr=0x1000;
__ACTUAL_READ__
    }
};
int main() {
    Memory memory;
    Cache cache{&memory};
    Image image{9};
    std::vector<u8> pooled(16);
    cache.Upload(image, pooled);
    assert(memory.calls==1);
#ifdef PS5_NATIVE
    assert(memory.size_read==9); // full 16-byte pooled span is NOT guest data
#else
    assert(memory.size_read==16); // unchanged historical desktop
#endif
    pooled.resize(9); // an exact stream-buffer staging subspan
    cache.Upload(image, pooled);
    assert(memory.calls==2 && memory.size_read==9);
    pooled.resize(16);
    image.upload_bytes=13;
    cache.Upload(image, pooled);
#ifdef PS5_NATIVE
    assert(memory.calls==3 && memory.size_read==13);
#else
    assert(memory.calls==3 && memory.size_read==16);
#endif
}
""".replace("__ACTUAL_READ__",read_branch)
with tempfile.TemporaryDirectory(prefix="eden-f07-accelerated-staging-read-") as directory:
    fixture=Path(directory)/"accelerated.cpp"
    fixture.write_text(cpp_accelerated)
    for mode in (False,True):
        for opt in ("-O0","-O2"):
            executable=Path(directory)/(("ps5" if mode else "desktop")+opt[2:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if mode else []),
                 str(fixture),"-o",str(executable)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(mode,opt,built.stderr[-5000:])
            ran=subprocess.run([str(executable)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(mode,opt,ran.stderr[-5000:])
print("F07_ACCELERATED_TEXTURE_READ_BOUNDS_PASS pooled_9of16=1 pooled_13of16=1 desktop_original=1 O0=1 O2=1")

