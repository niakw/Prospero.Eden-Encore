#!/usr/bin/env python3
"""Source-extracted Vulkan conditional-render state inversion ASan/UBSan witness.

A single VkBuffer/VkDeviceSize can support either inverted or normal
comparison. Reusing it must re-record the flags when equality flips.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
NATIVE=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp").read_text()
PINNED=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_query_cache.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
FLOW=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-vulkan-query-conditional-inversion-host.py" in FLOW
assert "impl->hcr_setup.flags == flags" in NATIVE and "impl->hcr_setup.flags == flags" in GEN
start="void QueryCacheRuntime::HostConditionalRenderingCompareValueImpl("
end="void QueryCacheRuntime::HostConditionalRenderingCompareBCImpl("
def grab(text):
    assert text.count(start)==text.count(end)==1
    return text[text.index(start):text.index(end)]
current=grab(NATIVE)
baseline=grab(PINNED)
assert "impl->hcr_setup.flags == flags" not in baseline
assert current.count("impl->hcr_setup.flags = flags;")==1
cpp=r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <utility>
using u32=std::uint32_t;
using VkBuffer=u32;
using VkConditionalRenderingFlagsEXT=u32;
constexpr u32 VK_CONDITIONAL_RENDERING_INVERTED_BIT_EXT=1;
namespace VideoCommon {
struct LookupData{u32 address;};
enum class ObtainBufferSynchronize{FullSynchronize};
enum class ObtainBufferOperation{DoNothing};
}
struct Buffer{VkBuffer Handle()const{return 17;}};
struct BufferCache {
    std::mutex mutex;
    Buffer storage;
    std::pair<Buffer*,u32> ObtainCPUBuffer(u32,u32,
        VideoCommon::ObtainBufferSynchronize,
        VideoCommon::ObtainBufferOperation){return {&storage,64};}
};
struct Setup{VkBuffer buffer{};u32 offset{};VkConditionalRenderingFlagsEXT flags{};};
struct Impl{
    BufferCache buffer_cache;
    VkBuffer hcr_buffer{};
    u32 hcr_offset{};
    Setup hcr_setup{};
    bool hcr_is_set=false,is_hcr_running=false;
};
struct QueryCacheRuntime {
    Impl owner{};
    Impl* impl=&owner;
    int pauses=0,resumes=0;
    void PauseHostConditionalRendering(){++pauses; impl->is_hcr_running=false;}
    void ResumeHostConditionalRendering(){++resumes; impl->is_hcr_running=true;}
    void HostConditionalRenderingCompareValueImpl(VideoCommon::LookupData,bool);
};
INJECT
int main(){
    QueryCacheRuntime q;
    VideoCommon::LookupData guest{1234};
    q.HostConditionalRenderingCompareValueImpl(guest,true);
    assert(q.impl->hcr_setup.buffer==17 && q.impl->hcr_setup.offset==64);
    assert(q.impl->hcr_setup.flags==1 && q.impl->hcr_is_set);
    q.impl->is_hcr_running=true;
    q.HostConditionalRenderingCompareValueImpl(guest,true);
    assert(q.pauses==0 && q.resumes==0 && q.impl->is_hcr_running);
    q.HostConditionalRenderingCompareValueImpl(guest,false);
    assert(q.impl->hcr_setup.flags==0);
    assert(q.pauses==1 && q.resumes==1 && q.impl->is_hcr_running);
    q.HostConditionalRenderingCompareValueImpl(guest,false);
    assert(q.pauses==1 && q.resumes==1);
    q.HostConditionalRenderingCompareValueImpl(guest,true);
    assert(q.impl->hcr_setup.flags==1);
    assert(q.pauses==2 && q.resumes==2);
    std::puts("ENCORE_CONDITIONAL_INVERSION_STATE_PASS");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-conditional-invert-") as td:
    folder=Path(td)
    for label,method,positive in (("pinned",baseline,False),("active",current,True)):
        source=folder/(label+".cpp")
        exe=folder/label
        source.write_text(cpp.replace("INJECT",method))
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        str(source),"-o",str(exe)],check=True,timeout=90)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        if positive:
            assert result.returncode==0,(label,result.stderr)
        else:
            assert result.returncode!=0, "Pinned baseline unexpectedly accepted inverted state"
print("HOST_VULKAN_QUERY_CONDITIONAL_INVERSION_PASS; console timing unverified")
