#!/usr/bin/env python3
"""C++20 ASan/UBSan: production slab heap under concurrent Allocate/Free."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_slab_heap.h").read_text()
assert "Node* ret = m_head.load(std::memory_order_relaxed);" in source
assert "m_head.store(ret->next, std::memory_order_relaxed);" in source
assert "node->next = m_head.load(std::memory_order_relaxed);" in source
assert "m_head.store(node, std::memory_order_relaxed);" in source
assert "m_lock.lock();" in source and "m_lock.unlock();" in source
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler
fixture=r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_set>
#include <vector>
#define YUZU_NON_COPYABLE(T) T(const T&)=delete;T& operator=(const T&)=delete;
#define YUZU_NON_MOVEABLE(T) T(T&&)=delete;T& operator=(T&&)=delete;
#define ASSERT(x) assert(x)
using u8=std::uint8_t;
namespace Common {
template<typename T> bool AtomicCompareAndSwap(T* p,T desired,T expected,T& old) {
 old=*p;
 if(old!=expected)return false;
 *p=desired;return true;
}
}
#include "core/hle/kernel/k_slab_heap.h"
int main() {
 constexpr int n=2048;
 alignas(64) Kernel::impl::KSlabHeapImpl::Node nodes[n]{};
 Kernel::impl::KSlabHeapImpl pool;
 pool.Initialize();
 for(auto& item:nodes)pool.Free(&item);
 std::mutex observed_mutex;
 std::unordered_set<void*> live;
 std::atomic<bool> collision{false};
 auto work=[&]{
  for(int i=0;i<10000;++i) {
   void* node=nullptr;
   while(!(node=pool.Allocate()))std::this_thread::yield();
   {
    std::lock_guard lock(observed_mutex);
    if(!live.insert(node).second)collision.store(true);
   }
   static_cast<Kernel::impl::KSlabHeapImpl::Node*>(node)->next=nullptr;
   {
    std::lock_guard lock(observed_mutex);
    if(live.erase(node)!=1)collision.store(true);
   }
   pool.Free(node);
  }
 };
 std::vector<std::thread> threads;
 for(int i=0;i<4;++i)threads.emplace_back(work);
 for(auto& t:threads)t.join();
 assert(!collision.load());
 assert(live.empty());
 std::unordered_set<void*> available;
 for(int i=0;i<n;++i){
  auto* node=pool.Allocate();
  assert(node&&available.insert(node).second);
 }
 assert(pool.Allocate()==nullptr);
 for(auto* ptr:available)pool.Free(ptr);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-kernel-slab-") as temp:
 d=Path(temp)
 for name in ("common/assert.h","common/atomic_ops.h","common/common_funcs.h","common/common_types.h"):
  p=d/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("#pragma once\n")
 (d/"fixture.cpp").write_text(fixture)
 exe=d/"test"
 subprocess.run([compiler,"-std=c++20","-O1","-g","-pthread","-Wall","-Wextra",
  "-Werror","-fsanitize=address,undefined","-fno-sanitize-recover=all",
  "-I",str(d),"-I",str(root/"vendor/encore-active/eden-threading/src"),
  str(d/"fixture.cpp"),"-o",str(exe)],check=True,timeout=90)
 subprocess.run([str(exe)],check=True,timeout=90)
print("KERNEL_SLAB_MUTEX_HOST_PASS relaxed_atomic_under_mutex=1 parallel_owners=1 exhaustion=1 sanitizers=1")
