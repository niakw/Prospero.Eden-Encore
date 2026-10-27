#!/usr/bin/env python3
"""Exercise real RX/RW Xbyak code on host and source-backed PS5 sparse mocks.

Do not run the retired dense-native fault injection against sparse-only PS5:
that tested an unshipped kernel ABI and aborted. The maintained native mock
compiles the actual PS5 memory manager and sparse Xbyak adapter, covering
bootstrap, demand commits, alias mapping, rollback and fail-closed behavior.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parents[1]
scratch = Path((root / '.local/headless-cache').read_text().strip())
code = (scratch / 'native-local/headless/block_of_code.cpp').read_text()
assert ', EdenJitAllocator())' in code
# The reduced host-allocation footprint must never be confused with a
# production cache-size change. Those remain independently constrained by
# the runtime's A64/A32 admission policy.
policy = (root / 'headless/experimental_performance.h').read_text()
assert '256u*kMiB, 192u*kMiB, 192u*kMiB, 16u*kMiB' in policy
assert '512u*kMiB, 64u*kMiB, 64u*kMiB, 16u*kMiB' in policy
assert 'kSingleArenaAddressingLimit = 1536u * kMiB' in policy
if sys.platform == 'darwin':
    # The runtime harness below is Linux/x86 specific: memfd aliases, mincore
    # semantics, GNU ld --wrap and generated x86 execution. The injected
    # production allocator is still required above and is compiled for PS5 by
    # the native target; the behavioral harness remains mandatory in Linux CI.
    print('Production JIT allocator injection PASS (Linux/x86 alias runtime harness deferred to CI)')
    raise SystemExit(0)
source = r'''
#include "jit-allocator.h"
#include <cassert>
#include <cerrno>
#include <limits>
#include <memory>
#include <vector>
#include <csignal>
#include <sys/wait.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
void fault(const unsigned char* p, bool write) {
    auto child=fork(); assert(child>=0);
    if (!child) {
        if (write) *const_cast<volatile unsigned char*>(p)=0;
        else reinterpret_cast<void(*)()>(const_cast<unsigned char*>(p))();
        _exit(0);
    }
    int status; assert(waitpid(child,&status,0)==child);
    assert(WIFSIGNALED(status) && WTERMSIG(status)==SIGSEGV);
}
int main() {
    auto* allocator = EdenJitAllocator();
    assert(!allocator->alloc(std::numeric_limits<std::size_t>::max()));
    allocator->free(nullptr);
    std::vector<std::unique_ptr<Xbyak::CodeGenerator>> caches;
    std::vector<const unsigned char*> pointers;
    const auto page = sysconf(_SC_PAGESIZE);
    // Keep this test an allocator/W^X/rollback test, not a 1.3 GiB
    // simultaneous address-space and memory-pressure stress. CI runners
    // can reject the 512 MiB alias despite the allocator being correct.
    // Full production arena sizes are tested separately in the JIT memory
    // policy and sparse virtual-plan contracts.
    for (auto mib : {16, 8, 8, 4}) {
        auto code = std::make_unique<Xbyak::CodeGenerator>(std::size_t(mib)*1024*1024,
            Xbyak::DontSetProtectRWE, allocator);
        code->mov(code->eax, 42); code->ret();
        auto* p = code->getCode(); pointers.push_back(p);
        auto* writable=code->writableAddress(p); pointers.push_back(writable);
        assert(code->hasWritableAlias() && p!=writable);
        assert(code->getCode<int(*)()>()()==42);
        fault(p,true); fault(writable,false);
        code->rewrite(1,84,4);
        assert(code->getCode<int(*)()>()()==84);
        caches.push_back(std::move(code));
    }
    caches.clear();
    for (auto* p : pointers) {
        unsigned char state;
        errno=0;
        assert(mincore(const_cast<unsigned char*>(p), page, &state)==-1 && errno==ENOMEM);
    }
}
'''
with tempfile.TemporaryDirectory() as temp:
    cpp=Path(temp)/'check.cpp'; exe=Path(temp)/'check'
    cpp.write_text(source)
    # Original host alias execution/permission regression is still mandatory.
    # PS5 sparse native semantics are verified below in their own real-memory mock.
    for host_alias in (True,):
        subprocess.run(['clang++-18','-std=c++20','-O2','-I'+str(root/'headless'),
            '-I'+str(scratch/'native-local/headless/include'),
            '-I'+str(scratch/'source/.cache/cpm/xbyak/v7.40.1'),str(cpp),
            str(root/'src/memory_pages.cpp'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True, cwd=temp)
# These source-extracted test suites target the only shipping PS5 allocator,
# not the old dense syscall mock. Let either failure block the native package.
native_sparse = root / 'tools/check-jit-sparse-host.py'
native_release = root / 'tools/check-native-sparse-jit-release-selector-host.py'
assert native_sparse.is_file() and native_release.is_file()
for proof in (native_sparse, native_release):
    subprocess.run([sys.executable, '-B', str(proof)], check=True, timeout=180)
print('Production JIT allocation PASS: host RW/RX execution and W^X faults; '
      'native sparse PS5 real-source mock, demand commits, OOM rollback and '
      'release-only selection (firmware execution still unverified)')
