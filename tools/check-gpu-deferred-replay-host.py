#!/usr/bin/env python3
"""Host-only sanitizer fixture for original GPU-dirty collection boundaries."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root/"vendor/sources/eden/src/core/gpu_dirty_memory_manager.h").read_text()
assert "constexpr static size_t page_bits = DEVICE_PAGEBITS - 1;" in src
assert "constexpr static size_t align_bits = 6U;" in src
assert "TransformAddress BuildTransform" in src
assert "current.compare_exchange_weak" in src

code = r'''
#include "gpu_deferred_replay.h"
#include <cassert>
#include <cstdint>
#include <vector>
using namespace Eden::GpuDeferredWrite;
struct Span {unsigned core; std::uint64_t address, size;};
int main() {
    Queue queue;
    std::vector<Span> replayed, dirty;
    assert(queue.Enqueue(1,2040,32));
    assert(queue.Enqueue(2,4096,70));
    assert(queue.Enqueue(3,8190,32));
    assert(queue.Enqueue(0,10,9));
    auto totals=ReplayQueued(queue,
        [&](std::uint64_t address,std::uint64_t size){
            replayed.push_back({0,address,size});
            return address==2040 || address==8190;
        },
        [&](unsigned core,std::uint64_t address,std::uint64_t size){
            assert(size>0 && size<=kDirtyRegionBytes);
            assert(address/kDirtyRegionBytes==(address+size-1)/kDirtyRegionBytes);
            dirty.push_back({core,address,size});
        });
    assert(!queue.Pending());
    assert(totals.queued_ranges==4 && totals.deferred_gpu_owned==2);
    assert(totals.dirty_segments==4 && dirty.size()==4);
    assert(dirty[0].core==1 && dirty[0].address==2040 && dirty[0].size==8);
    assert(dirty[1].core==1 && dirty[1].address==2048 && dirty[1].size==24);
    assert(dirty[2].core==3 && dirty[2].address==8190 && dirty[2].size==2);
    assert(dirty[3].core==3 && dirty[3].address==8192 && dirty[3].size==30);
    assert(ReplayQueued(queue,
        [](std::uint64_t,std::uint64_t){return true;},
        [](unsigned,std::uint64_t,std::uint64_t){assert(false);}).queued_ranges==0);
    Queue extensive;
    assert(extensive.Enqueue(2,1025,4096));
    std::vector<Span> parts;
    auto all=ReplayQueued(extensive,
        [](std::uint64_t,std::uint64_t){return true;},
        [&](unsigned core,std::uint64_t address,std::uint64_t size){
            parts.push_back({core,address,size});
        });
    assert(all.queued_ranges==1 && all.dirty_segments==3);
    assert(parts.size()==3);
    assert(parts[0].core==2 && parts[0].address==1025 && parts[0].size==1023);
    assert(parts[1].core==2 && parts[1].address==2048 && parts[1].size==2048);
    assert(parts[2].core==2 && parts[2].address==4096 && parts[2].size==1025);
    Queue reentrant;
    assert(reentrant.Enqueue(0,64,8));
    unsigned invoked=0;
    const auto rereplay=ReplayQueued(reentrant,
        [&](std::uint64_t,std::uint64_t){
            ++invoked;
            if(invoked==1)assert(reentrant.Enqueue(1,4096,8));
            return false;
        },[](unsigned,std::uint64_t,std::uint64_t){assert(false);});
    assert(invoked==2 && rereplay.queued_ranges==2 && !reentrant.Pending());
}
'''
with tempfile.TemporaryDirectory(prefix="encore-replay-host-") as folder:
    cpp=Path(folder)/"replay.cpp"
    exe=Path(folder)/"replay"
    cpp.write_text(code)
    subprocess.run(["clang++","-std=c++20","-O1","-g","-pthread",
                    "-Wall","-Wextra","-Werror","-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all","-I",str(root/"headless"),
                    str(cpp),"-o",str(exe)],check=True,timeout=45)
    subprocess.run([str(exe)],check=True,timeout=45)
print("GPU_DEFERRED_REPLAY_HOST_PASS dirty_regions=2048 granularity=64 crossregion=1 core_preserved=1 reentrant=1")
