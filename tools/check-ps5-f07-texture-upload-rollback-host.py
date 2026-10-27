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
assert "UntrackImage(image, image_id);" in guard
assert "image.flags |= ImageFlagBits::CpuModified;" in guard
assert body.index("runtime.InsertUploadMemoryBarrier();") < body.index("upload_completed = true;")
assert "F07 restore failed texture upload dirty state" in gen
assert "F07 completed texture upload marker" in gen
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
print("F07_UPLOAD_ROLLBACK_HOST_PASS O0=1 O2=1 exception_stages=3 success=1")
