#!/usr/bin/env python3
"""Replay the actual Vulkan readback staging guard in native/desktop builds."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
start=src.index("StagingBufferRef TextureCacheRuntime::DownloadStagingBuffer(size_t size, bool deferred) {")
end=src.index("\n\nvoid TextureCacheRuntime::FreeDeferredStagingBuffer(",start)
method=src[start:end]
assert "F07 reject invalid Vulkan guest readback staging in runtime" in gen
assert "if (!map.buffer || map.mapped_span.size_bytes() < size)" in method
assert "if (deferred && map.buffer) staging_buffer_pool.FreeDeferred(map);" in method
assert "throw std::bad_alloc{};" in method
for flow in (".github/workflows/encore-core-fast-gate.yml",".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-download-staging-runtime-host.py" in (root/flow).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <new>
#include <span>
#include <vector>
enum class MemoryUsage {Download};
struct StagingBufferRef {
    std::uintptr_t buffer{};
    std::span<std::uint8_t> mapped_span{};
};
struct Pool {
    bool null_buffer{}, short_map{}, fail_request{};
    int releases{};
    std::vector<std::uint8_t> backing;
    StagingBufferRef Request(std::size_t count,MemoryUsage usage,bool deferred) {
        assert(usage==MemoryUsage::Download);
        (void)deferred;
        if(fail_request)throw std::bad_alloc{};
        backing.resize(count);
        return {null_buffer ? 0u : 1u,
                {backing.data(),count-(short_map && count ? 1u : 0u)}};
    }
    void FreeDeferred(StagingBufferRef& ref) {
        assert(ref.buffer);
        ++releases;
    }
};
struct TextureCacheRuntime {
    Pool staging_buffer_pool;
    StagingBufferRef DownloadStagingBuffer(std::size_t size,bool deferred);
};
__METHOD__
int main() {
    TextureCacheRuntime good;
    auto map=good.DownloadStagingBuffer(256,false);
    assert(map.buffer && map.mapped_span.size()==256);
    TextureCacheRuntime null_map;
    null_map.staging_buffer_pool.null_buffer=true;
    bool threw=false;
    try{(void)null_map.DownloadStagingBuffer(256,true);}catch(const std::bad_alloc&){threw=true;}
#ifdef PS5_NATIVE
    assert(threw && null_map.staging_buffer_pool.releases==0);
#else
    assert(!threw && null_map.staging_buffer_pool.releases==0);
#endif
    TextureCacheRuntime short_deferred;
    short_deferred.staging_buffer_pool.short_map=true;
    threw=false;
    try{(void)short_deferred.DownloadStagingBuffer(256,true);}catch(const std::bad_alloc&){threw=true;}
#ifdef PS5_NATIVE
    assert(threw && short_deferred.staging_buffer_pool.releases==1);
#else
    assert(!threw && short_deferred.staging_buffer_pool.releases==0);
#endif
    TextureCacheRuntime short_immediate;
    short_immediate.staging_buffer_pool.short_map=true;
    threw=false;
    try{(void)short_immediate.DownloadStagingBuffer(256,false);}catch(const std::bad_alloc&){threw=true;}
#ifdef PS5_NATIVE
    assert(threw && short_immediate.staging_buffer_pool.releases==0);
#else
    assert(!threw && short_immediate.staging_buffer_pool.releases==0);
#endif
    TextureCacheRuntime failed;
    failed.staging_buffer_pool.fail_request=true;
    threw=false;
    try{(void)failed.DownloadStagingBuffer(256,true);}catch(const std::bad_alloc&){threw=true;}
    assert(threw && failed.staging_buffer_pool.releases==0);
}
""".replace("__METHOD__",method)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"No C++20 compiler"
with tempfile.TemporaryDirectory(prefix="eden-f07-runtime-staging-") as directory:
    source=Path(directory)/"test.cpp"
    source.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(directory)/("test"+("native" if native else "desktop")+opt[1:])
            flags=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined","-fno-sanitize-recover=all"]
            if native:flags.append("-DPS5_NATIVE=1")
            build=subprocess.run([*flags,str(source),"-o",str(exe)],capture_output=True,text=True,timeout=50)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert result.returncode==0,(native,opt,result.stderr[-4000:])
print("F07_READBACK_STAGING_RUNTIME_PASS native_desktop_O0_O2")
