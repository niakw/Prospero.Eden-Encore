#!/usr/bin/env python3
"""Prove source-backed DrawTexture invalidations happen before texture locks."""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
pinned=(root/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
memory=(root/"vendor/sources/eden/src/video_core/memory_manager.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
workflow=(root/".github/workflows/encore-core-preflight.yml").read_text()
start="void RasterizerVulkan::DrawTexture() {"
end="void RasterizerVulkan::Clear("
draw=active.split(start,1)[1].split(end,1)[0]
upstream=pinned.split(start,1)[1].split(end,1)[0]
assert "gpu_memory->FlushCaching();" not in upstream
assert draw.count("gpu_memory->FlushCaching();")==1
flush=draw.index("    FlushWork();")
drain=draw.index("    gpu_memory->FlushCaching();")
lock=draw.index("    std::scoped_lock l{texture_cache.mutex};")
descriptors=draw.index("    texture_cache.SynchronizeDescriptors(false);")
targets=draw.index("    texture_cache.UpdateRenderTargets(false);")
assert flush < drain < lock < descriptors < targets
inner=active.split("void RasterizerVulkan::InnerInvalidation(",1)[1]
assert "std::scoped_lock lock{texture_cache.mutex};" in inner
assert "texture_cache.WriteMemory(addr, size);" in inner
assert "rasterizer->InnerInvalidation(" in memory.split("void MemoryManager::FlushCaching()",1)[1].split("\n}",1)[0]
assert "accumulator.InvalidateAll(" in memory.split("void MemoryManager::FlushCaching()",1)[1].split("\n}",1)[0]

gen=ast.parse(generator)
pairs=[]
for node in ast.walk(gen):
    if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
        and node.func.id=="adapt" and len(node.args)>=3
        and isinstance(node.args[0],ast.Constant)
        and node.args[0].value=="src/video_core/renderer_vulkan/vk_rasterizer.cpp"):
        for el in node.args[2].elts:
            try: pair=ast.literal_eval(el)
            except (TypeError,SyntaxError,ValueError): continue
            if isinstance(pair,tuple) and len(pair)==2: pairs.append(pair)
matching=[(old,new) for old,new in pairs
          if "texture_cache.SynchronizeDescriptors(false);" in old
          and "gpu_memory->FlushCaching();" in new]
assert len(matching)==1
before,after=matching[0]
assert upstream.count(before)==1 and draw.count(after)==1
assert after in draw
assert "python3 -B tools/check-ps5-draw-texture-guest-invalidation-host.py" in workflow

# Execute the actual DrawTexture pre-lock call sequence. The fake memory
# manager sends a queued invalidation through the texture-cache mutex,
# proving that a late call would violate lock ownership.
body=draw[flush:targets+len("    texture_cache.UpdateRenderTargets(false);")]
cpp=r"""
#include <cassert>
#include <mutex>
struct TextureCache {
    std::mutex mutex;
    bool invalidated=false;
    unsigned syncs=0,targets=0;
    void WriteMemory(){invalidated=true;}
    void SynchronizeDescriptors(bool){assert(invalidated);++syncs;}
    void UpdateRenderTargets(bool){assert(invalidated);++targets;}
};
struct RasterizerVulkan;
struct MemoryManager {
    RasterizerVulkan* rasterizer{};
    bool queued=true;
    unsigned flushes=0;
    void FlushCaching();
};
struct RasterizerVulkan {
    TextureCache texture_cache;
    MemoryManager* gpu_memory{};
    unsigned works=0;
    void FlushWork(){++works;}
    void InnerInvalidation(){std::scoped_lock lock{texture_cache.mutex};
        texture_cache.WriteMemory();}
    void DrawTexturePreLock(){
__BODY__
    }
};
void MemoryManager::FlushCaching() {
    ++flushes;
    if (queued) {
        rasterizer->InnerInvalidation();
        queued=false;
    }
}
int main(){
    RasterizerVulkan r;
    MemoryManager m{&r};
    r.gpu_memory=&m;
    r.DrawTexturePreLock();
    assert(r.texture_cache.invalidated);
    assert(m.flushes==1 && !m.queued && r.works==1);
    assert(r.texture_cache.syncs==1 && r.texture_cache.targets==1);
    // No pending invalidations: calling FlushCaching again must still
    // be safe before taking the texture mutex.
    r.DrawTexturePreLock();
    assert(m.flushes==2 && r.works==2 && r.texture_cache.syncs==2);
}
""".replace("__BODY__",body)
clang=shutil.which("clang++-18") or shutil.which("clang++")
assert clang,"Clang required"
with tempfile.TemporaryDirectory(prefix="encore-draw-texture-invalidation-") as tmp:
    source=Path(tmp)/"test.cpp"; binary=Path(tmp)/"test"
    source.write_text(cpp)
    subprocess.run([clang,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(source),"-o",str(binary)],check=True,timeout=45)
    subprocess.run([str(binary)],check=True,timeout=30)
print("DRAW_TEXTURE_GUEST_INVALIDATION_HOST_PASS drain_before_mutex=1 cache_synced=2 generator_parity=1")
