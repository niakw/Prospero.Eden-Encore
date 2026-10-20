#!/usr/bin/env python3
"""Source-extracted host ASan/UBSan: sparse ZeroRegion clips invalid extents.

No inference about actual console memory or gameplay FPS.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
text=(ROOT/"vendor/encore-active/eden-core/src/common/sparse_large_vector.h").read_text()
cmake=(ROOT/"headless/CMakeLists.txt").read_text()
workflow=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
start="    void ZeroRegion(std::size_t start, std::size_t end_) noexcept {"
end="    constexpr void CommitRegion(size_t index, size_t end_) {"
commit_start="    constexpr void CommitRegion(size_t index, size_t end_) {"
commit_end="    constexpr T& GetUnchecked(size_t index) {"
assert text.count(commit_start)==1 and text.count(commit_end)==1
commit_method=text[text.index(commit_start):text.index(commit_end)]
assert "if (index >= end_ || index >= limit) return;" in commit_method
assert "end_ = (std::min)(end_, limit);" in commit_method
assert commit_method.index("index >= end_") < commit_method.index("static_cast<u64>(index) * sizeof(T)")
assert text.count(start)==1 and text.count(end)==1
method=text[text.index(start):text.index(end)]
assert "if (start >= end_ || start >= limit) return;" in method
assert "end_ = (std::min)(end_, limit);" in method
assert method.index("end_ = (std::min)(end_, limit);") < method.index("base_ptr[start]")
assert "std::lock_guard<std::mutex> mutation_lock{sparse_mutation_mutex};" in method
assert 'configure_file("${EDEN_MAINTAINED_SPARSE_VECTOR}"' in cmake
assert "python3 -B tools/check-sparse-zero-bounds-host.py" in workflow
cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
using u64=std::uint64_t;
constexpr std::size_t HostPageSize=16384;
static u64 AlignUp(u64 value,std::size_t alignment) {
    return (value + alignment - 1) & ~(alignment - 1);
}
static u64 AlignDown(u64 value,std::size_t alignment) {
    return value & ~(alignment - 1);
}
struct Table {
    using T=u64;
    std::mutex sparse_mutation_mutex;
    std::size_t alloc_size;
    T* base_ptr;
    unsigned decommits=0, commits=0;
    bool uncommitted_mode=false;
    bool IsCommittedPage(std::size_t index) const {
        assert(index < alloc_size/sizeof(T));
        return !uncommitted_mode;
    }
    void CommitPage(std::size_t index) {
        assert(index < alloc_size/sizeof(T));
        ++commits;
    }
    void DecommitPage(std::size_t index) {
        assert(index < alloc_size/sizeof(T));
        ++decommits;
        auto* page=reinterpret_cast<unsigned char*>(base_ptr+index);
        std::memset(page,0,HostPageSize);
    }
INJECT
INJECT_COMMIT
};
int main() {
    constexpr std::size_t Capacity=2*HostPageSize/sizeof(u64);
    // Another host page is a protected canary after the vector allocation.
    auto* bytes=static_cast<unsigned char*>(std::aligned_alloc(HostPageSize,3*HostPageSize));
    assert(bytes);
    std::memset(bytes,0xA5,3*HostPageSize);
    Table t{ {},2*HostPageSize,reinterpret_cast<u64*>(bytes) };
    t.ZeroRegion(0,0);
    t.ZeroRegion(Capacity,Capacity+20);
    t.ZeroRegion(Capacity-3,Capacity-10);
    assert(t.decommits==0);
    // Clip the oversized end rather than writing into a foreign mapping.
    t.ZeroRegion(Capacity-3,Capacity+40);
    for(std::size_t i=0;i<2*HostPageSize-3*sizeof(u64);++i)
        assert(bytes[i]==0xA5);
    for(std::size_t i=2*HostPageSize-3*sizeof(u64);i<2*HostPageSize;++i)
        assert(bytes[i]==0);
    for(std::size_t i=2*HostPageSize;i<3*HostPageSize;++i)
        assert(bytes[i]==0xA5);
    // Whole committed page is reclaimed only for a completely covered page.
    t.ZeroRegion(0,HostPageSize/sizeof(u64));
    assert(t.decommits==1);
    for(std::size_t i=0;i<HostPageSize;++i) assert(bytes[i]==0);
    t.uncommitted_mode=true;
    t.CommitRegion(0,0);
    t.CommitRegion(Capacity,Capacity+100);
    t.CommitRegion(Capacity-5,Capacity-7);
    assert(t.commits==0);
    t.CommitRegion(Capacity-5,Capacity+100);
    assert(t.commits==1);
    t.CommitRegion(0,Capacity+100);
    assert(t.commits==3);
    std::free(bytes);
    std::puts("ENCORE_SPARSE_ZERO_COMMIT_BOUNDS_PASS");
}
""".replace("INJECT_COMMIT",commit_method).replace("INJECT",method)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-sparse-zero-bounds-") as folder:
    src=Path(folder)/"bounds.cpp"
    exe=Path(folder)/"bounds"
    src.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra",
                    "-Werror","-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all",str(src),"-o",str(exe)],
                    check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("HOST_SPARSE_ZERO_COMMIT_BOUNDS_PASS; console runtime unqualified")
