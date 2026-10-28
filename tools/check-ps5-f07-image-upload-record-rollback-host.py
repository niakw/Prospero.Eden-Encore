#!/usr/bin/env python3
"""F07: accepted Vulkan upload Record is the image-initialization commit."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
oracle=(root/"tools/check-vulkan-deferred-copy-ownership-host.py").read_text()
begin="    const bool was_initialized = std::exchange(initialized, true);"
new_begin="    // Record can reject before accepting this copy."
start=source.index(new_begin)
start=source.rfind("#ifdef PS5_NATIVE",0,start)
end_marker="    initialized = true;\n#endif"
end=source.index(end_marker,start)+len(end_marker)
fragment=source[start:end]
assert fragment.count("scheduler->Record(")==1
assert fragment.count("std::exchange(initialized, true)")==1
assert fragment.index("scheduler->Record(") < fragment.rindex("initialized = true;")
assert fragment.count("#ifdef PS5_NATIVE")==2
assert source.count(new_begin)==1
assert "F07 native image initialized only after accepted upload record" in generator
assert "F07 native image initialized only after accepted upload record" in oracle
for path in (".github/workflows/encore-core-fast-gate.yml",
             ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-image-upload-record-rollback-host.py" in (root/path).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>
using VkBuffer=std::uint64_t;
using VkImage=std::uint64_t;
using VkImageAspectFlags=std::uint32_t;
namespace vk { struct CommandBuffer {}; }
namespace VideoCommon {
template<class T> const T& FixSmallVectorADL(const T& data) { return data; }
}
static unsigned uploaded=0;
static bool last_was_initialized=false;
void CopyBufferToImage(vk::CommandBuffer, VkBuffer, VkImage, VkImageAspectFlags,
                       bool was_initialized, const std::vector<int>& data) {
    assert(data.size()==1);
    ++uploaded;
    last_was_initialized=was_initialized;
}
struct Scheduler {
    bool refuse{};
    unsigned accepted{};
    template<class Fn> void Record(Fn&& fn) {
        if(refuse) throw std::runtime_error("mock queue rejection");
        ++accepted;
        fn(vk::CommandBuffer{});
    }
};
struct Image {
    bool initialized{};
    Scheduler* scheduler;
    void Submit() {
        std::vector<int> vk_copies{42};
        VkBuffer src_buffer=1;
        VkImage vk_image=2;
        VkImageAspectFlags vk_aspect_mask=4;
""" + fragment + r"""
    }
};
int main() {
    Scheduler scheduler{};
    Image image{false,&scheduler};
    scheduler.refuse=true;
    bool rejected=false;
    try {image.Submit();}
    catch(const std::runtime_error&) { rejected=true; }
    assert(rejected && scheduler.accepted==0 && uploaded==0);
#ifdef PS5_NATIVE
    assert(!image.initialized);
#else
    assert(image.initialized);
#endif
    scheduler.refuse=false;
    image.Submit();
    assert(scheduler.accepted==1 && uploaded==1 && image.initialized);
#ifdef PS5_NATIVE
    assert(!last_was_initialized);
#else
    assert(last_was_initialized);
#endif
    scheduler.refuse=true;
    rejected=false;
    try {image.Submit();}
    catch(const std::runtime_error&) { rejected=true; }
    assert(rejected && image.initialized && uploaded==1);
    scheduler.refuse=false;
    image.Submit();
    assert(scheduler.accepted==2 && uploaded==2 && last_was_initialized);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-f07-upload-commit-") as td:
    path=Path(td)/"test.cpp"
    path.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            executable=Path(td)/(("native" if native else "desktop")+opt[1:])
            defines=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",*defines,
                                  str(path),"-o",str(executable)],
                                  capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            run=subprocess.run([str(executable)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_UPLOAD_INIT_COMMIT_PASS reject_no_publish=1 native_first_retry_layout=1 original_desktop=1 repeated_upload=1 O0=1 O2=1 UBSan=1")
