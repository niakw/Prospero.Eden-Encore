#!/usr/bin/env python3
"""Compile actual query-sync grouping code under ASan/UBSan: crossing-page results.

Only a host source-extracted invariant, not real GPU timing or guest progression.
"""
from pathlib import Path
import subprocess
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp").read_text()
PIN=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_query_cache.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
CI=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-vulkan-query-page-span-host.py" in CI
assert "Query sync value range overflow" in SRC and "Query sync buffer span exceeds u32" in SRC
assert "Query sync value range overflow" in GEN and "Query sync buffer span exceeds u32" in GEN
mark="void QueryCacheRuntime::SyncValues("
st="    impl->redirect_cache.clear();"
en="    // Vulkan part."
def extract(text):
    part=text[text.index(mark):]
    assert part.count(st)==part.count(en)==1
    return part[part.index(st):part.index(en)]
current=extract(SRC)
pinned=extract(PIN)
assert "last_page" not in pinned and "last_page" in current
assert "loc.second = (std::max)(loc.second, base_end);" in current
assert "static_cast<u32>(pair.second - pair.first)" in SRC
cpp=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>
using DAddr=std::uint64_t;using u32=std::uint32_t;
namespace Core {constexpr DAddr DEVICE_PAGESIZE=4096;}
namespace Common {
DAddr AlignDown(DAddr v,DAddr a){return v-(v%a);}
}
struct Sync {DAddr address;std::size_t size;};
struct Impl {
    std::vector<std::size_t> redirect_cache;
    std::vector<std::pair<DAddr,DAddr>> little_cache;
};
struct QueryCacheRuntime {
    Impl data;
    Impl* impl=&data;
    void Test(std::span<const Sync> values){
        if(values.empty())return;
INJECT
        (void)total_size;
    }
};
int main(){
    constexpr DAddr P=Core::DEVICE_PAGESIZE;
    QueryCacheRuntime c;
    std::array<Sync,1> crossing{{{P-4,8}}};
    c.Test(crossing);
    assert(c.data.little_cache.size()==1);
    assert(c.data.little_cache[0].first==0);
    assert(c.data.little_cache[0].second==2*P);
    assert(c.data.redirect_cache[0]==0);
    std::array<Sync,2> same{{{7,8},{P-4,8}}};
    c.Test(same);
    assert(c.data.little_cache.size()==1);
    assert(c.data.little_cache[0].second==2*P);
    assert(c.data.redirect_cache[0]==0 && c.data.redirect_cache[1]==0);
    std::array<Sync,2> adj{{{4*P+32,8},{5*P-4,8}}};
    c.Test(adj);
    assert(c.data.little_cache.size()==1);
    assert(c.data.little_cache[0].first==4*P);
    assert(c.data.little_cache[0].second==6*P);
    std::array<Sync,1> zero{{{12,0}}};
    bool rejected=false;
    try{c.Test(zero);}catch(const std::overflow_error&){rejected=true;}
    assert(rejected);
    std::array<Sync,1> near_max{{{std::numeric_limits<DAddr>::max()-4,16}}};
    rejected=false;
    try{c.Test(near_max);}catch(const std::overflow_error&){rejected=true;}
    assert(rejected);
    std::array<Sync,1> large{{{0,static_cast<std::size_t>(std::numeric_limits<u32>::max())+1}}};
    rejected=false;
    try{c.Test(large);}catch(const std::overflow_error&){rejected=true;}
    assert(rejected);
    std::puts("ENCORE_QUERY_CROSS_PAGE_HOST_PASS");
}
""".replace("INJECT",current)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 host compiler needed"
with tempfile.TemporaryDirectory(prefix="encore-query-page-span-") as tmp:
    src=Path(tmp)/"query.cpp"; exe=Path(tmp)/"query"
    src.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("HOST_QUERY_PAGE_SPAN_PASS console_GPU_timing=unverified")
