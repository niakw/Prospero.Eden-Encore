#!/usr/bin/env python3
"""R437: buffer registration must not skip HUD texture or shader invalidation."""
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
cm=(root/'headless/CMakeLists.txt').read_text()
r=(root/'vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp').read_text()
g=(root/'tools/prepare-vulkan-port.py').read_text()
source=(root/'vendor/sources/eden/src/video_core/buffer_cache/buffer_cache.h').read_text()
assert 'Pinned BufferCache ChangeRegister changed' in cm
assert '::Eden::BufferPages::Mark(buffer.CpuAddr(), size);' in cm
assert 'buffer-pages/video_core/buffer_cache/buffer_cache.h' in cm
assert source.count('        total_used_memory += Common::AlignUp(size, 1024);')==1
assert r.count('::Eden::BufferPages::NeverRegistered(addr, size)')==1
assert g.count('::Eden::BufferPages::NeverRegistered(addr, size)')==1
pos=r.index('bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size)')
body=r[pos:r.index('void RasterizerVulkan::OnCacheInvalidation',pos)]
assert body.index('::Eden::BufferPages::NeverRegistered') < body.index(
    '::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false)')
assert body.index('::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false)') < body.index(
    'texture_cache.WriteMemory(addr, size);') < body.index(
    'pipeline_cache.InvalidateRegion(addr, size);')
assert body.count('texture_cache.WriteMemory(addr, size);')==1
assert body.count('pipeline_cache.InvalidateRegion(addr, size);')==1
cxx=shutil.which('c++') or shutil.which('clang++') or shutil.which('g++')
assert cxx
cpp=r"""
#include "buffer_pages.h"
#include <cassert>
#include <thread>
#include <vector>
int main(){
 using namespace Eden::BufferPages;
 constexpr std::uint64_t p=4096;
 assert(NeverRegistered(0,1));
 assert(!NeverRegistered(0,0) && !NeverRegistered(kSpace,1));
 assert(!NeverRegistered(0,64*p+1) && !NeverRegistered(kSpace-1,2));
 Mark(0,1);
 assert(!NeverRegistered(0,1) && NeverRegistered(p,1));
 Mark(63*p+7,2*p);
 assert(!NeverRegistered(63*p,1) && !NeverRegistered(64*p,1));
 assert(!NeverRegistered(65*p,1) && NeverRegistered(66*p,p));
 std::vector<std::thread> jobs;
 for(unsigned t=0;t<8;t++)jobs.emplace_back([t]{
    const auto b=(1000000ull+t*1000ull)*4096ull;
    for(unsigned n=0;n<512;n++)Mark(b+n*4096,1);
 });
 for(auto& j:jobs)j.join();
 for(unsigned t=0;t<8;t++){
   const auto b=(1000000ull+t*1000ull)*4096ull;
   assert(!NeverRegistered(b,1));
   assert(!NeverRegistered(b+511*p,1));
   assert(NeverRegistered(b+512*p,1));
 }
 Mark(kSpace+1,1);
 assert(!NeverRegistered(66*p,1));
}
"""
with tempfile.TemporaryDirectory(prefix='eden-r437-') as d:
 src=Path(d)/'b.cpp';exe=Path(d)/'b'
 src.write_text(cpp)
 subprocess.run([cxx,'-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror',
  '-fsanitize=undefined','-I'+str(root/'headless'),str(src),'-o',str(exe)],check=True,timeout=90)
 subprocess.run([str(exe)],check=True,timeout=90)
print('PASS R437 buffer-page witness and protected HUD invalidation')
