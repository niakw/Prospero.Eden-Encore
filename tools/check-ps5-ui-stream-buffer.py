#!/usr/bin/env python3
"""Host regression: PS5 launcher must not orphan the same GPU stream buffer every frame.

Compile the pure capacity policy and check exact renderer glue. No PS5 SDK or
hardware timing is exercised; only a real console replay can prove FPS gains.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
header = (ROOT / "headless/prosperoeden/pe/gfx/gl_batch.hpp").read_text()
source = (ROOT / "headless/prosperoeden/pe/gfx/gl_batch.cpp").read_text()
policy = (ROOT / "headless/prosperoeden/pe/gfx/stream_ring_policy.hpp").read_text()

assert "std::array<GLuint, kStreamBufferSlots> vaos_{};" in header
assert "std::array<GLuint, kStreamBufferSlots> buffers_{};" in header
assert "std::array<std::size_t, kStreamBufferSlots> capacities_{};" in header
assert "next_slot_ = 0;" in header
assert "std::size_t slot = next_slot_++ % kStreamBufferSlots;" in source
assert "glBindBuffer(GL_ARRAY_BUFFER, buffers_[slot]);" in source
assert "if (capacity != capacities_[slot])" in source
assert source.count("glBufferData(GL_ARRAY_BUFFER,") == 1
assert "glBindVertexArray(vaos_[slot]);" in source
assert "glDeleteBuffers(static_cast<GLsizei>(buffers_.size()), buffers_.data());" in source
assert "glDeleteVertexArrays(static_cast<GLsizei>(vaos_.size()), vaos_.data());" in source
assert "capacities_.fill(0);" in source
assert "constexpr std::size_t kStreamBufferSlots = 3;" in policy

cxx = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if not cxx:
    raise SystemExit("C++20 compiler needed for UI buffer capacity regression")
cpp = r"""
#include "pe/gfx/stream_ring_policy.hpp"
#include <cassert>
#include <limits>
using namespace pe::gfx;
int main() {
    static_assert(kStreamBufferSlots == 3);
    static_assert(StreamCapacity(0, 0) == 0);
    static_assert(StreamCapacity(0, 1) == 512);
    static_assert(StreamCapacity(0, 512) == 512);
    static_assert(StreamCapacity(0, 513) == 1024);
    static_assert(StreamCapacity(1024, 130) == 1024);
    static_assert(StreamCapacity(512, 700) == 1024);
    static_assert(StreamCapacity(1024, 2049) == 4096);
    static_assert(StreamCapacity(std::numeric_limits<std::size_t>::max() / 2 + 1,
                                 std::numeric_limits<std::size_t>::max()) ==
                  std::numeric_limits<std::size_t>::max());
    std::size_t capacities[kStreamBufferSlots]{};
    std::size_t allocations = 0;
    const std::size_t frame_sizes[] = {100,100,100,100,130,200,330,330,330,900,
                                       900,900,300,300,300,700,700,700};
    for (std::size_t frame = 0; frame < sizeof(frame_sizes)/sizeof(*frame_sizes); ++frame) {
        const auto slot = frame % kStreamBufferSlots;
        const auto desired = StreamCapacity(capacities[slot], frame_sizes[frame]);
        assert(desired >= frame_sizes[frame]);
        if (desired != capacities[slot]) ++allocations;
        capacities[slot] = desired;
    }
    // For 18 frames on 3 buffers only initial allocation and genuine
    // capacity upgrades cause GL storage reallocation.
    assert(allocations == 6);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-ps5-gl-ring-") as d:
    file = Path(d) / "ring.cpp"
    output = Path(d) / "ring"
    file.write_text(cpp)
    subprocess.run([cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "headless/prosperoeden"), str(file),
                    "-o", str(output)], check=True)
    subprocess.run([str(output)], check=True)
print("PASS: rotating 3 renderer VBO/VAO pairs with allocation only on growth")
print("Real PS5 UI draw latency remains to be verified on hardware")
