#!/usr/bin/env python3
"""Sanitizer witness for native guest write spans with mismatched sizes.

Compiles the actual pinned and maintained guest-memory template. A short
source span must trigger an ASan read overflow in the pinned version; the
native version copies only the intersection of source/destination lengths.
This is NOT a GPU scheduling or console performance test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
pinned=(root/"vendor/sources/eden/src/core/guest_memory.h").read_text()
native=(root/"vendor/encore-active/eden-core/overrides/core/guest_memory.h").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
workflow=(root/".github/workflows/encore-core-preflight.yml").read_text()
before="""    void Write(std::span<T> write_data) noexcept {
        if constexpr (FLAGS & GuestMemoryFlags::Cached) {
            m_memory->WriteBlockCached(m_addr, write_data.data(), this->size_bytes());
        } else if constexpr (FLAGS & GuestMemoryFlags::Safe) {
            m_memory->WriteBlock(m_addr, write_data.data(), this->size_bytes());
        } else {
            m_memory->WriteBlockUnsafe(m_addr, write_data.data(), this->size_bytes());
        }
    }"""
after="""    void Write(std::span<T> write_data) noexcept {
        // The supplied span may be shorter than the guest allocation.
        // Never read past its backing storage or write past the guest range.
        const std::size_t write_bytes = std::min(write_data.size_bytes(), this->size_bytes());
        if (write_bytes == 0) {
            return;
        }
        if constexpr (FLAGS & GuestMemoryFlags::Cached) {
            m_memory->WriteBlockCached(m_addr, write_data.data(), write_bytes);
        } else if constexpr (FLAGS & GuestMemoryFlags::Safe) {
            m_memory->WriteBlock(m_addr, write_data.data(), write_bytes);
        } else {
            m_memory->WriteBlockUnsafe(m_addr, write_data.data(), write_bytes);
        }
    }"""
assert pinned.count(before)==1
assert native == pinned.replace("#include <iterator>", "#include <algorithm>\n#include <iterator>").replace(before,after)
assert "Missing maintained native guest memory bounds" in cmake
assert 'target_include_directories(core BEFORE PUBLIC "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in cmake
assert 'target_include_directories(video_core BEFORE PRIVATE "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in cmake
assert "python3 -B tools/check-native-guest-write-span-host.py" in workflow

source=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
using u8=std::uint8_t;
using u32=std::uint32_t;
using u64=std::uint64_t;
#include "core/guest_memory.h"
struct FakeMemory {
    static constexpr bool HAS_FLUSH_INVALIDATION=true;
    std::array<u8,64> bytes{};
    std::size_t last_length{};
    unsigned writes{};
    u8* GetSpan(u64 a, std::size_t n) {
        if (a > bytes.size() || n > bytes.size()-a) return nullptr;
        return bytes.data()+a;
    }
    void WriteBlock(u64 a, const void* p, std::size_t n) {
        assert(a <= bytes.size() && n <= bytes.size()-a);
        last_length=n; ++writes; std::memcpy(bytes.data()+a,p,n);
    }
    void WriteBlockUnsafe(u64 a, const void* p, std::size_t n) { WriteBlock(a,p,n); }
    void WriteBlockCached(u64 a, const void* p, std::size_t n) { WriteBlock(a,p,n); }
    void InvalidateRegion(u64, std::size_t) {}
};
int main(int argc, char**) {
    using namespace Core::Memory;
    FakeMemory memory;
    GuestMemory<FakeMemory,u8,GuestMemoryFlags::SafeWrite> guest(memory,8,16);
    if (argc > 1) {
        std::array<u8,1> short_source{99};
        guest.Write(std::span<u8>(short_source));
        return 0; // Pinned version must trigger ASan first.
    }
    std::array<u8,1> short_source{99};
    guest.Write(std::span<u8>(short_source));
    assert(memory.writes==1 && memory.last_length==1);
    assert(memory.bytes[8]==99 && memory.bytes[9]==0);
    std::array<u8,32> large_source{};
    for(unsigned i=0;i<large_source.size();++i) large_source[i]=i+1;
    guest.Write(std::span<u8>(large_source));
    assert(memory.writes==2 && memory.last_length==16);
    assert(memory.bytes[8]==1 && memory.bytes[23]==16 && memory.bytes[24]==0);
    guest.Write(std::span<u8>{});
    assert(memory.writes==2);
}
"""
clang=shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-native-span-write-") as tmp:
    base=Path(tmp)
    common=base/"common"
    common.mkdir()
    (common/"assert.h").write_text("#pragma once\n#include <cassert>\n#define ASSERT(x) assert(x)\n")
    (common/"scratch_buffer.h").write_text(
        "#pragma once\n#include <vector>\n#include <span>\n"
        "namespace Common { template<class T> struct ScratchBuffer { "
        "std::vector<T> data; void resize_destructive(std::size_t n){data.resize(n);} "
        "operator std::span<T>() {return std::span<T>(data);} }; }\n"
    )
    unit=base/"span_write.cpp"
    unit.write_text(source)
    staged=base/"core"
    staged.mkdir()
    for label,header,corrected in (
        ("pinned",pinned,False),
        ("native",native,True),
    ):
        (staged/"guest_memory.h").write_text(header)
        binary=base/label
        subprocess.run([
            clang,"-std=c++20","-O0","-g","-Wall","-Wextra","-Werror",
            "-fsanitize=address,undefined","-fno-sanitize-recover=all",
            "-I",str(base),str(unit),"-o",str(binary)
        ],check=True,timeout=45)
        if corrected:
            subprocess.run([str(binary)],check=True,timeout=45)
        else:
            bad=subprocess.run([str(binary),"--short"],capture_output=True,text=True,timeout=45)
            assert bad.returncode != 0, "Pinned short span unexpectedly succeeded"
            assert "AddressSanitizer" in bad.stderr and "stack-buffer-overflow" in bad.stderr, bad.stderr
print("NATIVE_GUEST_WRITE_SPAN_HOST_PASS pinned_short_source_asan=1 native_source_bound=1 native_dest_bound=1 empty_span=1")
