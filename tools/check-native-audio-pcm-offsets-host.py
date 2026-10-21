#!/usr/bin/env python3
"""Exercise the real native audio PCM bounds helper with sanitizer edge values."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-core/src/audio_core/renderer/voice/voice_info.cpp").read_text()
begin = "constexpr bool PcmOffsetsWithinBuffer("
assert source.count(begin) == 1
helper = begin + source.split(begin, 1)[1].split("}\n} // namespace", 1)[0] + "}"
assert source.count("!PcmOffsetsWithinBuffer(") == 2
assert "start >= 0 && end >= 0" in helper
assert "bytes / sample_bytes" in helper
assert "start_offset * byte_size" not in source
assert "end_offset * byte_size" not in source

compiler = shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "clang required"
cpp = r"""
#include <cstdint>
#include <cassert>
#include <limits>
using s32 = std::int32_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
__HELPER__
int main() {
 constexpr s32 max_s32 = std::numeric_limits<s32>::max();
 constexpr s32 min_s32 = std::numeric_limits<s32>::min();
 constexpr u64 max_u64 = std::numeric_limits<u64>::max();
 static_assert(PcmOffsetsWithinBuffer(0, 0, 0, 2));
 static_assert(PcmOffsetsWithinBuffer(2, 4, 8, 2));
 static_assert(!PcmOffsetsWithinBuffer(2, 5, 8, 2));
 static_assert(PcmOffsetsWithinBuffer(1, 2, 8, 4));
 static_assert(!PcmOffsetsWithinBuffer(3, 2, 8, 4));
 static_assert(!PcmOffsetsWithinBuffer(-1, 0, 8, 2));
 static_assert(!PcmOffsetsWithinBuffer(0, min_s32, max_u64, 4));
 static_assert(!PcmOffsetsWithinBuffer(min_s32, max_s32, max_u64, 2));
 static_assert(!PcmOffsetsWithinBuffer(0, 0, 8, 0));
 static_assert(PcmOffsetsWithinBuffer(max_s32, max_s32, max_u64, 4));
 static_assert(!PcmOffsetsWithinBuffer(max_s32, max_s32, 64, 4));
 for (s32 sample = 0; sample < 4096; ++sample) {
  for (u32 b : {2u, 4u}) {
   const u64 bytes = static_cast<u64>(sample) * b;
   assert(PcmOffsetsWithinBuffer(sample, sample, bytes, b));
   assert(!PcmOffsetsWithinBuffer(sample+1, sample, bytes, b));
  }
 }
}
""".replace("__HELPER__", helper)
with tempfile.TemporaryDirectory(prefix="encore-audio-offset-") as temp:
    d = Path(temp)
    src = d / "offset.cpp"
    exe = d / "offset"
    src.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", str(src), "-o", str(exe)],
                   check=True, timeout=90)
    subprocess.run([str(exe)], check=True, timeout=90)
print("AUDIO_PCM_OFFSETS_HOST_PASS negative=1 large=1 zero=1 max_s32=1 sanitizer=1")
