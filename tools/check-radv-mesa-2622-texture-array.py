#!/usr/bin/env python3
"""Upstream Mesa 26.2.2 RADV sampler array-layer regression, real source guard.

Port: 3261364cab95877988e0bcf767e5f68c03f35652, dated 2026-08-25.
The original pinned Mesa source is preserved; only active PS5 build file changes.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"vendor/sources/ps5-mesa/src/amd/vulkan/radv_pipeline.c"
ACTIVE=ROOT/"vendor/encore-active/ps5-mesa/src/amd/vulkan/radv_pipeline.c"
GEN=ROOT/"tools/patch-radv-wsi.py"
INSTALL=ROOT/"tools/install-vendored-radv.py"
before="""               .lower_array_layer_round_even =
                  !compiler_info->ac->conformant_trunc_coord && !compiler_info->key.disable_trunc_coord,"""
after="               .lower_array_layer_round_even = !compiler_info->ac->conformant_trunc_coord,"
source=SOURCE.read_text()
active=ACTIVE.read_text()
assert source.count(before)==1, "Unexpected upstream source pin"
assert active==source.replace(before,after), "PS5 sampler unit differs from official one-line fix"
assert before in GEN.read_text() and after in GEN.read_text()
assert "'src/amd/vulkan/radv_pipeline.c'," in INSTALL.read_text()
assert "radv_pipeline.c': [" in GEN.read_text()
# Check the boolean decision's key behavior, including the formerly broken
# disable_trunc_coord path: array layer semantics follow the hardware flag.
code=r"""
#include <assert.h>
#include <stdbool.h>
struct amdgpu_info { bool conformant_trunc_coord; };
struct compiler_key { bool disable_trunc_coord; };
struct compiler_info {
 const struct amdgpu_info *ac;
 struct compiler_key key;
};
int main(void) {
 struct amdgpu_info gpu={0};
 struct compiler_info compiler_storage={&gpu,{0}};
 struct compiler_info *compiler_info = &compiler_storage;
 bool round;
""" + "round = " + after.strip().split("=",1)[1].strip().rstrip(",") + r""";
 assert(round);
 compiler_info->key.disable_trunc_coord=true;
""" + "round = " + after.strip().split("=",1)[1].strip().rstrip(",") + r""";
 assert(round); /* older Mesa 26.2.0 incorrectly turned this false */
 gpu.conformant_trunc_coord=true;
""" + "round = " + after.strip().split("=",1)[1].strip().rstrip(",") + r""";
 assert(!round);
 return 0;
}
"""
cc=shutil.which("clang-18") or shutil.which("clang") or shutil.which("cc")
assert cc
with tempfile.TemporaryDirectory(prefix="eden-radv-texture-rounding-") as temp:
    src=Path(temp)/"check.c"
    executable=Path(temp)/"check"
    src.write_text(code)
    subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror","-O1","-fsanitize=address,undefined",str(src),"-o",str(executable)],check=True,timeout=30)
    subprocess.run([str(executable)],check=True,timeout=10)
print("PASS official Mesa 26.2.2 corrected texture layer rounding; immutable base, active compilation path")
