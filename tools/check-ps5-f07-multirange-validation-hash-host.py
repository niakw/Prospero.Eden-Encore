#!/usr/bin/env python3
"""F07 native Vulkan multi-range: validate and fingerprint in the same pass.

Compile the production preflight and original FNV hash under both feature
modes. Check identical fingerprints, rejected invalid inputs, and overflow.
"""
from pathlib import Path
import shutil,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vk_multi_range_buffer_cost.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
fast=(root/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(root/".github/workflows/encore-core-preflight.yml").read_text()
assert "F07 merge native multi-range geometry fingerprint into validation walk validation" in gen and "F07 merge native multi-range geometry fingerprint into validation walk hash reuse" in gen
assert "python3 -B tools/check-ps5-f07-multirange-validation-hash-host.py" in fast and "python3 -B tools/check-ps5-f07-multirange-validation-hash-host.py" in pre
get_start="MultiRangeRef MultiRangeBufferCache::Get("
get_end="\nvoid MultiRangeBufferCache::MarkGathered("
body=src[src.index(get_start):src.index(get_end,src.index(get_start))]
guard_start="#ifdef PS5_NATIVE\n    // A multi-range hit formerly scanned"
guard_end="    if (!retired.empty()) {"
assert body.count(guard_start)==body.count(guard_end)==1
preflight=body[body.index(guard_start):body.index(guard_end)]
assert preflight.count("mix_geometry(")==6
assert preflight.index("return MultiRangeRef{};")<preflight.index("mix_geometry(u64(source.handle))")
assert body.index("    const u64 geometry = HashSources(sources);")>body.index("if (!retired.empty())")
assert body.index("    const auto it = entries.find(key);")>body.index("    const u64 geometry = HashSources(sources);")
hash_start="u64 MultiRangeBufferCache::HashSources("
hash_end="\nu64 MultiRangeBufferCache::HashContent("
hash_fn=src[src.index(hash_start):src.index(hash_end,src.index(hash_start))]
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <vector>
using u64=std::uint64_t;
using u32=std::uint32_t;
using VkDeviceSize=u64;
using VkBuffer=u64;
using VkDeviceMemory=u64;
constexpr VkBuffer VK_NULL_HANDLE=0;
struct MultiRangeSource{
 VkBuffer handle{};
 VkDeviceMemory memory{};
 VkDeviceSize memory_offset{},offset{},size{};
 u64 write_tick{};
 u32 memory_type{};
};
struct MultiRangeRef {
 VkBuffer handle{};
 u64 geometry{};
};
struct MultiRangeBufferCache {
 u64 HashSources(std::span<const MultiRangeSource>) const;
 MultiRangeRef Preflight(std::span<const MultiRangeSource> sources,VkDeviceSize total) const {
     if(sources.empty()||total==0)return MultiRangeRef{};
__PREFLIGHT__
#ifndef PS5_NATIVE
     const u64 geometry = HashSources(sources);
#endif
     return MultiRangeRef{1,geometry};
 }
};
__HASH__
int main() {
 MultiRangeBufferCache cache;
 for(size_t n=1;n<=64;n++) {
   std::vector<MultiRangeSource> sources;
   u64 total=0;
   for(size_t i=0;i<n;i++) {
      MultiRangeSource source{};
      source.handle=i+1;
      source.memory=0xFF0000+i;
      source.memory_offset=i*8192;
      source.offset=i*128;
      source.size=i+1;
      source.memory_type=static_cast<u32>(i%13);
      sources.push_back(source);
      total+=source.size;
   }
   auto x=cache.Preflight(sources,total);
   assert(x.handle==1 && x.geometry==cache.HashSources(sources));
   auto y=cache.Preflight(sources,total+1024);
   assert(y.handle==1 && y.geometry==x.geometry);
   sources[0].handle=0;
   assert(cache.Preflight(sources,total).handle==0);
   sources[0].handle=1;
   sources[0].size=0;
   assert(cache.Preflight(sources,total).handle==0);
 }
 {
   std::vector<MultiRangeSource> s{{5,1,0,0,10,0,0}};
   assert(cache.Preflight(s,9).handle==0);
   s[0].offset=std::numeric_limits<u64>::max()-5;
   assert(cache.Preflight(s,10).handle==0);
   s[0].offset=0;
   assert(cache.Preflight(s,10).geometry==cache.HashSources(s));
 }
 assert(cache.Preflight({},0).handle==0);
}
""".replace("__PREFLIGHT__",preflight).replace("__HASH__",hash_fn)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-multirange-hash-") as tmp:
  file=Path(tmp)/"test.cpp";file.write_text(cpp)
  for native in (False,True):
    for opt in ("-O0","-O2"):
      exe=Path(tmp)/("hash"+opt+str(int(native)))
      cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
           "-fsanitize=undefined","-fno-sanitize-recover=all",
           *(["-DPS5_NATIVE=1"] if native else []),str(file),"-o",str(exe)]
      build=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
      assert build.returncode==0,(native,opt,build.stderr[-6000:])
      run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
      assert run.returncode==0,(native,opt,run.stderr[-6000:])
print("F07_MULTIRANGE_FUSED_GEOMETRY_HASH_PASS native=1 desktop=1 invalid=1 overflow=1 O0_O2=1")
print("HOST_ONLY_NO_PS5_FPS_PROOF")
