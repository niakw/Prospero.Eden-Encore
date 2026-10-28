#!/usr/bin/env python3
"""Source-extracted PS5 descriptor-buffer semantic reuse witness, Clang ASan/UBSan."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
pipeline = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
assert "std::memcmp(last_descriptor_payload.data(), entries," in pipeline
assert "check-ps5-descriptor-entry-canonical-host.py" in workflow
assert '"#include <variant>"' in generator
# Generator text may contain both replay old/new string forms; assert the
# individual reviewed deltas rather than counting Python string literals.
for label in ("F07 zero native image descriptor payload bytes for legacy and buffer reuse",
              "F07 zero unused native texel descriptor payload bytes"):
    assert label in generator
assert header.count('std::memset(entry, 0, sizeof(*entry));') == 5
assert header.count('entry->texel_buffer = texel_buffer;') == 1
assert "#ifdef PS5_NATIVE\n#include <cstring>" in header

types = header[header.index("struct DescriptorAddress {"):header.index("class UpdateDescriptorQueue final")]
methods = header[header.index("    void AddSampledImage("):header.index("\nprivate:",header.index("    void AddSampledImage("))]
cpp = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <type_traits>
#include <variant>
#include <vector>
using VkDeviceAddress = std::uint64_t;
using VkDeviceSize = std::uint64_t;
using VkFormat = std::uint32_t;
using VkBufferView = std::uint64_t;
using VkImageView = std::uint64_t;
using VkSampler = std::uint64_t;
using VkBuffer = std::uint64_t;
using VkImageLayout = std::uint32_t;
constexpr VkDeviceSize VK_WHOLE_SIZE = UINT64_MAX;
constexpr VkFormat VK_FORMAT_UNDEFINED = 0;
constexpr VkImageLayout VK_IMAGE_LAYOUT_GENERAL = 1;
constexpr std::uint64_t VK_NULL_HANDLE = 0;
struct VkDescriptorImageInfo {VkSampler sampler;VkImageView imageView;VkImageLayout imageLayout;};
struct VkDescriptorBufferInfo {VkBuffer buffer;VkDeviceSize offset;VkDeviceSize range;};
__TYPES__
struct Queue {
  bool use_descriptor_buffer{true};
  DescriptorUpdateEntry* payload_cursor{};
__METHODS__
};
int main() {
  static_assert(std::is_trivially_copyable_v<DescriptorUpdateEntry>);
  static_assert(sizeof(DescriptorUpdateEntry)==24);
  std::array<DescriptorUpdateEntry,1> a{},b{};
  Queue first{true,a.data()},second{true,b.data()};
  auto test = [&](auto write) {
    // Emulate previously used ring slots with different inactive bytes.
    std::memset(a.data(),0x11,sizeof(a));
    std::memset(b.data(),0xEE,sizeof(b));
    first.payload_cursor=a.data();second.payload_cursor=b.data();
    write(first);write(second);
    assert(first.payload_cursor==a.data()+1);
    assert(second.payload_cursor==b.data()+1);
    // Bytes, including the inactive union portion and struct padding, must
    // be reproducible because production compares the entire union.
    assert(std::memcmp(a.data(),b.data(),sizeof(DescriptorUpdateEntry))==0);
    std::vector<DescriptorUpdateEntry> cache(a.begin(),a.end());
    assert(std::memcmp(cache.data(),b.data(),sizeof(DescriptorUpdateEntry))==0);
  };
  test([](Queue& q){q.AddSampledImage(17,23);});
  test([](Queue& q){q.AddImage(17);});
  test([](Queue& q){q.AddBuffer(7,42,8,16);});
  test([](Queue& q){q.AddTexelBuffer(9,42,8,16,31);});
  // The ordinary (non-descriptor-buffer) path retains the original Vulkan
  // update-template values; it must not be forced through the new writes.
  first.use_descriptor_buffer=false;
  first.payload_cursor=a.data();
  first.AddBuffer(7,8,16);
  assert(a[0].buffer.buffer==7 && a[0].buffer.offset==8 && a[0].buffer.range==16);
  first.payload_cursor=a.data();
  first.AddTexelBuffer(9);
  assert(a[0].texel_buffer==9);
}
"""
cpp = cpp.replace("__TYPES__",types).replace("__METHODS__",methods)
cc = shutil.which("clang++-18") or shutil.which("clang++")
assert cc, "Clang C++20 is required"
with tempfile.TemporaryDirectory(prefix="encore-descriptor-entry-canonical-") as tmp:
    source = Path(tmp) / "witness.cpp"
    source.write_text(cpp)
    for label,defines in (("native",["-DPS5_NATIVE"]),("upstream",[])):
        exe = Path(tmp) / label
        subprocess.run([cc,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        *defines,str(source),"-o",str(exe)],check=True,timeout=45)
        if label=="native":
            subprocess.run([str(exe)],check=True,timeout=30)
        else:
            # Compilation-only ABI check: raw padding comparison is intentionally
            # not enforced on the unchanged non-native path.
            pass
print("DESCRIPTOR_ENTRY_CANONICAL_HOST_PASS byte_stable=4 copy_stable=4 native_writers=5 nonbuffer_semantics=1")
