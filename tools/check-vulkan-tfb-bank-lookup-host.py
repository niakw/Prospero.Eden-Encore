#!/usr/bin/env python3
"""Actual TFB SyncWrites: pinned map, hash work, unchanged bank dispatch and flags."""
from pathlib import Path
import ast
import hashlib
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
active=ROOT/'vendor/encore-active/eden-vulkan'
tree=ast.parse((ROOT/'tools/prepare-vulkan-port.py').read_text())
edits=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
           and any(isinstance(t,ast.Name) and t.id=='tfb_sync_edits' for t in n.targets))
current=(active/'vulkan_query_cache.cpp').read_text()
previous=current
# Retain the earlier full-file oracle after the explicit samples scratch delta.
recycle_edits=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=='samples_recycle_edits' for t in n.targets))
for old,new in reversed(recycle_edits):
    assert previous.count(new)==1
    previous=previous.replace(new,old)
for old,new in reversed(edits):
    assert previous.count(new)==1
    previous=previous.replace(new,old)
blob=previous.encode()
assert hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()=='7a1857c575b5d197c94c533086f9e8a2c73ac731'
def method(source):
    start=source.index('    void SyncWrites() override {',source.index('class TFBCounterStreamer :'))
    end=source.index('\n    size_t WriteCounter(',start)
    body=source[start:end]
    # The real pinned Common map, with only its hasher instrumented. Same hash values.
    anchor='::Common::unordered_map<size_t, std::vector<HostSyncValues>>'
    assert body.count(anchor)==1
    return body.replace(anchor,'::Common::unordered_map<size_t, std::vector<HostSyncValues>, CountingHash>')
start=current.index('struct HostSyncValues {')
value=current[start:current.index('\n};',start)+3]
cpp=r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <span>
#include <vector>
#include "common/container/unordered_map.h"
using DAddr=std::uint64_t;
std::size_t hash_calls;
struct CountingHash { std::size_t operator()(std::size_t key) const {++hash_calls;return std::hash<std::size_t>{}(key);} };
HOSTVALUE
namespace VideoCommon {
enum QueryFlagBits:unsigned {IsRewritten=1,IsInvalidated=2,IsHostSynced=4};
struct Query {std::size_t start_bank_id,start_slot;DAddr guest_address;unsigned flags;};
}
bool True(unsigned value){return value!=0;}
struct TFBQueryBank {static constexpr std::size_t QUERY_SIZE=4;};
struct Event {std::size_t bank;std::vector<std::array<std::uint64_t,3>> values;bool operator==(const Event&)const=default;};
struct Runtime {
    std::vector<Event> events;
    template<class T> void SyncValues(const std::vector<T>& values,std::size_t bank) {
        Event event{bank,{}};
        for(const auto& v:values)event.values.push_back({v.address,v.size,v.offset});
        events.push_back(std::move(event));
    }
};
struct Bank {std::size_t index;std::size_t GetBuffer()const{return index+1000;}};
struct Pool {std::vector<Bank> banks;Bank& GetBank(std::size_t index){return banks.at(index);}};
struct Base {virtual ~Base()=default;virtual void SyncWrites()=0;};
struct State:Base {
    Runtime runtime;Pool bank_pool;
    std::vector<VideoCommon::Query> queries;
    std::vector<std::size_t> pending_sync,visited;
    unsigned closes{};
    void CloseCounter(){++closes;}
    VideoCommon::Query* GetQuery(std::size_t index){visited.push_back(index);return &queries.at(index);}
};
namespace Before {struct Stream:State { BEFORE };}
namespace After {struct Stream:State { AFTER };}
void Run(std::size_t count,std::size_t banks,bool filtered) {
    Before::Stream before;After::Stream after;
    std::size_t accepted{};
    for(std::size_t i=0;i<banks;++i){before.bank_pool.banks.push_back({i});after.bank_pool.banks.push_back({i});}
    for(std::size_t i=0;i<count;++i) {
        unsigned flags=filtered?(i%5==0?VideoCommon::IsRewritten:i%3==0?VideoCommon::IsInvalidated:0u):0u;
        before.queries.push_back({(i*13+7)%banks,i%2048,0x100000+i*16,flags});
        before.pending_sync.push_back(i);
        if(!flags)++accepted;
    }
    std::reverse(before.pending_sync.begin(),before.pending_sync.end());
    after.queries=before.queries;after.pending_sync=before.pending_sync;
    hash_calls=0;before.SyncWrites();const auto old_calls=hash_calls;
    hash_calls=0;after.SyncWrites();const auto new_calls=hash_calls;
    assert(old_calls==new_calls+accepted);
    assert(before.runtime.events==after.runtime.events && before.visited==after.visited);
    assert(before.closes==1 && after.closes==1 && before.pending_sync.empty() && after.pending_sync.empty());
    for(std::size_t i=0;i<count;++i) {
        assert(before.queries[i].flags==after.queries[i].flags);
        assert(bool(after.queries[i].flags&VideoCommon::IsHostSynced)==!(after.queries[i].flags&(VideoCommon::IsRewritten|VideoCommon::IsInvalidated)));
    }
    // Empty repeated sync must still close the counter without dispatching stale values.
    const auto dispatched=after.runtime.events.size();after.SyncWrites();
    assert(after.closes==2 && after.runtime.events.size()==dispatched);
    std::printf("TFB_BANK_LOOKUP queries=%zu banks=%zu filtered=%u accepted=%zu hash_calls=%zu->%zu\n",count,banks,filtered,accepted,old_calls,new_calls);
}
int main(){
    Run(0,1,false);
    for(auto [queries,banks]:std::array<std::pair<std::size_t,std::size_t>,3>{{{1024,1},{1024,32},{2048,1024}}})
        for(bool filtered:{false,true})Run(queries,banks,filtered);
    std::puts("TFB_BANK_LOOKUP_PASS actual_Boost_flat_map=1 bank_order_payload_flags=identical invalidated_rewritten=preserved empty_close=preserved sanitizers=ASan,UBSan");
}
'''.replace('HOSTVALUE',value).replace('BEFORE',method(previous)).replace('AFTER',method(current))
compiler=shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
includes=['-I'+str(p) for p in sorted((ROOT/'vendor/sources/eden-cpm/boost/boost-1.90.0').glob('libs/*/include'))]
includes+=['-I'+str(ROOT/'vendor/sources/eden/src')]
with tempfile.TemporaryDirectory(prefix='encore-tfb-lookup-') as temp:
    source,binary=Path(temp)/'main.cpp',Path(temp)/'tfb';source.write_text(cpp)
    command=[compiler,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',*includes,str(source),'-o',str(binary)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    if result.returncode:raise SystemExit(result.stdout+result.stderr)
    subprocess.run([str(binary)],check=True,timeout=20)
print('TFB_BANK_LOOKUP_HOST_ONLY GPU_progress_and_PS5_frametimes=unverified')
