#!/usr/bin/env python3
"""Source-derived native guest memory GetSpan boundaries under Clang ASan/UBSan."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
old=(root/"vendor/sources/eden/src/core/memory.cpp").read_text()
new=(root/"vendor/encore-active/eden-core/src/core/memory.cpp").read_text()
cm=(root/"headless/CMakeLists.txt").read_text()
ci=(root/".github/workflows/encore-core-preflight.yml").read_text()
start="    [[nodiscard]] inline const u8* GetSpan("
end="    bool WriteBlockImpl("
assert old.count(start)==new.count(start)==1
def methods(s):return start+s.split(start,1)[1].split(end,1)[0]
original=methods(old)
maintained=methods(new)
assert new==old.replace(original,maintained), "Unexpected changes to pinned guest memory"
assert original.count("[(addr + size) >> YUZU_PAGEBITS]")==2
assert maintained.count("[last_address >> YUZU_PAGEBITS]")==2
assert maintained.count("size == 0 || addr >= max_addr || size > max_addr - addr")==2
assert maintained.count("const VAddr last_address = addr + size - 1;")==2
assert cm.count("EDEN_CORE_MEMORY_SOURCE")==4
assert "vendor/encore-active/eden-core/src/core/memory.cpp" in cm
assert "check-ps5-memory-span-host.py" in ci
source=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
using VAddr=std::uint64_t;
using u8=std::uint8_t;
constexpr unsigned YUZU_PAGEBITS=12;
struct Entry{unsigned block{};unsigned Block()const{return block;}};
struct PageTable{
    std::array<Entry,2> entries{{{1},{2}}};
    unsigned GetAddressSpaceBits()const{return 13;}
};
struct Impl {
    PageTable table{};
    PageTable* current_page_table=&table;
    std::array<u8,8192> buffer{};
    const u8* GetPointerSilent(VAddr addr)const noexcept{
        return addr<buffer.size()?buffer.data()+addr:nullptr;
    }
    u8* GetPointerSilent(VAddr addr)noexcept{
        return addr<buffer.size()?buffer.data()+addr:nullptr;
    }
__METHODS__
};
int main(){
    Impl m;
    const Impl& c=m;
#ifdef PINNED
    // Exactly on a page boundary, the pinned source checks the NEXT page.
    assert(m.GetSpan(0,4096)==nullptr);
    assert(c.GetSpan(0,4096)==nullptr);
    assert(m.GetSpan(4094,2)==nullptr);
#else
    assert(m.GetSpan(0,4096)==m.buffer.data());
    assert(c.GetSpan(0,4096)==m.buffer.data());
    assert(m.GetSpan(4094,2)==m.buffer.data()+4094);
    assert(c.GetSpan(4094,2)==m.buffer.data()+4094);
    assert(m.GetSpan(4096,4096)==m.buffer.data()+4096);
    assert(c.GetSpan(4096,4096)==m.buffer.data()+4096);
    assert(m.GetSpan(4096,4097)==nullptr);
    assert(c.GetSpan(4096,4097)==nullptr);
    assert(m.GetSpan(0,0)==nullptr);
    assert(c.GetSpan(0,0)==nullptr);
    assert(m.GetSpan(UINT64_MAX-5,16)==nullptr);
    assert(c.GetSpan(UINT64_MAX-5,16)==nullptr);
    assert(m.GetSpan(100,4096)==nullptr);
    assert(c.GetSpan(100,4096)==nullptr);
    assert(m.GetSpan(4096,128)==m.buffer.data()+4096);
    assert(c.GetSpan(4096,128)==m.buffer.data()+4096);
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler,"Clang needed"
with tempfile.TemporaryDirectory(prefix="encore-guest-span-") as folder:
    for name,body,flags in (("pinned",original,["-DPINNED"]),("maintained",maintained,[])):
        cpp=Path(folder)/(name+".cpp")
        exe=Path(folder)/name
        cpp.write_text(source.replace("__METHODS__",body))
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
            "-fsanitize=address,undefined","-fno-sanitize-recover=all",
            *flags,str(cpp),"-o",str(exe)],check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=30)
print("MEMORY_SPAN_HOST_PASS original_false_negative=1 last_page=1 half_open=1 zero=1 overflow=1 both_overloads=1")
