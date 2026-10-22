#!/usr/bin/env python3
"""Execute the selected native batched buffer-cache invalidation, no GPU driver."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
native_path = root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp"
native = native_path.read_text()
begin = native.index("void RasterizerVulkan::InnerInvalidation(")
end = native.index("\nbool RasterizerVulkan::OnCPUWrite(", begin)
method = native[begin:end]
assert "bool buffer_may_overlap = false;" in method
assert method.count("::Eden::BufferPages::NeverRegistered(addr, size)") == 2
assert "query_cache.InvalidateRegion(addr, size);" in method
assert "pipeline_cache.InvalidateRegion(addr, size);" in method
assert method.index("texture_cache.WriteMemory") < method.index("buffer_cache.WriteMemory") < method.index("query_cache.InvalidateRegion")
# The conservative witness MUST publish before page-table registration.
buffer_owner = (root / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
reg = buffer_owner[buffer_owner.index("void BufferCache<P>::ChangeRegister("):]
assert reg.index("::Eden::BufferPages::Mark(buffer.CpuAddr(), size);") < reg.index("page_table[page] = buffer_id;")
# Important: marking an unregistered CPU range is unnecessary for a future
# buffer's first upload because fresh WordManager pages start CPU-dirty.
word_owner = (root / "vendor/sources/eden/src/video_core/buffer_cache/word_manager.h").read_text()
assert "std::fill_n(heap.data() + size_t(Type::CPU) * num_words, num_words, ~u64{0});" in word_owner
generator = (root / "tools/prepare-vulkan-port.py").read_text()
assert "A never-registered buffer page has no GPU-owned content to invalidate." in generator
host = r'''
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <span>
#include <utility>
#include <vector>
#include "buffer_pages.h"
using DAddr = std::uint64_t;
namespace Eden::ImagePages {
inline bool any_held = false;
bool NeverHeld(DAddr, std::size_t) noexcept { return !any_held; }
}
struct CountMutex {
  std::mutex impl;
  unsigned locks = 0;
  void lock() { impl.lock(); ++locks; }
  void unlock() { impl.unlock(); }
};
struct Cache {
  CountMutex mutex;
  std::vector<std::pair<DAddr, std::size_t>> written;
  void WriteMemory(DAddr address, std::size_t size) { written.emplace_back(address, size); }
};
struct Owner {
  unsigned calls = 0;
  void InvalidateRegion(DAddr, std::size_t) { ++calls; }
};
struct RasterizerVulkan {
  Cache texture_cache, buffer_cache;
  Owner query_cache, pipeline_cache;
  void InnerInvalidation(std::span<const std::pair<DAddr, std::size_t>>);
};
''' + method + r'''
int main() {
  using Pair = std::pair<DAddr, std::size_t>;
  // Never owned buffer or texture, but query and shader MUST invalidate.
  RasterizerVulkan empty;
  std::array<Pair, 1> unwritten{Pair{0x100000, 4096}};
  empty.InnerInvalidation(unwritten);
  assert(empty.buffer_cache.mutex.locks == 0);
  assert(empty.texture_cache.mutex.locks == 0);
  assert(empty.query_cache.calls == 1 && empty.pipeline_cache.calls == 1);

  // One registered buffer page in a batch with another previously empty page.
  Eden::BufferPages::Mark(0x200000, 4096);
  RasterizerVulkan mixed;
  std::array<Pair, 2> two{Pair{0x200000, 4096}, Pair{0x210000, 4096}};
  mixed.InnerInvalidation(two);
  assert(mixed.buffer_cache.mutex.locks == 1);
  assert(mixed.buffer_cache.written.size() == 1);
  assert(mixed.buffer_cache.written[0].first == 0x200000);
  assert(mixed.query_cache.calls == 2 && mixed.pipeline_cache.calls == 2);

  // A previously owned page cannot be skipped, even if now unregistered.
  mixed.InnerInvalidation(unwritten);
  assert(mixed.buffer_cache.written.size() == 1);
  std::array<Pair, 1> old{Pair{0x200000, 4096}};
  mixed.InnerInvalidation(old);
  assert(mixed.buffer_cache.written.size() == 2);

  // 128 KiB entirely unregistered: the two-word bitmap fast path
  // must skip the buffer mutex while still invalidating query/shader.
  RasterizerVulkan large;
  std::array<Pair, 1> broad{Pair{0x310000, 131072}};
  large.InnerInvalidation(broad);
  assert(large.buffer_cache.mutex.locks == 0);
  assert(large.buffer_cache.written.empty());
  assert(large.query_cache.calls == 1 && large.pipeline_cache.calls == 1);

  // Unknown or >256 KiB spans retain conservative cache invalidation.
  std::array<Pair, 1> oversized{Pair{0x310000, 256 * 1024 + 1}};
  large.InnerInvalidation(oversized);
  assert(large.buffer_cache.mutex.locks == 1);
  assert(large.buffer_cache.written.size() == 1);
  assert(large.query_cache.calls == 2 && large.pipeline_cache.calls == 2);

  // Texture-cache invalidation still occurs independently from buffer state.
  Eden::ImagePages::any_held = true;
  RasterizerVulkan texture;
  texture.InnerInvalidation(unwritten);
  assert(texture.texture_cache.written.size() == 1);
  assert(texture.buffer_cache.written.empty());
  assert(texture.pipeline_cache.calls == 1);

  // Outside address coverage, the witness must permanently fail open.
  Eden::BufferPages::Mark(Eden::BufferPages::kSpace, 4096);
  RasterizerVulkan unknown;
  unknown.InnerInvalidation(unwritten);
  assert(unknown.buffer_cache.written.size() == 1);
  assert(unknown.query_cache.calls == 1);
}
'''
with tempfile.TemporaryDirectory(prefix="encore-batched-inv-") as tmp:
    source = Path(tmp) / "test.cpp"
    source.write_text(host)
    for opt in ("-O0", "-O2"):
        binary = Path(tmp) / ("binary" + opt)
        subprocess.run(["c++", "-std=c++20", opt, "-pthread",
                        "-Wall", "-Wextra", "-Werror", "-I", str(root / "headless"),
                        str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
        print(f"EDEN_NATIVE_BATCHED_INVALIDATION_HOST_PASS profile={opt}")
