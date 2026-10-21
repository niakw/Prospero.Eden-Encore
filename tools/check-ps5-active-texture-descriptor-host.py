#!/usr/bin/env python3
"""Compile the maintained (CMake-selected) native TIC guard, offline."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
path = root / "vendor/encore-active/eden-core/src/video_core/texture_cache/util.cpp"
cmake = (root / "headless/CMakeLists.txt").read_text()
assert '"${PORT_ROOT}/vendor/encore-active/eden-core/src/video_core/texture_cache/util.cpp"' in cmake
assert 'list(APPEND video_sources "${EDEN_MAINTAINED_TEXTURE_UTIL}")' in cmake
data = path.read_text()
begin = data.index("bool IsValidEntry(")
end = data.index("\nboost::container::small_vector<BufferImageCopy", begin)
fn = data[begin:end]
assert fn.count("#ifdef PS5_NATIVE") == 2
assert 'config.format == static_cast<Tegra::Texture::TextureFormat>(0)' in fn
assert "if (config.is_sparse == 0)" in fn
fixture = r'''
#include <cstdint>
#include <cstddef>
#include <optional>
#include <cassert>
using GPUVAddr = std::uint64_t;
using DAddr = std::uint64_t;
namespace Tegra {
namespace Texture {
enum class TextureFormat : std::uint32_t { Invalid = 0, Valid = 1 };
}
struct MemoryManager {
    bool first{}, any{};
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr) const {
        return first ? std::optional<DAddr>{4096} : std::nullopt;
    }
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr, std::size_t) const {
        return any ? std::optional<DAddr>{8192} : std::nullopt;
    }
};
}
struct TICEntry {
    Tegra::Texture::TextureFormat format{Tegra::Texture::TextureFormat::Valid};
    int is_sparse{};
    GPUVAddr addr{8192};
    GPUVAddr Address() const { return addr; }
};
struct ImageInfo { explicit ImageInfo(const TICEntry&) {} };
std::size_t CalculateGuestSizeInBytes(const ImageInfo&) { return 16384; }
''' + fn + r'''
int main() {
    const Tegra::MemoryManager first{true, true};
    const Tegra::MemoryManager later{false, true};
    const Tegra::MemoryManager none{false, false};
    TICEntry t{};
    assert(IsValidEntry(first, t));
    t.addr = 0; assert(!IsValidEntry(first, t));
    t.addr = 1ULL << 40; assert(!IsValidEntry(first, t));
    t.addr = 8192;
#ifdef PS5_NATIVE
    t.format = Tegra::Texture::TextureFormat::Invalid;
    assert(!IsValidEntry(first, t));
    t.format = Tegra::Texture::TextureFormat::Valid;
    t.is_sparse = 0;
    assert(!IsValidEntry(later, t));
#else
    t.is_sparse = 0;
    assert(IsValidEntry(later, t));
#endif
    t.is_sparse = 1;
    assert(IsValidEntry(later, t));
    assert(!IsValidEntry(none, t));
}
'''
with tempfile.TemporaryDirectory(prefix="encore-active-tic-") as tmp:
    source = Path(tmp) / "tic.cpp"
    source.write_text(fixture)
    for label, flags in (("native", ["-DPS5_NATIVE"]), ("host", [])):
        output = Path(tmp) / label
        subprocess.run(["c++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        *flags, str(source), "-o", str(output)], check=True)
        subprocess.run([str(output)], check=True)
        print(f"ENCORE_ACTIVE_TIC_PASS variant={label}")
