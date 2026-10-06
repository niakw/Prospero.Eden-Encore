#!/usr/bin/env python3
"""Exercise actual Dynarmic monitor operations with the PS5 lock derivative."""
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
cache = Path((root / '.local/headless-cache').read_text().strip())
dynarmic = cache / 'source/src/dynarmic/src'
monitor = (dynarmic / 'dynarmic/backend/x64/exclusive_monitor.cpp').read_text()
# This implementation includes, but does not use, the application logger/asserts.
monitor = monitor.replace('#include "common/assert.h"', '')
lock = (root / 'headless/spin-lock.inc').read_text()
source = r'''
#include <cassert>
#include <chrono>
#include <thread>
#include <vector>
#include <barrier>
#include "dynarmic/interface/exclusive_monitor.h"
extern "C" int sceKernelUsleep(unsigned int microseconds) {
    std::this_thread::sleep_for(std::chrono::microseconds(microseconds));
    return 0;
}
namespace Dynarmic {
LOCK
}
MONITOR
int main() {
    Dynarmic::ExclusiveMonitor monitor(4);
    unsigned value = 0;
    auto read = [&](unsigned core) { return monitor.ReadAndMark<unsigned>(core, 0x1000, [&] { return value; }); };
    auto increment = [&](unsigned core) { return monitor.DoExclusiveOperation<unsigned>(core, 0x1000, [&](unsigned expected) {
        if (value != expected) return false;
        ++value;
        return true;
    }); };
    read(0); read(1);
    assert(increment(0) && !increment(1)); // One write invalidates peer reservation.
    read(0); monitor.ClearProcessor(0); assert(!increment(0));
    read(0); read(1); monitor.Clear(); assert(!increment(0) && !increment(1));
    read(0);
    assert(!monitor.DoExclusiveOperation<unsigned>(0, 0x2000, [](unsigned) { assert(false); return true; }));
    monitor.Clear(); value = 0;
    constexpr unsigned workers = 4, iterations = 50000;
    std::barrier ready(workers);
    std::vector<std::jthread> threads;
    for (unsigned core = 0; core < workers; ++core) threads.emplace_back([&, core] {
        ready.arrive_and_wait();
        for (unsigned i = 0; i < iterations; ++i) {
            do { read(core); } while (!increment(core));
        }
    });
    threads.clear();
    assert(value == workers * iterations);
}
'''.replace('LOCK', lock).replace('MONITOR', monitor)
boost = cache / 'source/.cache/cpm/boost/boost-1.90.0'
includes = ['-I' + str(dynarmic)] + ['-I' + str(p) for p in sorted(boost.glob('libs/*/include'))]
assert len(includes) > 1
with tempfile.TemporaryDirectory(prefix='eden-monitor-') as tmp:
    cpp = Path(tmp) / 'check.cpp'
    binary = Path(tmp) / 'check'
    cpp.write_text(source)
    compile_command = ['clang++-18', '-std=c++20', '-O3', '-flto=thin', '-fuse-ld=lld-18',
                       '-pthread', '-Wall', '-Wextra', '-Werror']
    # Dynarmic's x64 monitor contains x86 pause instructions. On Apple Silicon,
    # build the host semantics harness as a real x86_64 macOS binary and run it
    # through Rosetta; compiling it as arm64 would reject __builtin_ia32_pause.
    if sys.platform == 'darwin' and platform.machine() == 'arm64':
        preferred_sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk')
        sdk = (str(preferred_sdk) if preferred_sdk.is_dir() else
               subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip())
        compile_command = ['/usr/bin/clang++', '-arch', 'x86_64', '-isysroot', sdk,
                           '-std=c++20', '-O3', '-pthread', '-Wall', '-Wextra', '-Werror']
    subprocess.run([*compile_command, *includes, str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)
native = cache / 'native-local/bin/eden-headless'
symbols = subprocess.check_output(['llvm-nm-18', '--defined-only', str(native)], text=True)
outlined = '_ZN8Dynarmic8SpinLock4LockEv' in symbols
names = ('_ZN8Dynarmic8SpinLock4LockEv,_ZN8Dynarmic8SpinLock6UnlockEv' if outlined
         else '_ZN8Dynarmic16ExclusiveMonitor14ClearProcessorEm')
assembly = subprocess.check_output(['llvm-objdump-18',
    '--disassemble-symbols=' + names,
    str(native)], text=True)
for name in names.split(','):
    assert '<' + name + '>:' in assembly
# The bounded slow path deliberately sleeps so a critical-priority waiter cannot starve a
# preempted owner. It is the only runtime call permitted in the lock implementation.
calls = [line for line in assembly.splitlines() if re.search(r'\bcallq?\b', line)]
assert calls, 'Native monitor lock lost its bounded backoff call'
# lld may render a GOT import as an indirect register call after ThinLTO. Prove
# that the register was loaded from the relocation slot for sceKernelUsleep.
direct_backoff = any('sceKernelUsleep' in line for line in calls)
if not direct_backoff:
    got_load = re.search(r'movq\s+[^#\n]+%r12\s+#\s+0x([0-9a-f]+)', assembly)
    assert got_load and any('callq\t*%r12' in line for line in calls), (
        'Native monitor backoff is neither a direct nor the expected GOT call: ' + repr(calls))
    relocations = subprocess.check_output(['llvm-readobj-18', '--relocations', str(native)], text=True)
    slot = '0X' + got_load.group(1).upper()
    assert any(slot in line.upper() and 'SCEKERNELUSLEEP' in line.upper()
               for line in relocations.splitlines()), (
        'Native monitor GOT call does not resolve to sceKernelUsleep: ' + slot)
# A noexcept inlined ClearProcessor may carry Clang's exception-termination
# landing pad outside the lock path; it is not part of the backoff loop.
assert all('sceKernelUsleep' in line or '__clang_call_terminate' in line or '*%r12' in line
           for line in calls), 'Unexpected runtime call in native monitor lock: ' + repr(calls)
# ThinLTO may inline the lock in ClearProcessor and may lower the same seq_cst
# fence to a locked zero-OR on the stack instead of MFENCE.
full_fence = 'mfence' in assembly or re.search(r'\block\s*\n[^\n]*\borl\s+\$0x0,\s*-0x[0-9a-f]+\(%rsp\)', assembly)
minimum_exchanges = 3 if not outlined else 2
assert full_fence and 'pause' in assembly and assembly.count('xchgl') >= minimum_exchanges
print('Exclusive monitor: peer invalidation, clear, wrong address and 200000 contended increments PASS')
print('Native lock machine code: bounded sceKernelUsleep backoff, exchange acquisition/release and full fence PASS')
