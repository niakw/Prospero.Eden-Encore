#!/usr/bin/env python3
"""C++20 sanitizer regression for actual maintained merged vertex identity."""
import ast
from pathlib import Path
import subprocess
import shutil
import tempfile

root = Path(__file__).resolve().parents[1]
active = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
header = (root / "headless/dev_vulkan.h").read_text()
shader_costs = None
for node in ast.parse(generator).body:
    if isinstance(node, ast.Assign) and any(
        isinstance(name, ast.Name) and name.id == "shader_costs"
        for name in node.targets
    ):
        shader_costs = ast.literal_eval(node.value)
        break
assert shader_costs is not None
fragment = next(new for old, new in shader_costs
                if old == "GraphicsPipeline* PipelineCache::CurrentGraphicsPipeline() {")
start = "std::mutex eden_attributeless_mutex;"
end = "// A static key without attributes"
helper = active.split(start, 1)[1].split(end, 1)[0]
generated_helper = fragment.split(start, 1)[1].split(end, 1)[0]
assert helper == generated_helper
assert "using EdenVertexIdentity = std::array<u64, 2>;" in helper
assert "std::set<EdenVertexIdentity> eden_attributeless_vertex" in helper
assert "EdenResetStaticVertexInputBinding() noexcept" in helper
assert "std::array<Lookup, 64> lookups{}" in helper
assert "lookup.generation == generation && lookup.hash == vertex_hash" in helper
for text in (active, generator):
    assert "EdenAttributeless({graphics_key.unique_hashes[0], graphics_key.unique_hashes[1]})" in text
    assert "EdenRecordAttributeless({key.unique_hashes[0], key.unique_hashes[1]}, programs[1].info)" in text
    assert "EdenResetStaticVertexInputBinding();" in text
assert "static_vertex_input = true;" in header.split("inline void ResetForTitle() noexcept {", 1)[1]
compiler = shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "clang++ required"
cpp = r"""
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <set>
#include "dev_vulkan.h"
using u64=std::uint64_t; using u32=std::uint32_t;
namespace Shader {
namespace IR { constexpr std::size_t NUM_GENERICS=32; }
struct Info {
 struct Loads {
   u32 bits{};
   bool Generic(std::size_t i) const { return bool(bits & (u32{1} << i)); }
 } loads;
};
}
__EXACT_HELPER__
int main() {
 Shader::Info without{}, with{};
 with.loads.bits=1;
 EdenRecordAttributeless({0x10,0x55}, without);
 assert(EdenAttributeless({0x10,0x55}));
 assert(!EdenAttributeless({0x20,0x55}));
 EdenRecordAttributeless({0x20,0x55}, with);
 assert(!EdenAttributeless({0x20,0x55}));
 assert(EdenAttributeless({0x10,0x55}));
 EdenRecordAttributeless({0x30,0x55}, without);
 assert(EdenAttributeless({0x30,0x55}));
 assert(!EdenAttributeless({0x20,0x55}));
 assert(!EdenAttributeless({0x30,0x56}));
 // A memoized negative answer must turn positive after a worker publishes it.
 assert(!EdenAttributeless({0x70,0x88}));
 EdenRecordAttributeless({0x70,0x88}, without);
 assert(EdenAttributeless({0x70,0x88}));
 // Deliberate 64-slot collisions must never reuse a different shader result.
 for(u64 i=0;i<256;++i) {
   const u64 key=0x1000+i*64;
   if((i & 1)==0) EdenRecordAttributeless({key,0x55}, without);
   assert(EdenAttributeless({key,0x55})==((i&1)==0));
 }
 for(u64 i=0;i<256;++i) {
   const u64 key=0x1000+i*64;
   assert(EdenAttributeless({key,0x55})==((i&1)==0));
 }
 eden_static_vertex_input_bound=true;
 EdenResetStaticVertexInputBinding();
 assert(!eden_static_vertex_input_bound);
 Eden::DevVulkan::static_vertex_input=false;
 Eden::DevVulkan::ResetForTitle();
 assert(Eden::DevVulkan::static_vertex_input);
}
""".replace("__EXACT_HELPER__", start + helper)
with tempfile.TemporaryDirectory(prefix="encore-vertex-identity-") as folder:
    path = Path(folder)
    src = path / "identity.cpp"
    exe = path / "identity"
    src.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-pthread","-Wall",
                    "-Wextra","-Werror","-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all","-I",str(root/"headless"),
                    str(src),"-o",str(exe)],check=True,timeout=45)
    subprocess.run([str(exe)],check=True,timeout=30)
print("VERTEX_IDENTITY_HOST_PASS pair=1 shared_second_hash=1 title_reset=1 generator_parity=1")
