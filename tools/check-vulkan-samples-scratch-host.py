#!/usr/bin/env python3
"""Real samples staging/clear fragments and full SyncWrites; reusable vector ownership."""
from pathlib import Path
import ast
import hashlib
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp').read_text()
tree=ast.parse((ROOT/'tools/prepare-vulkan-port.py').read_text())
edits=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
           and any(isinstance(t,ast.Name) and t.id=='samples_recycle_edits' for t in n.targets))
previous=source
for old,new in reversed(edits):
    assert previous.count(new)==1,new
    previous=previous.replace(new,old)
b=previous.encode()
assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()=='92eee0bfba39615b3620c7bce99dc686e731627c'
def fixture(text,current):
    text=text[text.index('class SamplesStreamer :'):text.index('class TFBQueryBank :')]
    sync=text[text.index('    void SyncWrites() override {'):text.index('    void PresyncWrites() override {')]
    start=text.index('    void PresyncWrites() override {')+len('    void PresyncWrites() override {')
    prefix=text[start:text.index('        ::Common::unordered_map<size_t, std::pair<size_t, size_t>> offsets;',start)]
    start=text.index('        // Convert queries')
    convert=text[start:text.index('\n        if (has_multi_queries) {',start)]
    fields='    std::deque<std::vector<HostSyncValues>> sync_values_stash;\n'
    helper=''
    if current:
        fields+='    std::array<std::vector<HostSyncValues>, 2> sync_values_cache;\n'
        start=text.index('    void RecycleSyncValues() {')
        helper=text[start:text.index('    template <typename Func>',start)]
    return fields+helper+sync+'    void StageMetadata() {'+prefix+convert+'\n        pending_sync.clear();\n    }\n'
start=source.index('struct HostSyncValues {');value=source[start:source.index('\n};',start)+3]
cpp=r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <new>
#include <unordered_map>
#include <utility>
#include <vector>
using DAddr=std::uint64_t;using size_t=std::size_t;
#define ASSERT(x) assert(x)
unsigned allocations;
void* operator new(std::size_t n){++allocations;if(void* p=std::malloc(n))return p;throw std::bad_alloc{};}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete(void* p,std::size_t)noexcept{std::free(p);}
HOSTVALUE
namespace VideoCommon {enum QueryFlagBits:unsigned{IsRewritten=1,IsInvalidated=2,IsHostSynced=4};}
bool True(unsigned value){return value!=0;}
constexpr unsigned VK_DRIVER_ID_QUALCOMM_PROPRIETARY=1,VK_DRIVER_ID_ARM_PROPRIETARY=2,VK_DRIVER_ID_MESA_TURNIP=3;
struct Device{unsigned id{};unsigned GetDriverID()const{return id;}};
struct SamplesQueryBank{static constexpr size_t QUERY_SIZE=8;};
struct Query{size_t size_slots,start_bank_id,start_slot;DAddr guest_address;unsigned flags;};
struct Output{DAddr buffer{};std::vector<HostSyncValues> values;};
struct Runtime{
    std::array<Output,2> outputs;size_t count{};
    Runtime(){for(auto& o:outputs)o.values.reserve(1024);}
    template<class T>void SyncValues(const std::vector<T>& values,DAddr buffer){auto& o=outputs.at(count++);o.buffer=buffer;o.values.assign(values.begin(),values.end());}
};
struct State{
    virtual ~State()=default;virtual void SyncWrites()=0;
    Device device;Runtime runtime;unsigned pauses{};
    size_t num_slots_used=1024;bool accumulation_since_last_sync{};
    std::array<DAddr,2> handles{400,800};std::array<DAddr*,2> buffers{&handles[0],&handles[1]};
    std::array<size_t,2> resolve_buffers{0,1};
    std::vector<Query> queries;std::vector<size_t> pending_sync;
    std::unordered_map<size_t,std::pair<size_t,size_t>> offsets;
    State(){for(size_t i=0;i<8;++i)offsets.emplace(i,std::pair<size_t,size_t>{0,i*8192});}
    Query* GetQuery(size_t i){return &queries.at(i);}
    void PauseCounter(){++pauses;}
    void Fill(size_t n,bool multi){queries.clear();pending_sync.clear();for(size_t i=0;i<n;++i){queries.push_back({multi&&i%2?2u:1u,i%8,i%64,0x10000+i*8,unsigned(i%11==0?VideoCommon::IsInvalidated:i%13==0?VideoCommon::IsRewritten:0)});pending_sync.push_back(i);}runtime.count=0;}
};
struct Before:State{ BEFORE };
struct After:State{ AFTER };
void Equal(const Before& a,const After& b){
    assert(a.pauses==b.pauses && a.pending_sync==b.pending_sync && a.runtime.count==b.runtime.count);
    for(size_t i=0;i<a.runtime.count;++i){const auto& x=a.runtime.outputs[i];const auto& y=b.runtime.outputs[i];assert(x.buffer==y.buffer && x.values.size()==y.values.size());for(size_t j=0;j<x.values.size();++j){assert(x.values[j].address==y.values[j].address && x.values[j].size==y.values[j].size && x.values[j].offset==y.values[j].offset);}}
    assert(a.queries.size()==b.queries.size());for(size_t i=0;i<a.queries.size();++i)assert(a.queries[i].flags==b.queries[i].flags);
}
int main(){
    Before old;After now;
    old.Fill(512,true);now.Fill(512,true);old.StageMetadata();now.StageMetadata();old.SyncWrites();now.SyncWrites();Equal(old,now);
    unsigned old_alloc{},new_alloc{};
    for(unsigned cycle=0;cycle<128;++cycle){
        const size_t size=64*(1+cycle%8);const bool multi=cycle%3!=0;
        old.Fill(size,multi);now.Fill(size,multi);
        allocations=0;old.StageMetadata();old.SyncWrites();old_alloc+=allocations;
        allocations=0;now.StageMetadata();now.SyncWrites();new_alloc+=allocations;
        Equal(old,now);
        old.runtime.count=now.runtime.count=0;old.SyncWrites();now.SyncWrites();Equal(old,now);assert(now.runtime.count==0);
    }
    assert(old_alloc>128 && new_alloc==0);
    // Replacing an unconsumed batch discards the first metadata, as before.
    old.Fill(512,true);now.Fill(512,true);old.StageMetadata();now.StageMetadata();
    old.Fill(64,false);now.Fill(64,false);old.StageMetadata();now.StageMetadata();old.SyncWrites();now.SyncWrites();Equal(old,now);
    // Empty Presync leaves the staged batch for SyncWrites.
    old.Fill(256,true);now.Fill(256,true);old.StageMetadata();now.StageMetadata();old.StageMetadata();now.StageMetadata();old.SyncWrites();now.SyncWrites();Equal(old,now);
    for(unsigned driver:{1u,2u,3u}){
        old.Fill(128,true);now.Fill(128,true);old.StageMetadata();now.StageMetadata();
        old.Fill(64,false);now.Fill(64,false);old.device.id=now.device.id=driver;old.StageMetadata();now.StageMetadata();old.SyncWrites();now.SyncWrites();Equal(old,now);assert(now.runtime.count==0);
        old.device.id=now.device.id=0;
    }
    now.Fill(512,true);allocations=0;now.StageMetadata();now.SyncWrites();assert(allocations==0);
    std::printf("SAMPLES_SCRATCH_PASS batches=128 allocations=%u->%u metadata_order_flags=identical empty_repeat_overwrite_excluded_drivers=preserved ASan_UBSan=1\n",old_alloc,new_alloc);
}
'''.replace('HOSTVALUE',value).replace('BEFORE',fixture(previous,False)).replace('AFTER',fixture(source,True))
compiler=shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++');assert compiler
with tempfile.TemporaryDirectory(prefix='encore-samples-scratch-') as temp:
    unit,binary=Path(temp)/'main.cpp',Path(temp)/'samples';unit.write_text(cpp)
    result=subprocess.run([compiler,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(unit),'-o',str(binary)],capture_output=True,text=True,timeout=60)
    if result.returncode:raise SystemExit(result.stdout+result.stderr)
    subprocess.run([str(binary)],check=True,timeout=30)
print('SAMPLES_SCRATCH_HOST_ONLY metadata_fragments_and_full_SyncWrites; real_GPU_progress_and_PS5_frame_times=unverified')
