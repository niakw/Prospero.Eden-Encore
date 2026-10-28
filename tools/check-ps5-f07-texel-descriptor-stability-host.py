#!/usr/bin/env python3
"""Source-extracted F07 PS5 texel-descriptor deterministic byte reuse regression.

A VkBufferView only initializes part of DescriptorUpdateEntry. Reusing an
entry with stale union bytes must not force spurious payload reallocations
on identical FC27 HUD texel descriptors. Desktop source stays unchanged.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
header=(ROOT/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
begin="    void AddTexelBuffer(VkBufferView texel_buffer) {"
end="\n\n    void AddTexelBuffer(VkBufferView texel_buffer, VkDeviceAddress"
assert header.count(begin)==header.count(end)==1
method=header[header.index(begin):header.index(end,header.index(begin))]
assert "F07 zero unused native texel descriptor payload bytes" in generator
assert "std::memset(entry, 0, sizeof(*entry));" in method
assert "entry->texel_buffer = texel_buffer;" in method
assert "#else\n        *(payload_cursor++) = texel_buffer;\n#endif" in method
for workflow in (".github/workflows/encore-core-fast-gate.yml",
                 ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-texel-descriptor-stability-host.py" in (ROOT/workflow).read_text()

cpp=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
using VkBufferView=std::uint64_t;
struct DescriptorUpdateEntry {
    VkBufferView texel_buffer{};
    std::uint64_t unused[2]{};
    DescriptorUpdateEntry()=default;
    DescriptorUpdateEntry(VkBufferView view) : texel_buffer{view} {}
    DescriptorUpdateEntry& operator=(VkBufferView view) {texel_buffer=view;return *this;}
};
static_assert(sizeof(DescriptorUpdateEntry)>sizeof(VkBufferView));
struct Queue {
    std::array<DescriptorUpdateEntry,3> payload{};
    DescriptorUpdateEntry* payload_cursor=payload.data();
__METHOD__
};
int main() {
    Queue q;
    // Deliberately reuse storage containing distinct previous-descriptor bytes.
    std::memset(reinterpret_cast<unsigned char*>(&q.payload[0]),0xa5,sizeof(q.payload[0]));
    std::memset(reinterpret_cast<unsigned char*>(&q.payload[1]),0x5a,sizeof(q.payload[1]));
    std::memset(reinterpret_cast<unsigned char*>(&q.payload[2]),0xa5,sizeof(q.payload[2]));
    q.AddTexelBuffer(0xabc);
    q.AddTexelBuffer(0xabc);
    q.AddTexelBuffer(0xdef);
    assert(q.payload_cursor==q.payload.data()+3);
    assert(q.payload[0].texel_buffer==0xabc && q.payload[1].texel_buffer==0xabc);
    assert(q.payload[2].texel_buffer==0xdef);
    const bool same=std::memcmp(&q.payload[0],&q.payload[1],sizeof(q.payload[0]))==0;
    const bool changed=std::memcmp(&q.payload[0],&q.payload[2],sizeof(q.payload[0]))!=0;
    assert(changed);
#ifdef PS5_NATIVE
    assert(same);
    for(std::size_t i=sizeof(VkBufferView);i<sizeof(q.payload[0]);++i) {
        const auto* b=reinterpret_cast<const unsigned char*>(&q.payload[0]);
        assert(b[i]==0);
    }
#else
    assert(!same);
#endif
}
""".replace("__METHOD__",method)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler unavailable"
with tempfile.TemporaryDirectory(prefix="encore-f07-texel-descriptors-") as folder:
    p=Path(folder)/"texel.cpp"
    p.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            exe=Path(folder)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-Wno-class-memaccess","-fsanitize=undefined",
                 "-fno-sanitize-recover=all",*(['-DPS5_NATIVE=1'] if native else []),
                 str(p),"-o",str(exe)]
            compiled=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert compiled.returncode==0,(native,opt,compiled.stderr[-3000:])
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            assert ran.returncode==0,(native,opt,ran.stderr[-3000:])
print("F07_TEXEL_DESCRIPTOR_STABILITY_PASS native=1 desktop_original=1 O0=1 O2=1 stale_bytes=0 handle_change=1")
