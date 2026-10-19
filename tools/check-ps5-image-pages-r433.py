#!/usr/bin/env python3
"""R433: host-sanitized proof of monotonic texture-page lock-elision boundaries."""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
header = (root / "headless/image_pages.h").read_text()
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
cache = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
ast.parse(generator)
assert raster.count("::Eden::ImagePages::NeverHeld(addr, size)") == 5
write_start = raster.index("bool RasterizerVulkan::OnCPUWrite")
write_end = raster.index("void RasterizerVulkan::OnCacheInvalidation", write_start)
write_method = raster[write_start:write_end]
assert write_method.count("::Eden::ImagePages::NeverHeld(addr, size)") == 1
assert write_method.index("::Eden::BufferPages::NeverRegistered") < write_method.index(
    "::Eden::ImagePages::NeverHeld")
assert write_method.index("::Eden::ImagePages::NeverHeld") < write_method.index(
    "::Eden::Performance::GuestCacheLock(texture_cache.mutex, true)")
assert write_method.index("texture_cache.WriteMemory(addr, size)") < write_method.index(
    "pipeline_cache.InvalidateRegion(addr, size)")
assert write_method.count("pipeline_cache.InvalidateRegion(addr, size)") == 1
assert raster.index("::Eden::ImagePages::NeverHeld(addr, size)") < raster.index(
    "::Eden::Performance::GuestCacheLock(texture_cache.mutex, true)",
    raster.index("RasterizerVulkan::GetFlushArea"))
assert cache.count("::Eden::ImagePages::Mark(image.cpu_addr, image.guest_size_bytes);") == 1
assert cache.count("::Eden::ImagePages::Mark(cpu_addr, size);") == 1
assert cache.index("::Eden::ImagePages::Mark(image.cpu_addr") < cache.index(
    "slot_map_views.insert(image.gpu_addr")
assert cache.index("::Eden::ImagePages::Mark(cpu_addr, size);") < cache.index(
    "slot_map_views.insert(gpu_addr, cpu_addr")
assert "ImagePages::NeverHeld" in generator and generator.count("ImagePages::Mark(") == 2
assert "memory_order_acquire" in header and "memory_order_release" in header
assert "size > 256 * 1024" in header
cxx = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert cxx
fixture = r"""
#include "image_pages.h"
#include <cassert>
#include <atomic>
#include <cstdint>
#include <thread>
#include <vector>
using namespace Eden::ImagePages;
int main() {
  constexpr std::uint64_t p=4096;
  assert(NeverHeld(0,1) && NeverHeld(kSpace-1,1) && NeverHeld(123456789,64*p));
  assert(!NeverHeld(kSpace,1) && !NeverHeld(kSpace-1,2));
  assert(!NeverHeld(0,256*1024+1));
  Mark(p,1);
  assert(NeverHeld(p-1,1) && !NeverHeld(p,1) && !NeverHeld(2*p-1,1));
  assert(NeverHeld(2*p,1) && !NeverHeld(p-1,2));
  Mark(63*p+5,2*p);
  assert(!NeverHeld(63*p,1) && !NeverHeld(64*p,1) && !NeverHeld(65*p,1));
  assert(NeverHeld(66*p,p));
  Mark(1000*p,9000*p);
  assert(!NeverHeld(1000*p,1) && !NeverHeld(5000*p,1));
  assert(NeverHeld(10000*p,p));
  Mark(kSpace-1,1<<20);
  assert(!NeverHeld(kSpace-1,1) && !NeverHeld(kSpace-1,2));
  std::vector<std::thread> threads;
  std::atomic<unsigned> misses{0};
  for(unsigned i=0;i<8;++i) threads.emplace_back([i,&misses] {
    auto base=(1000000u+i*1000u)*4096ull;
    for(unsigned n=0;n<800;++n) {
      Mark(base+n*4096,p);
      if(NeverHeld(base+n*4096,1)) ++misses;
    }
  });
  for(auto& thread:threads) thread.join();
  assert(misses.load()==0);
  for(unsigned i=0;i<8;++i) {
    auto base=(1000000u+i*1000u)*4096ull;
    assert(!NeverHeld(base+799*p,1) && NeverHeld(base+800*p,1));
  }
}
"""
with tempfile.TemporaryDirectory(prefix="eden-r433-image-pages-") as tmp:
    source = Path(tmp) / "test.cpp"
    exe = Path(tmp) / "test"
    source.write_text(fixture)
    subprocess.run([cxx, "-std=c++20", "-O1", "-pthread",
                    "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-Wall", "-Wextra", "-Werror", "-I" + str(root / "headless"),
                    str(source), "-o", str(exe)], check=True, timeout=90)
    subprocess.run([str(exe)], check=True, timeout=90)
print("PASS R433: registered pages never fast-skipped; bounded scanning, concurrent marking, source replay guards")
