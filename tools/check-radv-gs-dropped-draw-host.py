#!/usr/bin/env python3
"""Check actual pinned/maintained GS dropped-draw blocks under Clang sanitizers."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
raw=(root/"vendor/sources/ps5-mesa/src/amd/vulkan/cl/radv_gs_compute.cl").read_text()
active=(root/"vendor/encore-active/ps5-mesa/src/amd/vulkan/cl/radv_gs_compute.cl").read_text()
cpu=(root/"vendor/encore-active/ps5-mesa/src/amd/vulkan/radv_cmd_buffer.c").read_text()
installer=(root/"tools/install-vendored-radv.py").read_text()
oracle=(root/"tools/patch-radv-wsi.py").read_text()
begin="   if (!ok) {\n      vertex_count = 0;\n      instance_count = 0;\n"
end="\n   poly_vertex_params_set_draw(vp"
assert raw.count(begin)==active.count(begin)==1
added="""      /* A dropped geometry draw still needs safe non-null scratch pointers. */
      vp->output_buffer = (uintptr_t)block->ro_sink;
      p->count_buffer = (global uint *)block->ro_sink;
      p->output_index_buffer = (global uint *)block->ro_sink;
"""
assert active==raw.replace(begin,begin+added)
def block(s):
    return begin+s.split(begin,1)[1].split(end,1)[0]
anchor="   poly_vertex_params_init(vp, gsc->vs_outputs, wg_size);\n   poly_geometry_params_init(gp, mode, wg_size);\n"
assert cpu.count(anchor)==1
init=cpu.split(anchor,1)[1].split("   /* Primitives generated",1)[0]
assert "const uint64_t null_sink = radv_gs_compute_upload(cmd_buffer, 256, NULL, NULL);" in init
for f in ("vp->output_buffer", "vp->index_buffer", "gp->count_buffer", "gp->output_index_buffer"):
    assert init.count(f+" = null_sink;")==1
assert "src/amd/vulkan/cl/radv_gs_compute.cl" in installer
assert "src/amd/vulkan/cl/radv_gs_compute.cl" in oracle
cpp=r"""
#include <cstdint>
#include <cassert>
using uint=unsigned int;
#define global
struct Vertex{std::uintptr_t output_buffer{};};
struct Geometry{uint *count_buffer{},*output_index_buffer{};};
struct Draw{std::uintptr_t ro_sink{0x1000};};
int main(){
    Vertex v{};Geometry g{};Draw d{};
    auto* vp=&v;auto* p=&g;auto* block=&d;
    bool ok=false;
    uint vertex_count=10,instance_count=3;
    __BLOCK__
    assert(vertex_count==0 && instance_count==0);
#ifdef LEGACY
    assert(v.output_buffer==0 && g.count_buffer==nullptr && g.output_index_buffer==nullptr);
#else
    assert(v.output_buffer==0x1000);
    assert(reinterpret_cast<std::uintptr_t>(g.count_buffer)==0x1000);
    assert(reinterpret_cast<std::uintptr_t>(g.output_index_buffer)==0x1000);
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler,"Clang required"
with tempfile.TemporaryDirectory(prefix="encore-gs-sink-") as directory:
    for label,text,flag in (("pinned",raw,["-DLEGACY"]),("guarded",active,[])):
        source=Path(directory)/(label+".cpp")
        binary=Path(directory)/label
        source.write_text(cpp.replace("__BLOCK__",block(text)))
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        *flag,str(source),"-o",str(binary)],check=True,timeout=45)
        subprocess.run([str(binary)],check=True,timeout=30)
print("RADV_GS_DROPPED_DRAW_HOST_PASS pinned_null=1 guarded_sink=1 cpu_init=1")
