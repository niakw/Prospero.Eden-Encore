#!/usr/bin/env python3
"""Host witness: stale GPU device span after a partial unmap/untracked map."""
from pathlib import Path
import difflib
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
pinned=(root/"vendor/sources/eden/src/core/device_memory_manager.inc").read_text()
native=(root/"vendor/encore-active/eden-core/overrides/core/device_memory_manager.inc").read_text()
header=(root/"vendor/sources/eden/src/core/device_memory_manager.h").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
workflow=(root/".github/workflows/encore-core-preflight.yml").read_text()
actual_tu=(root/"vendor/sources/eden/src/video_core/host1x/gpu_device_memory_manager.cpp").read_text()

# The upstream implementation must be untouched; this native override only
# inserts continuity invalidation points, bounded predecessor helper, and\n# exactly two explicit guarded native GetSpan methods.
edits=difflib.SequenceMatcher(
    None, pinned.splitlines(keepends=True), native.splitlines(keepends=True),
    autojunk=False).get_opcodes()
assert all(tag in ("equal","insert") for tag,*_ in edits), edits
inserts=["".join(native.splitlines(keepends=True)[j1:j2])
         for tag,i1,i2,j1,j2 in edits if tag=="insert"]
# The native override also adds exactly two guarded direct-span reads.
# Exclude only those source-pinned guards from the historical continuity
# insertion budget; never raise the limit for unrelated vendor rewrites.
span_guard = """    // The GPU address space is bounded. Reject empty, overflowing and
    // out-of-range spans before indexing the sparse page map or calculating
    // size + subbits, whose unsigned overflow could incorrectly allow a
    // direct pointer covering unmapped memory.
    if (size == 0 || src_addr >= device_as_size ||
        size > device_as_size - src_addr) {
        return nullptr;
    }
"""
assert native.count(span_guard) == 2
assert (root/"tools/check-native-device-span-bounds-host.py").is_file()
assert "python3 -B tools/check-native-device-span-bounds-host.py" in workflow
assert len(inserts)>=7 and sum(len(s) for s in inserts)-2*len(span_guard)<1900, inserts
for token in (
    "void TruncateContinuityBefore(Entries& entries, size_t changed_page)",
    "entries.GetAndFault(p).continuity_tracker =",
    "tracked_entries.GetUnchecked(start_page_d + i).continuity_tracker = 0;",
    "entry.continuity_tracker = 0;",
):
    assert native.count(token)==1,token
assert native.count("TruncateContinuityBefore(tracked_entries, start_page_d);")==2
assert "bool track = false" in header
assert '#include "core/device_memory_manager.inc"' in actual_tu
assert 'target_include_directories(video_core BEFORE PRIVATE' in cmake
assert cmake.count("Missing maintained native device memory continuity")==1
assert "python3 -B tools/check-native-device-continuity-host.py" in workflow

first="template <typename Traits>\nu8* DeviceMemoryManager<Traits>::GetSpan("
last="template <typename Traits>\nvoid DeviceMemoryManager<Traits>::InnerGatherDeviceAddresses("
assert pinned.count(first)==1 and pinned.count(last)==1
actual=pinned[pinned.index(first):pinned.index(last)]
assert actual.count("continuity_tracker+1")==2
helper=native.split("template <class Entries>\n",1)[1].split("class MultiAddressContainer",1)[0]
helper="template <class Entries>\n"+helper
cpp=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
using u8=std::uint8_t;
using u32=std::uint32_t;
using DAddr=std::uint64_t;
namespace Core {
@@HELPER@@
struct Entry { u32 continuity_tracker{}; u8* ptr{}; };
struct Entries {
    std::array<Entry,4> data{};
    Entry& operator[](std::size_t n){return data.at(n);}
    const Entry& operator[](std::size_t n) const{return data.at(n);}
    Entry& GetAndFault(std::size_t n){return data.at(n);}
};
struct Mock {};
template<class T> struct DeviceMemoryManager {
    static constexpr std::size_t page_bits=12, page_mask=4095;
    Entries tracked_entries;
    template<class V> V* GetPointer(DAddr a) {
        u8* p=tracked_entries[a>>page_bits].ptr;
        return p?reinterpret_cast<V*>(p+(a&page_mask)):nullptr;
    }
    template<class V> const V* GetPointer(DAddr a) const {
        const u8* p=tracked_entries[a>>page_bits].ptr;
        return p?reinterpret_cast<const V*>(p+(a&page_mask)):nullptr;
    }
    u8* GetSpan(DAddr,std::size_t);
    const u8* GetSpan(DAddr,std::size_t) const;
    void Map(std::size_t p,u8* physical){
#ifdef NATIVE_RESET
        TruncateContinuityBefore(tracked_entries,p);
        tracked_entries.GetAndFault(p).continuity_tracker=0;
#endif
        tracked_entries.GetAndFault(p).ptr=physical;
    }
    void Unmap(std::size_t p){
#ifdef NATIVE_RESET
        TruncateContinuityBefore(tracked_entries,p);
        tracked_entries.GetAndFault(p).continuity_tracker=0;
#endif
        tracked_entries.GetAndFault(p).ptr=nullptr;
    }
};
@@METHODS@@
}
int main(){
    std::array<u8,16384> physical{};
    std::array<u8,4096> replacement{};
    Core::DeviceMemoryManager<Core::Mock> d;
    auto& e=d.tracked_entries;
    for(std::size_t p=0;p<3;++p){
        e[p].ptr=physical.data()+p*4096;
        e[p].continuity_tracker=static_cast<u32>(2-p);
    }
    assert(d.GetSpan(0,12288)==physical.data());
    d.Unmap(1);
#ifdef NATIVE_RESET
    assert(e[0].continuity_tracker==0);
    assert(d.GetSpan(0,8192)==nullptr);
    assert(static_cast<const decltype(d)&>(d).GetSpan(0,8192)==nullptr);
#else
    assert(d.GetSpan(0,8192)==physical.data()); // stale pointer
#endif
    d.Map(1,replacement.data()); // default track=false
#ifdef NATIVE_RESET
    assert(e[1].continuity_tracker==0);
    assert(d.GetSpan(0,8192)==nullptr);
    assert(d.GetSpan(4096,8192)==nullptr);
#else
    assert(d.GetSpan(0,8192)==physical.data());
    assert(d.GetSpan(4096,8192)==replacement.data());
#endif
    assert(d.GetSpan(0,4096)==physical.data());
    assert(d.GetSpan(4096,4096)==replacement.data());
    e[1].ptr=physical.data()+4096; // restore an actually contiguous prefix
    e[0].continuity_tracker=2;
    e[1].continuity_tracker=1;
    e[2].continuity_tracker=0;
    d.Map(2,replacement.data());
#ifdef NATIVE_RESET
    assert(e[0].continuity_tracker==1);
    assert(e[1].continuity_tracker==0);
    assert(d.GetSpan(0,12288)==nullptr);
    assert(d.GetSpan(0,8192)==physical.data());
#else
    assert(e[0].continuity_tracker==2);
    assert(d.GetSpan(0,12288)==physical.data());
#endif
}
"""
clang=shutil.which("clang++-18") or shutil.which("clang++")
assert clang,"Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-continuity-") as tmp:
    t=Path(tmp)
    for name,native_build in (("pinned",False),("native",True)):
        file=t/(name+".cpp")
        file.write_text(cpp.replace("@@HELPER@@",helper).replace("@@METHODS@@",actual))
        exe=t/name
        command=[clang,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                 "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                 "-D_GLIBCXX_ASSERTIONS"]
        if native_build: command.append("-DNATIVE_RESET")
        command += [str(file),"-o",str(exe)]
        subprocess.run(command,check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=45)
print("NATIVE_DEVICE_CONTINUITY_HOST_PASS original_partial_unmap_stale=1 original_untracked_remap_stale=1 native_prior_prefix_truncated=1 native_const_mutable_span=2")
