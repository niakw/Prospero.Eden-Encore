#!/usr/bin/env python3
"""Prove a large valid buffer cannot poison all later never-owned writes."""
from pathlib import Path
import subprocess
import shutil
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"headless/buffer_pages.h").read_text()
assert "size>128ull*1024*1024" not in source
assert "if(address>=kSpace || size>kSpace-address)" in source
assert "registered[word].fetch_or(mask,std::memory_order_release)" in source
assert "coverage_unknown.store(true,std::memory_order_release)" in source
assert "coverage_unknown.load(std::memory_order_acquire)" in source
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler

program=r"""
#include "buffer_pages.h"
#include <cassert>
#include <thread>
#include <vector>
int main() {
  using namespace Eden::BufferPages;
  constexpr std::uint64_t mib=1024ull*1024ull;
  constexpr std::uint64_t kBig = 128*mib + 4096;
  constexpr std::uint64_t base=2*mib;
  assert(!coverage_unknown.load(std::memory_order_acquire));
  assert(NeverRegistered(base,4096));
  Mark(base,kBig);
  // A large VALID buffer is no longer a global disabling event.
  assert(!coverage_unknown.load(std::memory_order_acquire));
  assert(!NeverRegistered(base,4096));
  assert(!NeverRegistered(base+kBig-4096,4096));
  // Registration must not mark unrelated pages and unregistered writes
  // must still skip cache locking for the rest of the game.
  assert(NeverRegistered(base+kBig+2*4096,4096));
  assert(NeverRegistered(1ull*mib,4096));
  // Concurrent registration into one word must preserve both bitmaps.
  constexpr std::uint64_t other=512*mib;
  std::vector<std::thread> producers;
  for(unsigned t=0;t<4;++t)producers.emplace_back([t]{
    for(unsigned n=0;n<128;++n)
      Mark(other+(t*128+n)*4096,4096);
  });
  for(auto& x:producers)x.join();
  for(unsigned t=0;t<4;++t)
    assert(!NeverRegistered(other+t*128*4096,4096));
  assert(NeverRegistered(other+4*128*4096,4096));
  // Invalid or unrepresentable addresses retain conservative fallback.
  Mark(kSpace+1,4096);
  assert(coverage_unknown.load(std::memory_order_acquire));
  assert(!NeverRegistered(1ull*mib,4096));
}
"""
with tempfile.TemporaryDirectory(prefix="encore-buffer-large-page-") as d:
    cpp=Path(d)/"witness.cpp"
    cpp.write_text(program)
    for opt in ("-O0","-O2"):
        exe=Path(d)/("witness"+opt)
        subprocess.run([compiler,"-std=c++20",opt,"-pthread","-Wall","-Wextra",
                        "-Werror","-fsanitize=undefined","-I"+str(root/"headless"),
                        str(cpp),"-o",str(exe)],check=True,timeout=40)
        subprocess.run([str(exe)],check=True,timeout=30)
        print("NATIVE_LARGE_BUFFER_PAGES_PASS",opt)
