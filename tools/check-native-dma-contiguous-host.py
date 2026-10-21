#!/usr/bin/env python3
"""Real-source C++20 constexpr DMA coalescing oracle with ASan/UBSan."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-core/src/video_core/engines/maxwell_dma.cpp").read_text()
start="constexpr bool CanCoalescePitchDma("
assert source.count(start)==1
body=start+source.split(start,1)[1].split("\n}\n} // namespace",1)[0]+"\n}"
assert "width > (~u32{0}) / rows" in body
assert "source + bytes <= dest || dest + bytes <= source" in body
assert source.count("if (CanCoalescePitchDma(")==1
assert source.count("memory_manager.CopyBlock(")>=2
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
fixture=r"""
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <limits>
using u32=std::uint32_t;
using u64=std::uint64_t;
using s64=std::int64_t;
__BODY__
int main() {
 u64 n=99;
 assert(CanCoalescePitchDma(0x1000,0x2000,128,8,128,128,n) && n==1024);
 assert(CanCoalescePitchDma(0x1000,0x1400,128,8,128,128,n) && n==1024);
 assert(!CanCoalescePitchDma(0x1000,0x1300,128,8,128,128,n));
 assert(!CanCoalescePitchDma(0x1000,0x1000,128,8,128,128,n));
 assert(!CanCoalescePitchDma(0x1000,0x2000,128,8,144,128,n));
 assert(!CanCoalescePitchDma(0x1000,0x2000,128,8,128,144,n));
 assert(!CanCoalescePitchDma(0x1000,0x2000,128,8,-128,128,n));
 assert(!CanCoalescePitchDma(0x1000,0x2000,0,8,0,0,n));
 assert(!CanCoalescePitchDma(0x1000,0x2000,128,0,128,128,n));
 assert(!CanCoalescePitchDma(0x1000,0x2000,0xffffffffu,2,0xffffffffu,0xffffffffu,n));
 const u64 max=std::numeric_limits<u64>::max();
 assert(!CanCoalescePitchDma(max-8,0x1000,8,2,8,8,n));
 assert(!CanCoalescePitchDma(0x1000,max-8,8,2,8,8,n));
 assert(!CanCoalescePitchDma(0x1000,0x1007,8,2,8,8,n));
 assert(CanCoalescePitchDma(0x1000,0x1010,8,2,8,8,n)&&n==16);
 assert(n==16);
}
""".replace("__BODY__",body)
with tempfile.TemporaryDirectory(prefix="eden-dma-coalesce-") as temp:
 d=Path(temp);file=d/"copy.cpp";exe=d/"copy"
 file.write_text(fixture)
 subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
 "-fsanitize=address,undefined","-fno-sanitize-recover=all",
 str(file),"-o",str(exe)],check=True,timeout=90)
 subprocess.run([str(exe)],check=True,timeout=90)
print("DMA_COALESCE_HOST_PASS row_contiguous=1 overlap_rejected=1 pitch_rejected=1 overflow_rejected=1")
