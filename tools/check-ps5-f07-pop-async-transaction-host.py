#!/usr/bin/env python3
"""F07: source-extracted native async readback consumption must remain retryable."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
start=source.index("void TextureCache<P>::PopAsyncFlushes() {")
end=source.index("\ntemplate <class P>",start+20)
method=source[start:end]
marker="#ifdef PS5_NATIVE\n        // Keep staging queued until the entire guest download is consumed."
assert method.count(marker)==1
begin=method.index(marker)
finish=method.index("\n#endif",begin)+len("\n#endif")
block=method[begin:finish]
assert "#else\n        auto download_map = std::move(async_buffers.front());" in block
assert "boost::container::small_vector<size_t, 4> remaining_offsets;" in block
assert block.index("async_buffers_death_ring.emplace_back(buffer);") < block.index("SwizzleImage(")
assert block.index("slot_buffer_downloads.erase(download_info.object_id);") > block.index("WriteBlockUnsafe(")
assert "F07 transactional native async download replay and deferred release" in generator
for wf in (".github/workflows/encore-core-fast-gate.yml",".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-pop-async-transaction-host.py" in (root/wf).read_text()

cpp=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
#include <new>
#include <span>
#include <stdexcept>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>
#include <boost/container/small_vector.hpp>
using u8=std::uint8_t;
namespace Common {
std::size_t AlignUp(std::size_t n,std::size_t a){return (n+a-1)/a*a;}
}
struct Maker {};
template<class F> struct ScopeGuard{F f;~ScopeGuard(){f();}};
template<class F> ScopeGuard<std::decay_t<F>> operator+(Maker,F&&f){return {std::forward<F>(f)};}
#define SCOPE_EXIT auto guard_pop = Maker{} + [&]
struct Memory{
    bool fail_swizzle{},fail_write{};
    unsigned swizzles{},writes{};
    void WriteBlockUnsafe(std::uint64_t,const u8*,std::size_t){
        if(fail_write)throw std::runtime_error("guest DMA rejected");
        ++writes;
    }
};
struct ImageInfo {};
struct ImageBase{
    ImageInfo info{};
    std::uint64_t gpu_addr{};
    std::size_t unswizzled_size_bytes{32};
};
std::vector<int> FullDownloadCopies(const ImageInfo&){return {1};}
std::vector<int> FixSmallVectorADL(std::vector<int> v){return v;}
void SwizzleImage(Memory& mem,std::uint64_t,const ImageInfo&,const std::vector<int>&,
                  std::span<u8> span,std::vector<u8>&){
    assert(span.size()>=32);
    if(mem.fail_swizzle)throw std::runtime_error("swizzle rejected");
    ++mem.swizzles;
}
struct PendingDownload{bool is_swizzle{};std::size_t async_buffer_id{};unsigned object_id{};};
struct BufferDownload{std::uint64_t address{};std::size_t size{};};
struct Staging{
    std::size_t buffer{};
    std::size_t offset{};
    std::span<u8> mapped_span;
};
struct Cache{
    std::array<u8,128> staging_data{};
    Memory memory;
    Memory* gpu_memory{&memory};
    std::vector<ImageBase> slot_images{1};
    std::unordered_map<unsigned,BufferDownload> slot_buffer_downloads;
    std::vector<u8> swizzle_data_buffer;
    std::deque<std::vector<PendingDownload>> committed_downloads;
    std::deque<std::vector<Staging>> async_buffers;
    std::deque<Staging> async_buffers_death_ring;
    void Setup(){
        committed_downloads.push_back({{false,1,42},{true,0,0}});
        async_buffers.push_back({{111,64,staging_data},{222,0,staging_data}});
        slot_buffer_downloads.emplace(42,BufferDownload{55,12});
    }
    void Pop(){
        const auto& download_ids=committed_downloads.front();
__BLOCK__
    }
};
int main(){
    Cache swizzle_failure;
    swizzle_failure.Setup();
#ifdef PS5_NATIVE
    swizzle_failure.memory.fail_swizzle=true;
    bool failed=false;
    try{swizzle_failure.Pop();}catch(const std::runtime_error&){failed=true;}
    assert(failed);
    assert(swizzle_failure.committed_downloads.size()==1);
    assert(swizzle_failure.async_buffers.size()==1);
    assert(swizzle_failure.async_buffers.front()[0].offset==64);
    assert(swizzle_failure.async_buffers_death_ring.empty());
    assert(swizzle_failure.slot_buffer_downloads.contains(42));
    swizzle_failure.memory.fail_swizzle=false;
#endif
    swizzle_failure.Pop();
    assert(swizzle_failure.committed_downloads.empty());
    assert(swizzle_failure.async_buffers.empty());
    assert(swizzle_failure.async_buffers_death_ring.size()==2);
    assert(swizzle_failure.memory.swizzles==1 && swizzle_failure.memory.writes==1);
    assert(swizzle_failure.slot_buffer_downloads.empty());
#ifdef PS5_NATIVE
    Cache dma_failure;
    dma_failure.Setup();
    dma_failure.memory.fail_write=true;
    bool failed_dma=false;
    try{dma_failure.Pop();}catch(const std::runtime_error&){failed_dma=true;}
    assert(failed_dma);
    assert(dma_failure.committed_downloads.size()==1);
    assert(dma_failure.async_buffers.front()[0].offset==64);
    assert(dma_failure.async_buffers_death_ring.empty());
    assert(dma_failure.slot_buffer_downloads.contains(42));
    dma_failure.memory.fail_write=false;
    dma_failure.Pop();
    assert(dma_failure.committed_downloads.empty());
    assert(dma_failure.async_buffers_death_ring.size()==2);
    assert(dma_failure.memory.writes==1 && dma_failure.memory.swizzles==2);
    Cache invalid;
    invalid.Setup();
    invalid.async_buffers.front()[0].buffer=0;
    bool invalid_rejected=false;
    try{invalid.Pop();}catch(const std::bad_alloc&){invalid_rejected=true;}
    assert(invalid_rejected && invalid.committed_downloads.size()==1);
    assert(invalid.async_buffers_death_ring.empty());
    assert(invalid.slot_buffer_downloads.contains(42));
    invalid.async_buffers.front()[0].buffer=111;
    invalid.Pop();
    assert(invalid.async_buffers_death_ring.size()==2);
#endif
}
""".replace("__BLOCK__",block)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-pop-async-") as folder:
    src=Path(folder)/"pop.cpp"
    src.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            exe=Path(folder)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),str(src),"-o",str(exe)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            assert built.returncode==0,(native,opt,built.stderr[-4000:])
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-4000:])
print("F07_POP_ASYNC_TRANSACTION_PASS native=1 desktop=1 swizzle_retry=1 dma_retry=1 invalid_staging=1 O0=1 O2=1")
