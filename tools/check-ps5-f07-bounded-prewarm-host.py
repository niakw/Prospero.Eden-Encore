#!/usr/bin/env python3
"""Compile PS5 persistent-worker prewarm quota and token separation scenarios.

Only the file reader may be cancelled by reaching the quota. All queued jobs
must join before the borrowed state goes out of scope; actual shader workers
remain eligible for new gameplay jobs. Prevent full-cache rebuild at boot.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
main=(root/"headless/main.cpp").read_text()
shader=(root/"vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
worker=(root/"vendor/sources/eden/src/common/thread_worker.h").read_text()
begin="void PipelineCache::LoadDiskResources("
end="\nvoid PipelineCache::QueueVulkanPipelineCacheFlush()"
method=begin+shader.split(begin,1)[1].split(end,1)[0]
assert shader.count(begin)==1 and shader.count(end)==1
assert method.count("++state.total;")==2
assert method.count("if (state.total == kStartupPrewarmPipelines)")==2
assert method.count("startup_reader.request_stop();")==2
assert "constexpr size_t kStartupPrewarmPipelines = 8;" in method
assert "std::stop_source startup_reader;" in method
assert "const std::stop_token reader_token{startup_reader.get_token()};" in method
assert "VideoCommon::LoadPipelines(reader_token" in method
assert "workers.WaitForRequests(stop_loading);" in method
assert "workers.WaitForRequests(reader_token)" not in method
assert 'mode=bounded-prewarm8' in main
assert 'lazy_cache.request_stop();' not in main
assert "for (auto& thread : threads) {" in worker
assert "thread.request_stop();" in worker
for i in range(5):
    assert f"shader_source.count(f07_warm_before_{i})" in gen
assert "#include <stop_token>" in shader

cpp=r"""
#include <cassert>
#include <cstddef>
#include <stop_token>
#include <functional>
#include <vector>
constexpr std::size_t kStartupPrewarmPipelines = 8;
struct Worker {
    bool alive=true;
    size_t done=0;
    std::vector<std::function<void()>> pending;
    void QueueWork(std::function<void()> job){ assert(alive); pending.push_back(std::move(job)); }
    void WaitForRequests(std::stop_token token={}) {
        if(token.stop_requested()) alive=false;
        for(auto& work:pending){work(); ++done;}
        pending.clear();
    }
};
std::size_t Run(std::size_t persisted, Worker& workers, bool init_only=false) {
    if(init_only) return 0;  // legacy setup-only compatibility
    std::stop_source startup_reader;
    std::size_t queued=0;
    for(std::size_t i=0;i<persisted && !startup_reader.stop_requested();++i) {
        workers.QueueWork([]{});
        ++queued;
        if(queued == kStartupPrewarmPipelines)
            startup_reader.request_stop();
    }
    workers.WaitForRequests(std::stop_token{});
    assert(workers.alive); // never forward startup_reader.get_token()
    return queued;
}
int main(){
    for(auto persisted:{0u,1u,7u,8u,9u,128u,50000u}){
        Worker workers;
        auto count=Run(persisted,workers);
        assert(count==(persisted<kStartupPrewarmPipelines?persisted:kStartupPrewarmPipelines));
        assert(workers.done==count);
        // First-use compilation after prewarm must remain possible.
        workers.QueueWork([]{});
        workers.WaitForRequests();
        assert(workers.done==count+1);
        assert(Run(1, workers, true)==0);
    }
    Worker negative;
    std::stop_source canceled;
    canceled.request_stop();
    negative.WaitForRequests(canceled.get_token());
    assert(!negative.alive); // why reader token must NOT be sent to worker
}
"""
compiler=shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-prewarm-") as d:
    p=Path(d)/"test.cpp";p.write_text(cpp)
    for optimization in ("-O0","-O2"):
        exe=Path(d)/("test"+optimization[1:])
        subprocess.run([compiler,"-std=c++20",optimization,"-Wall","-Wextra","-Werror",
                        str(p),"-o",str(exe)],check=True,capture_output=True,text=True,timeout=35)
        subprocess.run([str(exe)],check=True,timeout=15)
print("F07_BOUND_PREWARM_HOST_PASS cap=8 reader_only_cancel=1 workers_persist=1 O0=1 O2=1")
