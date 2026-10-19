#!/usr/bin/env python3
"""C++ sanitizer witness from the actual two maintained Fermi2D address blocks.

The pre-widening source stays immutable as a historical regression witness.
A successful host test does not prove PS5 execution or close GitHub CodeQL.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
engines = root / "vendor/encore-active/eden-core/src/video_core/engines"
pinned = (root / "vendor/sources/eden/src/video_core/engines/fermi_2d.cpp").read_text()
old = "auto address = src.Address() + config.src_x0 * bytes_per_pixel;"
assert pinned.count(old) == 1
blocks = []
for name in ("fermi_2d_observed.cpp", "fermi_2d_experimental.cpp"):
    data = (engines / name).read_text()
    assert old not in data, ("unwidened CodeQL product", name)
    start = data.index("    const auto need_align_to_pitch =")
    stop = data.index("\n    memory_manager.FlushCaching();", start)
    snippet = data[start:stop]
    assert "bytes_per_pixel != 0 &&" in snippet
    assert "static_cast<u64>(config.src_x0) *" in snippet
    assert "static_cast<u64>(bytes_per_pixel)" in snippet
    assert "x_offset > ~u64{0} - base_address" in snippet
    blocks.append(snippet)
assert blocks[0] == blocks[1], "default and optional Fermi protections diverged"
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-fermi2d-address-widening-host.py" in workflow

cpp = r"""
#include <cassert>
#include <cstdint>
#include <limits>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
namespace Tegra::Engines {
struct Fermi2D { enum class MemoryLayout { Pitch, Block }; };
}
struct Surface {
    Tegra::Engines::Fermi2D::MemoryLayout linear;
    u32 width, pitch;
    u64 address;
    u32 addr_upper{}, addr_lower{};
    u64 Address() const { return (static_cast<u64>(addr_upper) << 32) | addr_lower; }
    explicit Surface(Tegra::Engines::Fermi2D::MemoryLayout layout, u32 w,
                     u32 p, u64 a) : linear(layout), width(w), pitch(p),
                                       address(a), addr_upper(u32(a >> 32)),
                                       addr_lower(u32(a)) {}
};
struct Config { s32 src_x0, src_x1; };
static unsigned rejected = 0;
void AssertFailSoftImpl() { ++rejected; }
void Apply(Surface& src, Config& config, u32 bytes_per_pixel) {
__SOURCE__
}
int main() {
    using Layout = Tegra::Engines::Fermi2D::MemoryLayout;
    {
        Surface src{Layout::Pitch, 1024, 32, 0xffffffffULL};
        Config c{16, 1024};
        Apply(src, c, 4);
        assert(rejected == 0);
        assert(src.Address() == 0x10000003fULL && src.width == 1008);
        assert(c.src_x0 == 0 && c.src_x1 == 1008);
    }
    {
        // Prior implicit 32-bit multiplication would wrap and lose upper bits.
        Surface src{Layout::Pitch, 2147483647u, 8, 0x1000};
        Config c{2147483646, 2147483647};
        Apply(src, c, 16);
        assert(rejected == 0);
        assert(src.Address() == 0x1000ULL +
               static_cast<u64>(2147483646ULL) * 16ULL);
        assert(src.width == 1u && c.src_x0 == 0 && c.src_x1 == 1);
    }
    {
        Surface src{Layout::Pitch, 1024, 32, std::numeric_limits<u64>::max()-20};
        Config c{16, 1024};
        const u64 original = src.Address();
        Apply(src, c, 4);
        assert(rejected == 1);
        assert(src.Address() == original && src.width == 1024);
        assert(c.src_x0 == 16 && c.src_x1 == 1024);
    }
    {
        // Zero block size cannot reach pitch division, even on a pitch surface.
        Surface src{Layout::Pitch, 1024, 32, 0x1000};
        Config c{16, 1024};
        Apply(src, c, 0);
        assert(rejected == 1 && src.Address() == 0x1000);
    }
    {
        Surface src{Layout::Pitch, 1024, 32, 0x1000};
        Config c{-1, 1024};
        Apply(src, c, 4);
        assert(rejected == 1 && src.Address() == 0x1000);
    }
    {
        Surface src{Layout::Block, 1024, 32, 0x1000};
        Config c{16, 1024};
        Apply(src, c, 4);
        assert(rejected == 1 && src.Address() == 0x1000);
    }
}
""".replace("__SOURCE__", blocks[0])
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang required for the sanitizer witness"
with tempfile.TemporaryDirectory(prefix="encore-fermi2d-widening-") as tmp:
    source = Path(tmp) / "fermi2d-widening.cpp"
    output = Path(tmp) / "witness"
    source.write_text(cpp)
    subprocess.run(
        [clang, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
         str(source), "-o", str(output)], check=True, timeout=45)
    subprocess.run([str(output)], check=True, timeout=20)
print("FERMI2D_ADDRESS_WIDENING_HOST_PASS variants=2 offset64=1 carry=1 "
      "large_product=1 address_wrap_rejected=1 zero_bpp=1 guards=2 sanitizer=1")
