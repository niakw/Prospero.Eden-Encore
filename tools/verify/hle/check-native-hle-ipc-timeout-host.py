#!/usr/bin/env python3
"""Host UBSan replay of actual ReplyAndReceive IPC deadline expressions.

The signed-overflow witness from immutable pinned Eden must fail. Both
Encore maintained normal and DEV C++ units must saturate safely. No
emulated thread waits or game performance are claimed by this test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[3]
pinned=(root/"vendor/sources/eden/src/core/hle/kernel/svc/svc_ipc.cpp").read_text()
owner=root/"vendor/encore-active/eden-core/src/core/hle/kernel/svc"
normal=(owner/"svc_ipc_standard.cpp").read_text()
dev=(owner/"svc_ipc.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
workflow=(root/".github/workflows/encore-core-preflight.yml").read_text()
old="""                timeout = kernel.HardwareTimer().GetTick() + offset_tick + 2;
                if (timeout <= 0) {
                    timeout = (std::numeric_limits<s64>::max)();
                }"""
fixed="""                s64 absolute{};
                if (__builtin_add_overflow(kernel.HardwareTimer().GetTick(), offset_tick,
                                           &absolute) ||
                    __builtin_add_overflow(absolute, s64{2}, &absolute) ||
                    absolute <= 0) {
                    timeout = (std::numeric_limits<s64>::max)();
                } else {
                    timeout = absolute;
                }"""
assert pinned.count(old)==1 and normal==pinned.replace(old,fixed)
assert old not in dev and dev.count(fixed)==1
assert "BeginGuestIpc(ipc_tid, ipc_start)" in dev
assert "BeginGuestIpc(ipc_tid, ipc_start)" not in normal
assert "Eden::Performance" not in normal
assert "python3 -B tools/verify/hle/check-native-hle-ipc-timeout-host.py" in workflow
assert 'if(NOT EDEN_DEV_PROFILE)\n    set(EDEN_MAINTAINED_SVC_IPC_STANDARD' in cmake
assert 'set(EDEN_MAINTAINED_PROFILE_SVC_IPC' in cmake
assert cmake.count('list(REMOVE_ITEM core_sources "hle/kernel/svc/svc_ipc.cpp")')==1
assert 'list(REMOVE_ITEM core_sources "hle/service/service.cpp" "hle/kernel/svc/svc_ipc.cpp")' in cmake
for source in (normal,dev):
    for marker in ("Result ReplyAndReceiveImpl(",
                   "KSynchronizationObject::Wait(kernel, std::addressof(index)",
                   "R_TRY(session->SendReply(kernel, message, buffer_size, message_paddr));",
                   "if (ResultNotFound == result)"):
        assert marker in source
def extract(source):
    first="        // Convert the timeout from nanoseconds to ticks."
    last="        // Wait for a message."
    assert source.count(first)==source.count(last)==1
    return source.split(first,1)[1].split(last,1)[0].strip()+"\n"
pre=r"""
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <limits>
using s64=std::int64_t;
struct Timer {s64 tick{};s64 GetTick() const {return tick;}};
struct KernelCore {Timer timer;Timer& HardwareTimer(){return timer;}};
s64 Convert(KernelCore& kernel,s64 timeout_ns) {
"""
post=r"""
return timeout;
}
int main(int argc,char** argv){
 assert(argc==2);
 KernelCore kernel;
 const s64 max=(std::numeric_limits<s64>::max)();
 const int mode=std::atoi(argv[1]);
 if(mode==0){
   kernel.timer.tick=100;
   assert(Convert(kernel,20)==122);
   assert(Convert(kernel,0)==0);
   assert(Convert(kernel,-1)==-1);
   assert(Convert(kernel,-2)==-2);
   kernel.timer.tick=max-4;
   assert(Convert(kernel,1)==max-1);
 }else if(mode==1){
   kernel.timer.tick=100;
   volatile s64 large=max;
   const s64 result=Convert(kernel,large);
#if EXPECT_FIXED
   assert(result==max);
#else
   (void)result;
#endif
 }else if(mode==2){
   kernel.timer.tick=max-2;
   volatile s64 small=1;
   const s64 result=Convert(kernel,small);
#if EXPECT_FIXED
   assert(result==max);
#else
   (void)result;
#endif
 }else return 9;
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-ipc-deadline-") as tmp:
    tmp=Path(tmp)
    for name,source,repaired in (("pinned",pinned,False),("normal",normal,True),("dev",dev,True)):
        cpp=tmp/(name+".cpp");exe=tmp/name
        cpp.write_text(pre+extract(source)+post)
        subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined","-fno-sanitize-recover=undefined",
                        "-DEXPECT_FIXED="+str(int(repaired)),str(cpp),"-o",str(exe)],
                       check=True,timeout=45)
        for mode in range(3):
            result=subprocess.run([str(exe),str(mode)],capture_output=True,text=True,timeout=10)
            if not repaired and mode:
                assert result.returncode!=0 and "signed integer overflow" in result.stderr,(
                    name,mode,result.stdout,result.stderr)
            else:
                assert result.returncode==0,(name,mode,result.stdout,result.stderr)
print("NATIVE_IPC_DEADLINE_HOST_PASS pinned_overflow=2 standard=1 dev=1 guard=1")
