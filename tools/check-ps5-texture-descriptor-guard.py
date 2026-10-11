#!/usr/bin/env python3
"""R312: exact pinned Eden TIC replay and host-compiled mapping/format test."""
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pin = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
source_name = "src/video_core/texture_cache/util.cpp"
git_blob = "e55d0752eca7070d5fb43737923a41502901ed4f"
patch_name = "headless/backports/eden-ps5-texture-descriptor-residency.patch"
apply = (root / "tools/apply-eden-backports.sh").read_text()
assert "expected=" + pin in apply
assert apply.count("apply_one \"$root/" + patch_name + "\"") == 1
request = Request("https://raw.githubusercontent.com/eden-emulator/mirror/"
                  + pin + "/" + source_name,
                  headers={"User-Agent": "Eden-Encore-R312-pinned-TIC-test"})
with urlopen(request, timeout=25) as reply:
    source = reply.read(250000)
assert hashlib.sha1(b"blob " + str(len(source)).encode() +
                    b"\\0" + source).hexdigest() == git_blob

with tempfile.TemporaryDirectory(prefix="eden-r312-TIC-") as d:
    path = Path(d) / source_name
    path.parent.mkdir(parents=True)
    path.write_bytes(source)
    patch = root / patch_name
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=d, check=True, timeout=10)
    subprocess.run(["git", "apply", str(patch)], cwd=d, check=True, timeout=10)
    data = path.read_text()
    begin = data.index("bool IsValidEntry(")
    end = data.index("\nboost::container::small_vector<BufferImageCopy", begin)
    fn = data[begin:end]
    assert fn.count("#ifdef PS5_NATIVE") == 2
    assert "if (config.is_sparse == 0)" in fn
    assert "config.format == static_cast<Tegra::Texture::TextureFormat>(0)" in fn
    # Build and execute the ORIGINAL C++ routine with simple memory-manager
    # doubles. Avoid rewriting a Python approximation of the decision logic.
    source_test = r"""
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
""" + fn + r"""
int main() {
    const Tegra::MemoryManager first{true, true};
    const Tegra::MemoryManager only_later{false, true};
    const Tegra::MemoryManager absent{false, false};
    TICEntry t{};
    assert(IsValidEntry(first, t));
    t.addr = 0; assert(!IsValidEntry(first, t));
    t.addr = 1ULL << 40; assert(!IsValidEntry(first, t));
    t.addr = 8192;
#ifdef PS5_NATIVE
    t.format = Tegra::Texture::TextureFormat::Invalid;
    assert(!IsValidEntry(first, t)); // don't invent a valid RGBA8 view
    t.format = Tegra::Texture::TextureFormat::Valid;
    t.is_sparse = 0;
    assert(!IsValidEntry(only_later, t)); // no backing for first non-sparse page
#else
    t.is_sparse = 0;
    assert(IsValidEntry(only_later, t)); // upstream semantics remain unchanged
#endif
    t.is_sparse = 1;
    assert(IsValidEntry(only_later, t)); // sparse texture may start with a hole
    assert(!IsValidEntry(absent, t));
}
"""
    cpp = Path(d) / "tic_guard_test.cpp"
    cpp.write_text(source_test)
    for name, flags in (("ps5", ["-DPS5_NATIVE"]), ("upstream", [])):
        executable = Path(d) / name
        subprocess.run(["c++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        *flags, str(cpp), "-o", str(executable)],
                       check=True, timeout=30)
        subprocess.run([str(executable)], check=True, timeout=10)
        print("PASS R312 exact patched C++ valid/invalid/sparse TIC contract", name)
print("PASS R312 pinned upstream SHA-verified git apply; PS5 guard and upstream behavior")
