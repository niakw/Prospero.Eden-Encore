#!/usr/bin/env python3
"""Run real maintained fibers on the pinned Boost context assembly, host only."""
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if platform.system() != 'Linux' or platform.machine() != 'x86_64':
    print('FIBER_STACK source parity retained; Linux/x86 context harness runs in native CI')
    raise SystemExit(0)
cache = Path((ROOT / '.local/headless-cache').read_text().strip())
boost = cache / 'source/.cache/cpm/boost/boost-1.90.0'
assembly = [boost / ('libs/context/src/asm/' + name + '_x86_64_sysv_elf_gas.S')
            for name in ('make', 'jump')]
assert all(p.is_file() for p in assembly), 'run pinned native dependency preparation first'
pinned = (ROOT / 'vendor/sources/eden/src/common/fiber.cpp').read_text()
first = '    to.impl->previous_fiber = weak_from.lock();'
previous = pinned.replace(first, first + '\n    ASSERT(to.impl->previous_fiber);\n    weak_from.reset();').replace(
    '    // "from" might no longer be valid if the thread was killed\n    if (auto from = weak_from.lock()) {',
    '    if (auto* from = static_cast<Fiber*>(transfer.data)) {')
fixture = r'''
#include "common/fiber.h"
#include <array>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <semaphore>
#include <thread>
static std::atomic<std::size_t> large_bytes;
void* operator new(std::size_t bytes) {
    if (auto* p = std::malloc(bytes)) {
        if (bytes >= 1024 * 1024) large_bytes.fetch_add(bytes, std::memory_order_relaxed);
        return p;
    }
    throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
int main() {
    std::array<std::binary_semaphore, 2> turn{std::binary_semaphore{1}, std::binary_semaphore{0}};
    std::atomic<Common::Fiber*> active_host{};
    std::atomic<unsigned> active_worker{}, transitions{};
    std::array<unsigned, 2> visits{};
    std::shared_ptr<Common::Fiber> guest;
    guest = std::make_shared<Common::Fiber>([&] {
        for (;;) {
            ++visits[active_worker.load(std::memory_order_relaxed)];
            transitions.fetch_add(1, std::memory_order_relaxed);
            Common::Fiber::YieldTo(guest, *active_host.load(std::memory_order_acquire));
        }
    });
    const auto guest_bytes = large_bytes.exchange(0);
    auto worker = [&](unsigned id) {
        auto host = Common::Fiber::ThreadToFiber();
        for (unsigned iteration = 0; iteration < 64; ++iteration) {
            turn[id].acquire();
            active_worker.store(id, std::memory_order_relaxed);
            active_host.store(host.get(), std::memory_order_release);
            Common::Fiber::YieldTo(host, *guest);
            turn[1 - id].release();
        }
        host->Exit();
    };
    std::thread a(worker, 0), b(worker, 1);
    a.join(); b.join();
    assert(transitions == 128 && visits[0] == 64 && visits[1] == 64);
    const auto host_bytes = large_bytes.load();
#ifdef OLD_STACK
    assert(guest_bytes >= 4 * 1024 * 1024 && host_bytes >= 8 * 1024 * 1024);
#else
    assert(guest_bytes >= 2 * 1024 * 1024 && guest_bytes < 2 * 1024 * 1024 + 4096);
    assert(host_bytes == 0);
#endif
    guest.reset();
    std::printf("FIBER_STACK_HOST_PASS switches=128 migrated_workers=2 guest_large_bytes=%zu "
                "host_large_bytes=%zu guards_and_exit=preserved\n", guest_bytes, host_bytes);
}
'''
compiler = shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
with tempfile.TemporaryDirectory(prefix='encore-fiber-stack-') as temp:
    folder = Path(temp)
    stub = folder / 'include/common'; stub.mkdir(parents=True)
    (stub / 'assert.h').write_text('#pragma once\n#include <array>\n#include <cassert>\n#include <cstdint>\n#include <cstdlib>\nusing u8=std::uint8_t; using u32=std::uint32_t;\n#define ASSERT(x) assert(x)\n#define ASSERT_MSG(x,...) assert(x)\n#define UNREACHABLE() std::abort()\n')
    harness = folder / 'main.cpp'; harness.write_text(fixture)
    # The native cache exposes C++ declarations; raw SysV assembly exports C
    # symbols. Bridge only that linkage boundary and execute the real assembly.
    bridge = folder / 'context-linkage.cpp'
    bridge.write_text(r'''
#include <boost/context/detail/fcontext.hpp>
using boost::context::detail::fcontext_t;
using boost::context::detail::transfer_t;
extern "C" fcontext_t raw_make(void*, std::size_t, void (*)(transfer_t)) asm("make_fcontext");
extern "C" transfer_t raw_jump(fcontext_t, void*) asm("jump_fcontext");
namespace boost::context::detail {
fcontext_t make_fcontext(void* stack, std::size_t size, void (*entry)(transfer_t)) {
    return raw_make(stack, size, entry);
}
transfer_t jump_fcontext(fcontext_t target, void* data) {
    return raw_jump(target, data);
}
}
''')
    old = folder / 'previous.cpp'; old.write_text(previous)
    objects = []
    for index, asm in enumerate(assembly):
        obj = folder / ('context-' + str(index) + '.o')
        subprocess.run([compiler, '-c', str(asm), '-o', str(obj)], check=True, timeout=30)
        objects.append(obj)
    for label, source in (('old', old), ('active', ROOT / 'vendor/encore-active/eden-core/src/common/fiber.cpp')):
        binary = folder / label
        flags = ['-DOLD_STACK=1'] if label == 'old' else []
        subprocess.run([compiler, '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all', *flags,
                        '-I' + str(folder / 'include'), '-I' + str(ROOT / 'vendor/sources/eden/src'),
                        '-I' + str(boost / 'libs/context/include'),
                        '-I' + str(boost / 'libs/config/include'),
                        str(harness), str(source), str(bridge), *(str(p) for p in objects), '-o', str(binary)],
                       check=True, timeout=90)
        subprocess.run([str(binary)], check=True, timeout=30)
print('FIBER_STACK_HOST_ONLY PS5_gameplay=unverified')
