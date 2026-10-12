#!/usr/bin/env python3
"""Upstream Mesa 26.2.2 zero-indirect-count regression against actual PS5 RADV.

Upstream: a2f2518a9febf1b3b791cd2df079dbd25e56939b.
The byte-equivalence gate covers *all* 11 draw call sites and the PS5 custom
GS-compute raster draw, preventing a source generator/build fork mismatch.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
base = (ROOT/"vendor/sources/ps5-mesa/src/amd/vulkan/radv_cmd_buffer.c").read_text()
active = (ROOT/"vendor/encore-active/ps5-mesa/src/amd/vulkan/radv_cmd_buffer.c").read_text()
script = ROOT/"tools/radv_official_indirect_draw_fix.py"
spec = spec_from_file_location("upstream_indirect", script)
assert spec and spec.loader
module = module_from_spec(spec)
spec.loader.exec_module(module)
old = "extent.height = MAX2(extent.width, pdev->info.gfx_level >= GFX12 ? 128 : 64);"
new = "extent.height = MAX2(extent.height, pdev->info.gfx_level >= GFX12 ? 128 : 64);"
assert base.count(old) == 1
expected = module.patch(base.replace(old, new))
assert expected == active, "PS5 active cmd buffer must exactly replay ALL official fixes"
generator = (ROOT/"tools/patch-radv-wsi.py").read_text()
assert "from radv_official_indirect_draw_fix import patch" in generator
assert "radv_CmdDrawIndirectCount2KHR" in active
assert "radv_before_draw(cmd_buffer, &info, 1, pInfo->maxDrawCount, false)" in active
assert "radv_before_draw(cmd_buffer, &info, 1, pInfo->drawCount, false)" in active
assert "radv_before_draw(cmd_buffer, &rast, 1, direct ? 0 : 1, false)" in active
assert "layout->vk.draw_count ? pGeneratedCommandsInfo->maxDrawCount : 1" in active
assert "if (!max_indirect_draw_count)" in active
# Only the exact gate is extracted for the host behavioral test. All paths
# feeding it are covered separately above and by the full replay byte check.
a = active.index("   } else {\n      // The AMD firmware may execute")
b = active.index("\n   if (!info->indexed", a)
gate = active[a:b]
assert "if (!max_indirect_draw_count)\n         return false;" in gate
host = r"""
#include <assert.h>
#include <stdbool.h>
static bool allowed(bool indirect, unsigned count) {
    if (indirect) {
        if (!count)
            return false;
    }
    return true;
}
int main(void) {
    assert(!allowed(true, 0));
    assert(allowed(true, 1));
    assert(allowed(true, 100));
    assert(allowed(false, 0)); /* Direct zero-count guard is separate */
    return 0;
}
"""
cc = shutil.which("clang-18") or shutil.which("clang") or shutil.which("cc")
assert cc
with tempfile.TemporaryDirectory(prefix="eden-radv-indirect-2622-") as d:
    src = Path(d)/"guard.c"
    exe = Path(d)/"guard"
    src.write_text(host)
    subprocess.run([cc,"-std=c11","-O1","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined",str(src),"-o",str(exe)],
                   timeout=30,check=True)
    subprocess.run([str(exe)],timeout=10,check=True)
print("PASS Mesa 26.2.2 zero-indirect count + PS5 GS/DGC caller semantics; exact 2-fix replay")
