#!/usr/bin/env python3
"""Compile all three actual maintained GetSlabIndex helpers against the slab API."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-threading/src/core/hle/kernel/slab_helpers.h").read_text()
assert src.count("kernel.SlabHeap<Derived>().GetObjectIndex(static_cast<const Derived*>(this));")==3
assert "SlabHeap<Derived>(kernel).GetObjectIndex" not in src
assert ".GetIndex(static_cast<const Derived*>(this))" not in src
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler
stub=r"""
#pragma once
#include <cstddef>
#include <cstdint>
#include <type_traits>
namespace Kernel {
class KernelCore;
class KAutoObject {
public:
 explicit KAutoObject(KernelCore&){}
 virtual ~KAutoObject()=default;
 virtual void Destroy(KernelCore&){}
 virtual void Finalize(KernelCore&){}
 static void Create(KAutoObject*){}
};
class KAutoObjectWithList: public KAutoObject {
public: explicit KAutoObjectWithList(KernelCore& kernel):KAutoObject(kernel){}
};
class KernelCore {
public:
 template<class T> struct Heap {
  std::size_t GetObjectIndex(const T*)const{return 7;}
  T* Allocate(KernelCore&){return nullptr;}
  void Free(T*){}
  void Initialize(void*,std::size_t){}
  std::size_t GetObjectSize()const{return 1;}
  std::size_t GetSlabHeapSize()const{return 1;}
  std::size_t GetPeakIndex()const{return 0;}
  std::uintptr_t GetSlabHeapAddress()const{return 0;}
  std::size_t GetNumRemaining()const{return 1;}
 };
 template<class T> Heap<T>& SlabHeap(){static Heap<T> value;return value;}
 struct Objects {
  void Unregister(KAutoObject*){}
  void Register(KAutoObject*){}
  void Initialize(){}
 };
 Objects& ObjectListContainer(){static Objects obj;return obj;}
};
}
"""
fixture=r"""
#include <cassert>
#include "core/hle/kernel/slab_helpers.h"
struct Plain:Kernel::KSlabAllocated<Plain>{};
struct Owned:Kernel::KAutoObjectWithSlabHeap<Owned,Kernel::KAutoObject>{
 explicit Owned(Kernel::KernelCore& k):Kernel::KAutoObjectWithSlabHeap<Owned,Kernel::KAutoObject>(k){}
 static void PostDestroy(Kernel::KernelCore&,std::uintptr_t){}
};
struct Listed:Kernel::KAutoObjectWithSlabHeapAndContainer<Listed,Kernel::KAutoObjectWithList>{
 explicit Listed(Kernel::KernelCore& k):Kernel::KAutoObjectWithSlabHeapAndContainer<Listed,Kernel::KAutoObjectWithList>(k){}
 static void PostDestroy(Kernel::KernelCore&,std::uintptr_t){}
};
int main(){
 Kernel::KernelCore k;
 Plain a;Owned b(k);Listed c(k);
 assert(a.GetSlabIndex(k)==7);
 assert(b.GetSlabIndex(k)==7);
 assert(c.GetSlabIndex(k)==7);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-slab-index-") as temp:
 d=Path(temp)
 header=d/"core/hle/kernel/k_auto_object.h"
 header.parent.mkdir(parents=True)
 header.write_text(stub)
 for name in ("k_auto_object_container.h","kernel.h"):
  (header.parent/name).write_text("#pragma once\n")
 (d/"fixture.cpp").write_text(fixture)
 exe=d/"test"
 subprocess.run([compiler,"-std=c++20","-O1","-g","-pthread","-Wall","-Wextra",
 "-Werror","-fsanitize=address,undefined","-fno-sanitize-recover=all",
 "-I",str(d),"-I",str(root/"vendor/encore-active/eden-threading/src"),
 str(d/"fixture.cpp"),"-o",str(exe)],check=True,timeout=90)
 subprocess.run([str(exe)],check=True,timeout=90)
print("NATIVE_SLAB_INDEX_HOST_PASS all_three_helpers=1 correct_heap_accessor=1 asan_ubsan=1")
