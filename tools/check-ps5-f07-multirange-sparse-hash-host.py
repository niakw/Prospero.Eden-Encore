#!/usr/bin/env python3
"""Source-extracted F07 native sparse multi-range cache-hit hash fast path.

Sparse references live memory and cannot need a CPU content hash, while
gathered fallback still checks write ticks. Test original desktop parity.
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
assert "python3 -B tools/check-ps5-f07-multirange-sparse-hash-host.py" in fast and "python3 -B tools/check-ps5-f07-multirange-sparse-hash-host.py" in pre
assert "F07 omit native sparse multi-range content hash on stable geometry hits" in gen
start="#ifdef PS5_NATIVE\n    const auto it = entries.find(key);"
stop="    if (it != entries.end() && it->second.geometry == geometry && it->second.size == total) {"
begin=source.index("MultiRangeRef MultiRangeBufferCache::Get(")
body=source[begin:source.index("\nvoid MultiRangeBufferCache::MarkGathered(",begin)]
assert body.count(start)==body.count(stop)==1
block=body[body.index(start):body.index(stop)]
assert block.index("it->second.sparse_handle") < block.index("const u64 content = HashContent(sources);")
assert block.count("const u64 content = HashContent(sources);")==1
assert "const u64 content = same_geometry ? HashContent(sources) : 0;" in block
assert "entry.content = HashContent(sources);" in body
assert "mix_geometry(u64(source.size));" in body
assert "const u64 geometry = HashSources(sources);" in body
assert body.index("if (!entry.sparse_handle) {") < body.index("entry.content = HashContent(sources);")
assert "F07 hash native multi-range content only for gathered fallback lookup" in gen and "F07 hash native multi-range content only for gathered fallback gather" in gen
cpp=r"""
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <unordered_map>
#include <vector>
using u64=std::uint64_t;
using VkBuffer=u64;
struct Buffer {
    VkBuffer handle{};
    explicit operator bool() const {return handle!=0;}
    VkBuffer operator*() const {return handle;}
};
struct MultiRangeSource {u64 write_tick{};};
struct MultiRangeRef {
    VkBuffer handle{};
    u64 address{}, size{};
    bool sparse{}, needs_gather{};
};
struct Entry {
    u64 geometry{},size{},address{};
    Buffer sparse_handle{};
};
struct MultiRangeBufferCache {
    std::unordered_map<u64,Entry> entries{};
    unsigned geometry_calls{},content_calls{};
    u64 HashSources(const std::vector<MultiRangeSource>&) {++geometry_calls;return 17;}
    u64 HashContent(const std::vector<MultiRangeSource>& s) {
        ++content_calls;return s.front().write_tick;
    }
    MultiRangeRef Probe(u64 key,const std::vector<MultiRangeSource>& sources,u64 total) {
__SOURCE__
        (void)content;
        if (it != entries.end() && it->second.geometry == geometry &&
            it->second.size == total) {
            if (it->second.sparse_handle) {
                return MultiRangeRef{*it->second.sparse_handle,it->second.address,
                                     it->second.size,true,false};
            }
            return MultiRangeRef{5,11,total,false,true};
        }
        return MultiRangeRef{5,11,total,false,true};
    }
};
int main() {
    std::vector<MultiRangeSource> s{{3}};
    MultiRangeBufferCache sparse;
    sparse.entries.emplace(42, Entry{17,8,11,Buffer{55}});
    auto a=sparse.Probe(42,s,8);
    assert(a.handle==55 && a.sparse && !a.needs_gather);
#ifdef PS5_NATIVE
    assert(sparse.content_calls==0);
#else
    assert(sparse.content_calls==1);
#endif
    s[0].write_tick=9;
    a=sparse.Probe(42,s,8);
    assert(a.handle==55 && a.sparse);
#ifdef PS5_NATIVE
    assert(sparse.content_calls==0);
#else
    assert(sparse.content_calls==2);
#endif
    MultiRangeBufferCache gathered;
    gathered.entries.emplace(42, Entry{17,8,11,Buffer{0}});
    auto b=gathered.Probe(42,s,8);
    assert(b.handle==5 && b.needs_gather);
    assert(gathered.content_calls==1);
    MultiRangeBufferCache changed;
    changed.entries.emplace(42, Entry{13,8,11,Buffer{88}});
    auto c=changed.Probe(42,s,8);
    assert(c.handle==5);
#ifdef PS5_NATIVE
    assert(changed.content_calls==0); // no hash until sparse creation/fallback
#else
    assert(changed.content_calls==1);
#endif
}
""".replace("__SOURCE__","    const u64 geometry = HashSources(sources);\n"+block)
# source code keeps 'content' in scope after the guarded native early return.
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-sparse-content-") as d:
    s=Path(d)/"source.cpp"
    s.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(d)/("test"+opt+str(int(native)))
            proc=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                                 *(["-DPS5_NATIVE=1"] if native else []),
                                 str(s),"-o",str(exe)],
                                 capture_output=True,text=True,timeout=50)
            assert proc.returncode==0,(native,opt,proc.stderr[-4000:])
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert result.returncode==0,(native,opt,result.stderr[-4000:])
print("F07_SPARSE_HASH_SKIPPED_PASS native=1 desktop_unchanged=1 O0_O2=1")
print("NO_PS5_FPS_PROOF")
