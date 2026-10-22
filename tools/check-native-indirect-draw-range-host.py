#!/usr/bin/env python3
"""Reject zero or truncated indirect-draw byte spans in the selected native GPU cache."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = (root / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
backport = (root / "vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
start = "template <class P>\nvoid BufferCache<P>::UpdateDrawIndirect() {"
end = "\ntemplate <class P>"
def method(text):
    assert text.count(start) == 1
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]
native = method(active)
legacy = method(backport)
assert "if (size == 0 || size > static_cast<size_t>(~u32{0}))" in native
assert "if (size == 0 || size > static_cast<size_t>(~u32{0}))" not in legacy
assert native.index("if (size == 0") < native.index("GpuToCpuAddress(gpu_addr)")
assert native.count("binding = NULL_BINDING;") == 2

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using GPUVAddr = u64;
using DAddr = u64;
using BufferId = u32;
struct Binding { DAddr device_addr{}; u32 size{}; BufferId buffer_id{}; };
inline constexpr Binding NULL_BINDING{};
struct DrawIndirect {
    bool include_count{};
    GPUVAddr count_start_address{0x1000};
    GPUVAddr indirect_start_address{0x2000};
    size_t buffer_size{64};
};
struct Memory {
    bool mapped{true};
    unsigned translations{};
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr addr) {
        ++translations;
        return mapped ? std::optional<DAddr>(addr + 0x10000) : std::nullopt;
    }
};
struct State {
    Binding count_buffer_binding{};
    Binding indirect_buffer_binding{};
};
template<class P> struct BufferCache {
    DrawIndirect* current_draw_indirect{};
    Memory* gpu_memory{};
    State* channel_state{};
    unsigned finds{};
    BufferId FindBuffer(DAddr, u32 size, bool) {
        assert(size != 0);
        ++finds;
        return 17;
    }
    void UpdateDrawIndirect();
};
""" + native + r"""
int main() {
    static_assert(sizeof(size_t) >= 8);
    DrawIndirect d{};
    Memory m{};
    State s{};
    BufferCache<void> c{&d,&m,&s};
    d.include_count = true;
    c.UpdateDrawIndirect();
    assert(c.finds == 2 && m.translations == 2);
    assert(s.count_buffer_binding.size == 4 && s.indirect_buffer_binding.size == 64);
    // A zero-byte subsequent command cannot retain the old indirect buffer.
    d.include_count = false;
    d.buffer_size = 0;
    c.UpdateDrawIndirect();
    assert(c.finds == 2 && m.translations == 2);
    assert(s.indirect_buffer_binding.size == 0);
    // A 4 GiB range used to wrap to zero at the u32 FindBuffer boundary.
    d.buffer_size = static_cast<size_t>(std::numeric_limits<u32>::max()) + 1;
    s.indirect_buffer_binding = Binding{.device_addr=1,.size=42,.buffer_id=17};
    c.UpdateDrawIndirect();
    assert(c.finds == 2 && m.translations == 2);
    assert(s.indirect_buffer_binding.size == 0 && s.indirect_buffer_binding.buffer_id == 0);
    // The largest representable nonzero range must retain the existing path.
    d.buffer_size = std::numeric_limits<u32>::max();
    c.UpdateDrawIndirect();
    assert(c.finds == 3 && s.indirect_buffer_binding.size == d.buffer_size);
    // Unmapped GPU memory still clears a previously live binding.
    m.mapped = false;
    d.buffer_size = 64;
    c.UpdateDrawIndirect();
    assert(c.finds == 3 && s.indirect_buffer_binding.size == 0);
    // Also reject size_t's maximum before GPU address translation.
    unsigned previous_translations = m.translations;
    d.buffer_size = std::numeric_limits<size_t>::max();
    c.UpdateDrawIndirect();
    assert(m.translations == previous_translations && c.finds == 3);
}
"""
compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++ compiler required"
with tempfile.TemporaryDirectory(prefix="encore-indirect-range-") as tmp:
    source = Path(tmp) / "indirect.cpp"
    source.write_text(cpp)
    for opt in ("-O0", "-O2"):
        binary = Path(tmp) / ("indirect" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", str(source), "-o",
                        str(binary)], check=True, timeout=45)
        subprocess.run([str(binary)], check=True, timeout=20)
        print("NATIVE_INDIRECT_DRAW_RANGE_PASS", opt)
