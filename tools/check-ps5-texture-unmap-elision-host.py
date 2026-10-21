#!/usr/bin/env python3
"""ASan/UBSan native-method witness: CPU texture-page unmap lock elision.

Never infer GPU-addressed image mapping from CPU-addressed occupancy.
Known GPU buffer writes and pipeline notifications must still execute.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = (root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
bridge = (root/"vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
pinned = (root/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
oracle = (root/"tools/prepare-vulkan-port.py").read_text()
workflow = (root/".github/workflows/encore-core-preflight.yml").read_text()
cache = (root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
begin = "void RasterizerVulkan::UnmapMemory(DAddr addr, u64 size) {"
end = "\nvoid RasterizerVulkan::SignalFence("
def method_pair(s):
    assert s.count(begin) == s.count(end) == 1
    return s[s.index(begin):s.index(end,s.index(begin))]
body = method_pair(main)
assert body == method_pair(bridge)
assert body != method_pair(pinned)
assert body.count("::Eden::ImagePages::NeverHeld(addr, size)") == 1
assert body.count("::Eden::BufferPages::NeverRegistered(addr, size)") == 1
assert body.index("::Eden::ImagePages::NeverHeld(addr, size)") < body.index(
    "texture_cache.UnmapMemory(addr, size)")
assert body.index("texture_cache.UnmapMemory(addr, size)") < body.index(
    "buffer_cache.WriteMemory(addr, size)")
assert body.index("buffer_cache.WriteMemory(addr, size)") < body.index(
    "pipeline_cache.OnCacheInvalidation(addr, size)")
gpu_part = body.split("void RasterizerVulkan::ModifyGPUMemory(",1)[1]
assert "ImagePages::NeverHeld" not in gpu_part
assert "texture_cache.UnmapGPUMemory(as_id, addr, size)" in gpu_part
assert "buffer_cache.UnmapGPUMemory(as_id, addr, size)" in gpu_part
assert cache.index("::Eden::ImagePages::Mark(image.cpu_addr") < cache.index(
    "slot_map_views.insert(image.gpu_addr")
assert cache.index("::Eden::ImagePages::Mark(cpu_addr, size)") < cache.index(
    "slot_map_views.insert(gpu_addr, cpu_addr")
assert "CPU-addressed unmapping: do not lock an image cache" in oracle
assert "python3 -B tools/check-ps5-texture-unmap-elision-host.py" in workflow

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include "image_pages.h"
#include "buffer_pages.h"
using DAddr = std::uint64_t;
using GPUVAddr = std::uint64_t;
using u64 = std::uint64_t;
struct CountingMutex {
  std::recursive_mutex underlying;
  unsigned locks{};
  void lock() {underlying.lock(); ++locks;}
  void unlock() {underlying.unlock();}
};
struct TextureCache {
  CountingMutex mutex;
  unsigned cpu_unmaps{}, gpu_unmaps{};
  void UnmapMemory(DAddr, u64) {++cpu_unmaps;}
  void UnmapGPUMemory(std::size_t, GPUVAddr, u64) {++gpu_unmaps;}
};
struct BufferCache {
  CountingMutex mutex;
  unsigned write_calls{}, gpu_unmaps{};
  void WriteMemory(DAddr, u64) {++write_calls;}
  void UnmapGPUMemory(std::size_t, GPUVAddr, u64) {++gpu_unmaps;}
};
struct PipelineCache {
  unsigned invalidations{};
  void OnCacheInvalidation(DAddr, u64) {++invalidations;}
};
class RasterizerVulkan {
public:
  TextureCache texture_cache;
  BufferCache buffer_cache;
  PipelineCache pipeline_cache;
  void UnmapMemory(DAddr addr, u64 size);
  void ModifyGPUMemory(std::size_t as_id, GPUVAddr addr, u64 size);
};
__METHODS__
int main() {
  constexpr DAddr page=4096;
  RasterizerVulkan x;
  x.UnmapMemory(100*page,page);
  assert(x.texture_cache.cpu_unmaps==0 && x.texture_cache.mutex.locks==0);
  assert(x.buffer_cache.write_calls==0 && x.buffer_cache.mutex.locks==0);
  assert(x.pipeline_cache.invalidations==1);
  // An image ever registered at this CPU page must still be removed.
  Eden::ImagePages::Mark(200*page,page);
  Eden::BufferPages::Mark(200*page,page);
  x.UnmapMemory(200*page,page);
  x.UnmapMemory(199*page,2*page);
  assert(x.texture_cache.cpu_unmaps==2 && x.texture_cache.mutex.locks==2);
  assert(x.buffer_cache.write_calls==2 && x.buffer_cache.mutex.locks==2);
  assert(x.pipeline_cache.invalidations==3);
  // Unknown, oversized and out-of-range ranges use the legacy mutex.
  x.UnmapMemory(300*page,256*1024+1);
  x.UnmapMemory(Eden::ImagePages::kSpace-2,4);
  assert(x.texture_cache.cpu_unmaps==4 && x.texture_cache.mutex.locks==4);
  assert(x.buffer_cache.write_calls==4 && x.buffer_cache.mutex.locks==4);
  assert(x.pipeline_cache.invalidations==5);
  // GPU unmapping must NEVER consult CPU page witness.
  x.ModifyGPUMemory(7,700*page,page);
  assert(x.texture_cache.gpu_unmaps==1 && x.texture_cache.mutex.locks==5);
  assert(x.buffer_cache.gpu_unmaps==1);
  assert(x.buffer_cache.write_calls==4 && x.buffer_cache.mutex.locks==4);
  assert(x.pipeline_cache.invalidations==5);
}
""".replace("__METHODS__",body)
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler,"clang++ sanitizer host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-unmap-cache-") as tmp:
    f=Path(tmp)/"unmap.cpp"
    exe=Path(tmp)/"test"
    f.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-pthread","-Wall","-Wextra",
                    "-Werror","-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all","-I"+str(root/"headless"),
                    str(f),"-o",str(exe)],check=True,timeout=55)
    subprocess.run([str(exe)],check=True,timeout=20)
print("VULKAN_TEXTURE_UNMAP_ELISION_HOST_PASS actual_methods=2 unowned=1 registered=1 "
      "overlap=1 unknown=1 large=1 gpu_address_separate=1 buffer_shader_kept=1 asan_ubsan=1")
