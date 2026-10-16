#!/usr/bin/env python3
"""Verify actual pinned and native DeviceMemoryManager::GetSpan methods.

A wrapped size+offset can make an impossible span appear to fit a tracked
contiguous physical run. Host-only, no native build or console assertion.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/core/device_memory_manager.inc").read_text()
native = (root / "vendor/encore-active/eden-core/overrides/core/device_memory_manager.inc").read_text()
traits = (root / "vendor/sources/eden/src/video_core/host1x/gpu_device_memory_manager.h").read_text()
header = (root / "vendor/sources/eden/src/core/device_memory_manager.h").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

start = "template <typename Traits>\nu8* DeviceMemoryManager<Traits>::GetSpan("
end = "template <typename Traits>\nvoid DeviceMemoryManager<Traits>::InnerGatherDeviceAddresses("
assert pinned.count(start) == native.count(start) == 1
assert pinned.count(end) == native.count(end) == 1
original = pinned.split(start, 1)[1].split(end, 1)[0]
updated = native.split(start, 1)[1].split(end, 1)[0]
guard = """    // The GPU address space is bounded. Reject empty, overflowing and
    // out-of-range spans before indexing the sparse page map or calculating
    // size + subbits, whose unsigned overflow could incorrectly allow a
    // direct pointer covering unmapped memory.
    if (size == 0 || src_addr >= device_as_size ||
        size > device_as_size - src_addr) {
        return nullptr;
    }
"""
assert updated == original.replace(
    "    size_t page_index = src_addr >> page_bits;\n",
    guard + "    size_t page_index = src_addr >> page_bits;"
    + "\n"
)
assert updated.count(guard) == 2
assert original.count(">= size + subbits") == 2
assert "device_virtual_bits = 34" in traits
assert "device_as_size = 1ULL << device_virtual_bits" in header
assert "target_include_directories(video_core BEFORE PRIVATE" in cmake
assert 'python3 -B tools/check-native-device-span-bounds-host.py' in workflow

cpp = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
using u8 = std::uint8_t;
using u32 = std::uint32_t;
using DAddr = std::uint64_t;
namespace Core {
struct Traits { static constexpr std::size_t device_virtual_bits = 34; };
template <typename T> class DeviceMemoryManager {
public:
    static constexpr std::size_t page_bits = 12;
    static constexpr std::size_t page_mask = (1ULL << page_bits) - 1;
    static constexpr std::size_t device_as_size = 1ULL << T::device_virtual_bits;
    struct Entry { u32 continuity_tracker{}; };
    std::array<Entry, 3> tracked_entries{};
    std::array<u8, 3 * 4096> storage{};
    template<class V> V* GetPointer(DAddr a) {
        return a < storage.size() ? reinterpret_cast<V*>(storage.data()+a) : nullptr;
    }
    template<class V> const V* GetPointer(DAddr a) const {
        return a < storage.size() ? reinterpret_cast<const V*>(storage.data()+a) : nullptr;
    }
    u8* GetSpan(DAddr, std::size_t);
    const u8* GetSpan(DAddr, std::size_t) const;
};
}
@@ACTUAL_METHODS@@
int main(int argc, char**) {
    Core::DeviceMemoryManager<Core::Traits> mgr;
    auto& read = static_cast<const Core::DeviceMemoryManager<Core::Traits>&>(mgr);
    mgr.tracked_entries[0].continuity_tracker = 1;
    if (argc > 1) {
        // Old arithmetic: SIZE_MAX + offset 1 wraps to zero.
        assert(mgr.GetSpan(1, std::numeric_limits<std::size_t>::max()) != nullptr);
        assert(read.GetSpan(1, std::numeric_limits<std::size_t>::max()) != nullptr);
        assert(mgr.GetSpan(0, 0) != nullptr);
        return 0;
    }
    assert(mgr.GetSpan(0,4096) == mgr.storage.data());
    assert(read.GetSpan(1,4096) == mgr.storage.data()+1);
    assert(mgr.GetSpan(4094,4) == mgr.storage.data()+4094);
    assert(read.GetSpan(4094,4) == mgr.storage.data()+4094);
    assert(mgr.GetSpan(0,8193) == nullptr);
    assert(mgr.GetSpan(4095,8193) == nullptr);
    assert(mgr.GetSpan(0,0) == nullptr);
    assert(read.GetSpan(0,0) == nullptr);
    assert(mgr.GetSpan(1,std::numeric_limits<std::size_t>::max()) == nullptr);
    assert(read.GetSpan(1,std::numeric_limits<std::size_t>::max()) == nullptr);
    assert(mgr.GetSpan(mgr.device_as_size,1) == nullptr);
    assert(read.GetSpan(mgr.device_as_size,1) == nullptr);
    assert(mgr.GetSpan(mgr.device_as_size-1,2) == nullptr);
    assert(read.GetSpan(mgr.device_as_size-1,2) == nullptr);
    assert(mgr.GetSpan(std::numeric_limits<DAddr>::max(),4096) == nullptr);
    assert(read.GetSpan(std::numeric_limits<DAddr>::max(),4096) == nullptr);
}
"""
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-device-span-bounds-") as tmp:
    directory = Path(tmp)
    for label, segment, negative in (
        ("pinned", original, True),
        ("native", updated, False),
    ):
        source = directory / (label + ".cpp")
        binary = directory / label
        source.write_text(cpp.replace("@@ACTUAL_METHODS@@", start + segment))
        subprocess.run(
            [clang, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
             "-D_GLIBCXX_ASSERTIONS", "-fsanitize=address,undefined",
             "-fno-sanitize-recover=all", str(source), "-o", str(binary)],
            check=True, timeout=45
        )
        subprocess.run([str(binary), "--original"] if negative else [str(binary)],
                       check=True, timeout=45)
print("NATIVE_DEVICE_SPAN_BOUNDS_HOST_PASS original_wrapped_size_alias=2 zero_alias=1 native_const_mutable=2 mapped=1 partial=1 zero=1 overflow=1 virtual_end=1")
