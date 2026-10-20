#!/usr/bin/env python3
"""Real AppendBuffer + PCM ring: stable samples, one publication, warm allocation cost."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'vendor/encore-active/eden-core/src/audio_core/sink/sink_stream.cpp').read_text()
start=source.index('void SinkStream::AppendBuffer(')
current=source[start:source.index('\nstd::vector<s16> SinkStream::ReleaseBuffer',start)]
old='        std::vector<s16> new_samples(samples.size() / system_channels * device_channels);'
new='''        // AppendBuffer does not call back into producers. Reuse this thread's
        // expansion storage across streams while preserving one PCM publication.
        thread_local std::vector<s16> new_samples;
        new_samples.assign(samples.size() / system_channels * device_channels, 0);'''
assert current.count(new)==1
previous=current.replace(new,old)
ring=(ROOT/'vendor/sources/eden/src/common/ring_buffer.h').read_text()
push='    std::size_t Push(const void* new_slots, std::size_t slot_count) {'
assert ring.count(push)==1
ring=ring.replace(push,push+'\n        assert(::publication_phase==1); ::publication_phase=2; ++::pcm_publications;')
common=(ROOT/'vendor/sources/eden/src/audio_core/common/common.h').read_text()
channels=common[common.index('enum class Channels : u32 {'):]
channels=channels[:channels.index('};')+2]
cpp=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <span>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <vector>
using s16=std::int16_t; using s32=std::int32_t; using u32=std::uint32_t; using u64=std::uint64_t; using f32=float;
thread_local unsigned publication_phase,pcm_publications,allocations;
void* operator new(std::size_t n) {
    ++allocations;
    if(void* p=std::malloc(n)) return p;
    throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }
#include "ring.h"
CHANNELS
enum class StreamType { Render,Out,In };
struct SinkBuffer { u64 frames{},frames_played{},tag{}; bool consumed{}; };
namespace Settings { thread_local f32 volume=1.f; f32 Volume(){return volume;} }
struct MetadataQueue {
    void EmplaceWait(const SinkBuffer&) { assert(publication_phase==0); publication_phase=1; }
};
struct Stream {
    StreamType type{StreamType::Render};
    u32 system_channels=1,device_channels=2;
    f32 system_volume=0.8f,device_volume=0.9f;
    MetadataQueue queue;
    Common::RingBuffer<s16,0x10000> samples_buffer;
    std::atomic<unsigned> queued_buffers{};
};
namespace Before { struct SinkStream:Stream { void AppendBuffer(SinkBuffer&,std::span<s16>); }; BEFORE }
namespace After { struct SinkStream:Stream { void AppendBuffer(SinkBuffer&,std::span<s16>); }; AFTER }
template<class S> unsigned Append(S& stream,std::vector<s16>& samples) {
    SinkBuffer buffer{samples.size()/stream.system_channels};
    publication_phase=pcm_publications=allocations=0;
    stream.AppendBuffer(buffer,samples);
    const auto result=allocations;
    assert(publication_phase==2 && pcm_publications==1);
    return result;
}
void Run(unsigned identity) {
    Settings::volume=identity?1.75f:0.7f;
    unsigned before_allocations=0,after_allocations=0;
    for(const auto& [in,out]:std::array<std::pair<u32,u32>,4>{{{1,2},{2,6},{6,2},{2,2}}}) {
        Before::SinkStream before;
        After::SinkStream after;
        before.system_channels=after.system_channels=in;
        before.device_channels=after.device_channels=out;
        // Warm the largest valid block; subsequent blocks reuse capacity.
        std::vector<s16> warm(256*in,73);
        Append(after,warm);
        (void)after.samples_buffer.Pop(256*out);
        for(unsigned iteration=0;iteration<128;++iteration) {
            const auto frames=32*(1+iteration%8);
            std::vector<s16> left(frames*in);
            for(std::size_t i=0;i<left.size();++i)
                left[i]=static_cast<s16>((i*29+iteration*97+identity*13)%65536-32768);
            auto right=left;
            const auto old_alloc=Append(before,left),new_alloc=Append(after,right);
            assert(old_alloc==(in<out?1u:0u) && new_alloc==0);
            before_allocations+=old_alloc; after_allocations+=new_alloc;
            assert(left==right);
            auto old_pcm=before.samples_buffer.Pop(frames*out);
            auto new_pcm=after.samples_buffer.Pop(frames*out);
            assert(old_pcm.size()==frames*out && old_pcm==new_pcm);
        }
        assert(before.queued_buffers==128 && after.queued_buffers==129);
    }
    // Queue overflow still rejects the entire block before any publication.
    After::SinkStream full;
    std::vector<s16> occupied(0x10000);
    publication_phase=1; full.samples_buffer.Push(occupied);
    SinkBuffer buffer{1}; std::array<s16,1> sample{2};
    publication_phase=pcm_publications=0;
    try { full.AppendBuffer(buffer,sample); assert(false); }
    catch(const std::overflow_error&) { assert(publication_phase==0 && pcm_publications==0); }
    After::SinkStream input;
    input.type=StreamType::In;
    input.AppendBuffer(buffer,sample);
    assert(publication_phase==0 && pcm_publications==0);
    std::printf("AUDIO_UPMIX_HOST_PASS producer=%u upmix_blocks_after_warmup=256 allocations=%u->%u PCM=bit_exact publication=single\n",
                identity,before_allocations,after_allocations);
}
int main() {
    std::thread first(Run,0),second(Run,1);
    first.join();second.join();
    std::puts("AUDIO_UPMIX_TLS_PASS producers=2 channel_pairs=1to2,2to6,6to2,2to2 volumes=2 ring_wrap=covered overflow=rejected");
}
'''.replace('CHANNELS',channels).replace('BEFORE',previous).replace('AFTER',current)
compiler=shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
with tempfile.TemporaryDirectory(prefix='encore-audio-upmix-') as temp:
    folder=Path(temp);(folder/'ring.h').write_text(ring)
    unit,binary=folder/'main.cpp',folder/'audio';unit.write_text(cpp)
    subprocess.run([compiler,'-std=c++20','-O2','-g','-Wall','-Wextra','-Werror',
                    '-ffp-contract=off','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                    '-I'+str(folder),str(unit),'-o',str(binary)],check=True,timeout=60)
    subprocess.run([str(binary)],check=True,timeout=30)
print('AUDIO_UPMIX_HOST_ONLY native_audio_timing_and_PS5_stutters=unverified')
