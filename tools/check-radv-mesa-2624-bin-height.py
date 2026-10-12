#!/usr/bin/env python3
"""Test the actual Mesa 26.2.4 GFX10-11.7 bin-height bugfix in our PS5 RADV.

Upstream 1f4f4aeee9db552e2955db77ee5584aa729b0644 (2026-09-21).
The old line copied the *width* into the height calculation.
This host test exercises the two corrected production assignment lines.
"""
from pathlib import Path
import subprocess
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "vendor/encore-active/ps5-mesa/src/amd/vulkan/radv_cmd_buffer.c"
BASE = ROOT / "vendor/sources/ps5-mesa/src/amd/vulkan/radv_cmd_buffer.c"
GENERATOR = ROOT / "tools/patch-radv-wsi.py"
s = ACTIVE.read_text()
original = BASE.read_text()
oracle = GENERATOR.read_text()
old = "extent.height = MAX2(extent.width, pdev->info.gfx_level >= GFX12 ? 128 : 64);"
new = "extent.height = MAX2(extent.height, pdev->info.gfx_level >= GFX12 ? 128 : 64);"
assert original.count(old) == 1, "Unexpected pinned input - do not blindly patch"
assert s.count(new) == 1 and old not in s, "Production native RADV regression"
assert old in oracle and new in oracle
start = s.index("   extent.width = MAX2(extent.width, 128);")
end = s.index("\n   if (pdev->info.gfx_level >= GFX12)", start)
production_lines = s[start:end].strip()
assert production_lines.count("MAX2(") == 2, "Unexpected source section"
assert new in production_lines

fixture = """
#include <assert.h>
#include <stdint.h>
typedef struct { uint32_t width, height; } VkExtent2D;
struct {struct {unsigned gfx_level;} info;} physical;
#define pdev (&physical)
#define GFX12 12
#define MAX2(a,b) ((a) > (b) ? (a) : (b))
static VkExtent2D check(uint32_t width,uint32_t height,unsigned gfx) {
    physical.info.gfx_level=gfx;
    VkExtent2D extent={width,height};
""" + production_lines + """
    return extent;
}
int main(void) {
    VkExtent2D a=check(128,256,10); assert(a.width==128&&a.height==256);
    VkExtent2D b=check(1024,4,10); assert(b.width==1024&&b.height==64);
    VkExtent2D c=check(16,2,12); assert(c.width==128&&c.height==128);
    VkExtent2D d=check(320,200,11); assert(d.width==320&&d.height==200);
    return 0;
}
"""
cc = shutil.which("clang-18") or shutil.which("clang") or shutil.which("cc")
assert cc
with tempfile.TemporaryDirectory(prefix="eden-mesa-2624-bin-") as t:
    file = Path(t) / "test.c"
    binary = Path(t) / "bin_height"
    file.write_text(fixture)
    subprocess.run([cc, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(file), "-o", str(binary)],
                   check=True, timeout=30)
    subprocess.run([str(binary)], check=True, timeout=10)
print("PASS Mesa official 26.2.4 GFX10/GFX11 corrected bin-height on active PS5 RADV")
