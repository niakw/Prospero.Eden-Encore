#!/usr/bin/env python3
"""Source-extracted ASan/UBSan: reject failed CV waiter-flag write before sleep.

A scheduler lock and a valid virtual address do not guarantee a writable key.
Test the actual active code against the pinned negative control.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
ACTIVE=(ROOT/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_condition_variable.cpp").read_text()
PINNED=(ROOT/"vendor/sources/eden/src/core/hle/kernel/k_condition_variable.cpp").read_text()
SELECTOR=(ROOT/"vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "k_condition_variable.cpp" in SELECTOR
assert "python3 -B tools/check-native-hle-cv-key-write-host.py" in FAST
assert "python3 -B tools/check-native-hle-cv-key-write-host.py" in FULL
anchor="            // Write to the cv key."
ending="\n\n            // Write the value to userspace."
def grab(text,first):
    assert text.count(first)==1
    return text[text.index(first):text.index(ending,text.index(first))]
baseline=grab(PINNED,anchor)
active=grab(ACTIVE,"            // Publishing the waiter flag")
assert "!WriteToUser(" not in baseline and "!WriteToUser(" in active
assert "slp.CancelSleep();" in active
assert "R_THROW(ResultInvalidCurrentMemory);" in active
cpp=r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
using u32=std::uint32_t;
using u64=std::uint64_t;
constexpr int ResultInvalidCurrentMemory=9;
struct KernelCore{};
struct System{KernelCore kernel;KernelCore& Kernel(){return kernel;}};
struct Slp{int cancelled=0;void CancelSleep(){++cancelled;}};
static bool should_fail=false;
static unsigned writes=0;
bool WriteToUser(KernelCore&,u64,u32){
    ++writes;
    return !should_fail;
}
#define R_THROW(reason) return reason
struct WaitSimulation{
    System m_system;
    int Execute(u64 key,Slp& slp){
INJECT
        return 0;
    }
};
int main(){
    WaitSimulation simulation;
    Slp normal;
    should_fail=false;
    assert(simulation.Execute(0x1000,normal)==0);
    assert(normal.cancelled==0 && writes==1);
    Slp failed;
    should_fail=true;
    assert(simulation.Execute(0x1000,failed)==ResultInvalidCurrentMemory);
    assert(failed.cancelled==1 && writes==2);
    std::puts("ENCORE_CV_KEY_FAILED_WRITE_GUARD_PASS");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-cv-key-write-") as td:
    folder=Path(td)
    for name,body,corrected in (("pinned",baseline,False),("active",active,True)):
        path=folder/(name+".cpp");exe=folder/name
        path.write_text(cpp.replace("INJECT",body))
        subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        str(path),"-o",str(exe)],check=True,timeout=90)
        p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        if corrected:
            assert p.returncode==0,p.stderr[-1400:]
        else:
            assert p.returncode!=0,"Pinned code unexpectedly rejected failed waiter-flag write"
print("HLE_CV_KEY_WRITE_HOST_PASS; console deadlock proof unavailable")
