#!/usr/bin/env python3
"""Compile maintained Vulkan multi-range retirement and ownership under ASan/UBSan.

Qualifies only native C++ host semantics: both sparse and gathered source
owners trigger retired-tick protection, with no early release while pending.
Not a measurement of real GPU queue completion or console frametimes.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/"vendor/encore-active/eden-vulkan/vk_multi_range_buffer_cost.cpp").read_text()
PIN=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_multi_range_buffer.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
FLOW=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-vulkan-multirange-owner-lifetime-host.py" in FLOW
anchor="    entry.owners.reserve(sources.size());"
sparse="    if (CanBindSparse(sources)) {"
assert SRC.count(anchor)==PIN.count(anchor)==1
assert SRC.index(anchor) < SRC.index(sparse,SRC.index("MultiRangeRef MultiRangeBufferCache::Get("))
assert PIN.index(anchor) > PIN.index(sparse,PIN.index("MultiRangeRef MultiRangeBufferCache::Get("))
assert "DropOwner cannot retire a gathered buffer" in SRC
assert "DropOwner cannot retire a gathered buffer" in GEN
first=SRC.index(anchor)
end=SRC.index(sparse,first)
owners=SRC[first:end]
for n in ("entry.owners.reserve(sources.size());","entry.owners.push_back(source.handle);"):
    assert n in owners

def extract(start,end):
    assert SRC.count(start)==1 and SRC.count(end)==1, (start,end)
    return SRC[SRC.index(start):SRC.index(end,SRC.index(start))]
retire=extract("void MultiRangeBufferCache::RetireEntry(","void MultiRangeBufferCache::DrainRetired(")
# In production this RAII timer is meaningful through its real destructor.
# The host double has no destructor side effect; suppress only its warning.
retire=retire.replace("auto timer = Eden::Performance::VulkanTimer(11);",
                      "[[maybe_unused]] auto timer = Eden::Performance::VulkanTimer(11);")
drain=extract("void MultiRangeBufferCache::DrainRetired(","MultiRangeRef MultiRangeBufferCache::Get(")
drop=extract("void MultiRangeBufferCache::DropOwner(","void MultiRangeBufferCache::Invalidate(")
invalidate=SRC[SRC.index("void MultiRangeBufferCache::Invalidate("):SRC.rindex("} // namespace Vulkan")]

cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <span>
#include <unordered_map>
#include <utility>
#include <vector>
#include <boost/container/static_vector.hpp>
using u64=std::uint64_t;using VkBuffer=u64;
constexpr VkBuffer VK_NULL_HANDLE=0;
namespace Eden {
namespace Performance {struct VulkanTimer { explicit VulkanTimer(int){} };}
namespace DevVulkan {inline bool trace_pipelines=false;}
void Report(const char*,const char*){}
}
namespace Vulkan {
struct MultiRangeSource {VkBuffer handle{};};
struct Handle {
    std::shared_ptr<int> value{};
    Handle()=default;
    explicit Handle(int x):value(std::make_shared<int>(x)){}
    explicit operator bool() const {return bool(value);}
};
struct Scheduler {
    u64 now=1,completed=0;
    unsigned waits=0;
    u64 CurrentTick() const{return now;}
    bool IsFree(u64 tick) const{return tick<=completed;}
    void Wait(u64 tick) {assert(tick<=now);completed=std::max(completed,tick);++waits;}
};
class MultiRangeBufferCache {
public:
    static constexpr size_t MAX_RETIRED=256;
    struct Entry {
        Handle sparse_handle,gathered;
        std::vector<VkBuffer> owners;
        bool dirty=true;
    };
    struct Retired {Handle handle,gathered;u64 tick{};};
    std::unordered_map<u64,Entry> entries;
    boost::container::static_vector<Retired,MAX_RETIRED> retired;
    void Track(Entry& entry,std::span<const MultiRangeSource> sources) {
INJECT_OWNERS
    }
    void RetireEntry(Scheduler&,Entry&);
    void DrainRetired(Scheduler&);
    void DropOwner(Scheduler&,VkBuffer);
    void Invalidate(u64);
};
INJECT_RETIRE
INJECT_DRAIN
INJECT_DROP
INJECT_INVALIDATE
}
int main() {
    using namespace Vulkan;
    MultiRangeBufferCache cache;
    Scheduler sched;
    const MultiRangeSource source1{17},source2{23};
    auto add=[&](u64 key,VkBuffer handle,bool sparse,int id){
        MultiRangeBufferCache::Entry entry{};
        if(sparse)entry.sparse_handle=Handle(id);
        else entry.gathered=Handle(id);
        const MultiRangeSource sources[]={MultiRangeSource{handle}};
        cache.Track(entry,sources);
        assert(entry.owners.size()==1 && entry.owners[0]==handle);
        auto weak=std::weak_ptr<int>(sparse?entry.sparse_handle.value:entry.gathered.value);
        cache.entries.emplace(key,std::move(entry));
        return weak;
    };
    auto gathered=add(1,source1.handle,false,111);
    auto sparse=add(2,source1.handle,true,222);
    auto independent=add(3,source2.handle,false,333);
    cache.entries[3].dirty=false;
    cache.Invalidate(3);
    assert(cache.entries[3].dirty);
    cache.DropOwner(sched,0); // null owner is a no-op
    assert(cache.entries.size()==3);
    cache.DropOwner(sched,source1.handle);
    assert(cache.entries.size()==1 && cache.retired.size()==2);
    assert(!gathered.expired() && !sparse.expired() && !independent.expired());
    cache.DrainRetired(sched);
    assert(cache.retired.size()==2); // no premature GPU-free
    sched.completed=sched.now;
    cache.DrainRetired(sched);
    assert(cache.retired.empty() && gathered.expired() && sparse.expired());
    assert(!independent.expired());
    cache.DropOwner(sched,source2.handle);
    assert(cache.entries.empty() && cache.retired.size()==1);
    sched.completed=sched.now;
    cache.DrainRetired(sched);
    assert(independent.expired());
    // Saturate the fixed retirement queue and prove oldest-tick backpressure
    // reclaims safely without exceeding static_vector capacity.
    sched.completed=0;
    for(u64 i=0;i<300;++i){
        sched.now=i+20;
        auto w=add(i+100,900+i,(i%2)==0,1000+int(i));
        cache.DropOwner(sched,900+i);
        assert(cache.entries.empty());
        assert(cache.retired.size()<=MultiRangeBufferCache::MAX_RETIRED);
        if(i>=256)assert(sched.waits>0);
        if(i>=256)assert(!w.expired());
    }
    sched.completed=sched.now;
    cache.DrainRetired(sched);
    assert(cache.retired.empty() && sched.waits>0);
    std::puts("ENCORE_MULTIRANGE_OWNER_RETIREMENT_PASS");
}
""".replace("INJECT_OWNERS",owners).replace("INJECT_RETIRE",retire).replace(
    "INJECT_DRAIN",drain).replace("INJECT_DROP",drop).replace(
    "INJECT_INVALIDATE",invalidate)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-vulkan-owner-lifetime-") as name:
    folder=Path(name);source=folder/"test.cpp";exe=folder/"test"
    source.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(source),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("HOST_MULTIRANGE_OWNER_RETIREMENT_PASS native_fence_progress=unverified")
