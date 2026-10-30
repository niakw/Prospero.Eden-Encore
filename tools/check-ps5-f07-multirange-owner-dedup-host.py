#!/usr/bin/env python3
"""F07: native adjacent owner de-dup in source-extracted multi-range insertion.

Preserve DropOwner membership and source-pixel order; bound memory and
linear owner probe cost when multiple adjacent pieces share one buffer.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vk_multi_range_buffer_cost.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
fast=(root/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(root/".github/workflows/encore-core-preflight.yml").read_text()
assert "F07 deduplicate adjacent native multi-range buffer owners" in gen
assert "python3 -B tools/check-ps5-f07-multirange-owner-dedup-host.py" in fast and "python3 -B tools/check-ps5-f07-multirange-owner-dedup-host.py" in pre
start="    entry.owners.reserve(sources.size());"
stop="    if (CanBindSparse(sources)) {"
begin=source.index("MultiRangeRef MultiRangeBufferCache::Get(")
body=source[begin:source.index("\nvoid MultiRangeBufferCache::MarkGathered(",begin)]
assert body.count(start)==body.count(stop)==1
owner_block=body[body.index(start):body.index(stop)]
assert owner_block.count("entry.owners.push_back(source.handle);")==1
assert owner_block.index("entry.owners.back() == source.handle") < owner_block.index("entry.owners.push_back(source.handle)")
drop=source[source.index("void MultiRangeBufferCache::DropOwner("):source.index("\nvoid MultiRangeBufferCache::Invalidate(",source.index("void MultiRangeBufferCache::DropOwner("))]
assert "for (const VkBuffer handle : entry.owners)" in drop
assert "if (handle == owner)" in drop
code=r"""
#include <cassert>
#include <cstdint>
#include <vector>
using VkBuffer=std::uint64_t;
struct MultiRangeSource{VkBuffer handle{};};
struct Entry{std::vector<VkBuffer> owners;};
struct Cache{
    Entry entry;
    void Populate(const std::vector<MultiRangeSource>& sources) {
        Entry& entry = this->entry;
__SOURCE__
    }
    bool DropOwner(VkBuffer handle) const {
        for (const auto h: entry.owners) {
            if(h==handle)return true;
        }
        return false;
    }
};
int main(){
    const std::vector<MultiRangeSource> slices{{5},{5},{5},{7},{7},{5},{9},{9},{9},{9}};
    Cache c;
    c.Populate(slices);
#ifdef PS5_NATIVE
    assert((c.entry.owners==std::vector<VkBuffer>{5,7,5,9}));
#else
    assert(c.entry.owners.size()==slices.size());
#endif
    assert(c.DropOwner(5) && c.DropOwner(7) && c.DropOwner(9));
    assert(!c.DropOwner(11));
    Cache empty;
    empty.Populate({});
    assert(empty.entry.owners.empty());
    Cache distinct;
    distinct.Populate({{1},{2},{3}});
    assert((distinct.entry.owners==std::vector<VkBuffer>{1,2,3}));
}
""".replace("__SOURCE__",owner_block)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-multirange-owners-") as tmp:
    src=Path(tmp)/"owners.cpp"
    src.write_text(code)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(tmp)/("owners"+opt+str(int(native)))
            result=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                "-fsanitize=undefined","-fno-sanitize-recover=all",
                *(["-DPS5_NATIVE=1"] if native else []),str(src),"-o",str(exe)],
                capture_output=True,text=True,timeout=60)
            assert result.returncode==0,(native,opt,result.stderr[-5000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-5000:])
print("F07_MULTIRANGE_OWNER_DEDUP_PASS adjacent=1 nonadjacent=1 dropowner=1 desktop=1 O0_O2=1")
print("NO_PS5_GPU_OR_FPS_PROOF")
