#!/usr/bin/env python3
"""Compile pinned GuestMemory to qualify CPU/GPU flush/invalidation contracts.

Runs actual pinned C++ templates through direct spans and copy fallbacks.
No console build, no driver calls. The test is a contract witness, not a
measurement of native GPU fence completion.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/sources/eden/src/core/guest_memory.h").read_text()
gpu_guest = (root / "vendor/sources/eden/src/video_core/guest_memory.h").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
for marker in (
    "m_memory->FlushRegion(m_addr, this->size_bytes());",
    "m_memory->ReadBlock(m_addr, this->data(), this->size_bytes());",
    "m_memory->WriteBlock(this->m_addr, this->data(), this->size_bytes());",
    "this->m_memory->InvalidateRegion(this->m_addr, this->size_bytes());",
    "if (u8* ptr = m_memory->GetSpan(m_addr, this->size_bytes()); ptr)",
):
    assert header.count(marker) == 1, marker
assert "using GpuGuestMemoryScoped = Core::Memory::GuestMemoryScoped<" in gpu_guest
assert "python3 -B tools/check-native-guest-memory-coherence-host.py" in workflow

source = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <span>
using u8=std::uint8_t;
using u32=std::uint32_t;
using u64=std::uint64_t;
#include "core/guest_memory.h"

struct FakeGpuMemory {
    static constexpr bool HAS_FLUSH_INVALIDATION=true;
    alignas(u32) std::array<u8,64> bytes{};
    bool contiguous=true;
    unsigned flushes=0, safe_reads=0, unsafe_reads=0;
    unsigned safe_writes=0, unsafe_writes=0, invalidations=0, cached_writes=0;
    FakeGpuMemory() {
        for (unsigned i=0;i<bytes.size();++i) bytes[i]=static_cast<u8>(i);
    }
    u8* GetSpan(u64 a, std::size_t n) {
        return contiguous && a <= bytes.size() && n <= bytes.size()-a
            ? bytes.data()+a : nullptr;
    }
    void FlushRegion(u64, std::size_t) { ++flushes; }
    void ReadBlock(u64 a,void* p,std::size_t n) {
        ++safe_reads;
        assert(a <= bytes.size() && n <= bytes.size()-a);
        std::memcpy(p,bytes.data()+a,n);
    }
    void ReadBlockUnsafe(u64 a,void* p,std::size_t n) {
        ++unsafe_reads;
        assert(a <= bytes.size() && n <= bytes.size()-a);
        std::memcpy(p,bytes.data()+a,n);
    }
    void WriteBlock(u64 a,const void* p,std::size_t n) {
        ++safe_writes;
        assert(a <= bytes.size() && n <= bytes.size()-a);
        std::memcpy(bytes.data()+a,p,n);
    }
    void WriteBlockUnsafe(u64 a,const void* p,std::size_t n) {
        ++unsafe_writes;
        assert(a <= bytes.size() && n <= bytes.size()-a);
        std::memcpy(bytes.data()+a,p,n);
    }
    void WriteBlockCached(u64 a,const void* p,std::size_t n) {
        ++cached_writes;
        assert(a <= bytes.size() && n <= bytes.size()-a);
        std::memcpy(bytes.data()+a,p,n);
    }
    void InvalidateRegion(u64,std::size_t) { ++invalidations; }
};
using namespace Core::Memory;

int main() {
    FakeGpuMemory a;
    {
        GuestMemory<FakeGpuMemory,u8,GuestMemoryFlags::SafeRead> data(a,4,8);
        assert(data.data() == a.bytes.data()+4);
        assert(data.size_bytes()==8 && data[0]==4);
    }
    assert(a.flushes==1 && a.safe_reads==0 && a.invalidations==0);
    {
        GuestMemoryScoped<FakeGpuMemory,u8,GuestMemoryFlags::SafeReadWrite> data(a,4,8);
        data[2]=99;
    }
    assert(a.flushes==2 && a.invalidations==1);
    assert(a.bytes[6]==99 && a.safe_writes==0);
    {
        GuestMemoryScoped<FakeGpuMemory,u8,GuestMemoryFlags::SafeWrite> data(a,8,8);
        data[0]=101;
    }
    assert(a.invalidations==2 && a.bytes[8]==101 && a.safe_writes==0);

    FakeGpuMemory b;
    b.contiguous=false;  // GetSpan null: force tracked copy fallback
    {
        GuestMemory<FakeGpuMemory,u8,GuestMemoryFlags::SafeRead> data(b,4,8);
        assert(data.data()!=b.bytes.data()+4 && data[0]==4);
    }
    assert(b.safe_reads==1 && b.flushes==0);
    {
        GuestMemoryScoped<FakeGpuMemory,u8,GuestMemoryFlags::SafeReadWrite> data(b,4,8);
        data[1]=77;
    }
    assert(b.safe_reads==2 && b.safe_writes==1 && b.invalidations==0);
    assert(b.bytes[5]==77);
    {
        GuestMemoryScoped<FakeGpuMemory,u8,GuestMemoryFlags::SafeWrite> data(b,8,8);
        data[0]=88;
    }
    assert(b.safe_writes==2 && b.bytes[8]==88 && b.invalidations==0);

    FakeGpuMemory c;
    {
        GuestMemoryScoped<FakeGpuMemory,u8,GuestMemoryFlags::SafeReadWrite> data(c,4,8);
        data.SetAddressAndSize(20,8);
    }
    assert(c.flushes==1 && c.safe_writes==1 && c.invalidations==0);
    assert(c.bytes[20]==4 && c.bytes[27]==11);

    // A safe guest command read can be a *live alias* after FlushRegion.
    // It does not freeze command words against later guest RAM mutation.
    FakeGpuMemory live_words;
    {
        GuestMemory<FakeGpuMemory,u32,GuestMemoryFlags::SafeRead>
            commands(live_words,16,2);
        assert(live_words.flushes==1 && live_words.safe_reads==0);
        assert(commands.data()==reinterpret_cast<u32*>(live_words.bytes.data()+16));
        const u32 observed=commands[0];
        const u32 replacement=0xdecafbad;
        std::memcpy(live_words.bytes.data()+16,&replacement,sizeof(replacement));
        assert(commands[0]==replacement && commands[0]!=observed);
    }

    // The copied fallback snapshots its source at construction time.
    FakeGpuMemory copied_words;
    copied_words.contiguous=false;
    {
        GuestMemory<FakeGpuMemory,u32,GuestMemoryFlags::SafeRead>
            commands(copied_words,16,2);
        assert(copied_words.safe_reads==1 && copied_words.flushes==0);
        const u32 observed=commands[0];
        const u32 replacement=0xdecafbad;
        std::memcpy(copied_words.bytes.data()+16,&replacement,sizeof(replacement));
        assert(commands[0]==observed && commands[0]!=replacement);
    }

    FakeGpuMemory d;
    {
        GuestMemory<FakeGpuMemory,u8,GuestMemoryFlags::UnsafeRead> data(d,4,8);
        assert(data[0]==4);
    }
    assert(d.flushes==0 && d.safe_reads==0 && d.unsafe_reads==0);
}
"""
clang=shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-guest-coherence-") as tmp:
    temp=Path(tmp)
    common=temp/"common"
    common.mkdir()
    (common/"assert.h").write_text("#pragma once\n#include <cassert>\n#define ASSERT(x) assert(x)\n")
    (common/"scratch_buffer.h").write_text(
        "#pragma once\n#include <vector>\n#include <span>\n"
        "namespace Common {\n"
        "template<class T> struct ScratchBuffer {\n"
        "std::vector<T> data;\n"
        "void resize_destructive(std::size_t n) {data.resize(n);}\n"
        "operator std::span<T>() {return std::span<T>(data);}\n"
        "};\n}\n"
    )
    unit=temp/"fixture.cpp"
    unit.write_text(source)
    binary=temp/"fixture"
    subprocess.run(
        [clang,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
         "-pthread","-fsanitize=address,undefined","-fno-sanitize-recover=all",
         "-I",str(temp),"-I",str(root/"vendor/sources/eden/src"),
         str(unit),"-o",str(binary)],check=True,timeout=45
    )
    subprocess.run([str(binary)],check=True,timeout=45)
print("NATIVE_GUEST_MEMORY_COHERENCE_HOST_PASS direct_safe_read_flush=1 direct_safe_write_invalidate=2 copied_safe_read=2 copied_safe_write=2 relocated_write=1 unsafe_alias_no_flush=1 safe_read_live_alias=1 copied_read_stable_snapshot=1")
