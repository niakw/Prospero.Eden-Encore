#!/usr/bin/env python3
"""N04: native Host1x late-ready callback reentrance with historical negative.

Extract real C++ methods from pinned and maintained TUs, compile at -O0/-O2,
and force a syncpoint update between initial and mutex-protected recheck.
This covers only RegisterAction: Increment still holds its action mutex.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PIN=(ROOT/"vendor/sources/eden/src/video_core/host1x/syncpoint_manager.cpp").read_text()
ACT=(ROOT/"vendor/encore-active/eden-core/src/video_core/host1x/syncpoint_manager.cpp").read_text()
CM=(ROOT/"headless/CMakeLists.txt").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
NAME="python3 -B tools/check-native-host1x-register-reentrant-host.py"
assert NAME in FAST and NAME in FULL
assert "list(REMOVE_ITEM video_sources host1x/syncpoint_manager.cpp)" in CM
assert "list(APPEND video_sources" in CM and "EDEN_MAINTAINED_HOST1X_SYNCPOINT" in CM
old="""    std::scoped_lock lk(guard);
    if (syncpoint.load(std::memory_order_relaxed) >= expected_value) {
        action();
        return {};
    }"""
new="""    std::unique_lock lk(guard);
    if (syncpoint.load(std::memory_order_relaxed) >= expected_value) {
        // The action can register or cancel other Host1x work.
        // Release the shared lock before invoking an already-ready callback.
        lk.unlock();
        action();
        return {};
    }"""
assert PIN.count(old)==ACT.count(new)==1
increment_old="    std::scoped_lock lk(guard);\n    auto it = action_storage.begin();\n    while (it != action_storage.end()) {\n        if (it->expected_value > new_value) {\n            break;\n        }\n        it->action();\n        it = action_storage.erase(it);\n    }\n    wait_cv.notify_all();"
increment_new="    // Claim ready callbacks atomically against deregistration without\n    // allocating or executing arbitrary callbacks under the Host1x guard.\n    std::list<RegisteredAction> ready_actions;\n    {\n        std::scoped_lock lk(guard);\n        auto it = action_storage.begin();\n        while (it != action_storage.end() && it->expected_value <= new_value) {\n            ++it;\n        }\n        ready_actions.splice(ready_actions.end(), action_storage,\n                             action_storage.begin(), it);\n    }\n    // Cancellation can prevent an action only before the claim above.\n    // Execute the already-claimed batch without holding the global guard.\n    for (auto& ready : ready_actions) {\n        ready.action();\n    }\n    // Preserve the original contract: guest/host waiters are notified\n    // only after all due callbacks have completed, never before dispatch.\n    wait_cv.notify_all();"
guest_old="void SyncpointManager::IncrementGuest(u32 syncpoint_id) {\n    Increment(syncpoints_guest[syncpoint_id], wait_guest_cv, guest_action_storage[syncpoint_id]);\n}"
guest_new="void SyncpointManager::IncrementGuest(u32 syncpoint_id) {\n    // The old global guard serialized callbacks for this id. Keep their\n    // submission order without blocking independent guest syncpoints.\n    static std::array<std::recursive_mutex, 192> dispatch_mutexes{};\n    std::scoped_lock dispatch_lock{dispatch_mutexes[syncpoint_id]};\n    Increment(syncpoints_guest[syncpoint_id], wait_guest_cv, guest_action_storage[syncpoint_id]);\n}"
host_old="void SyncpointManager::IncrementHost(u32 syncpoint_id) {\n    Increment(syncpoints_host[syncpoint_id], wait_host_cv, host_action_storage[syncpoint_id]);\n}"
host_new="void SyncpointManager::IncrementHost(u32 syncpoint_id) {\n    static std::array<std::recursive_mutex, 192> dispatch_mutexes{};\n    std::scoped_lock dispatch_lock{dispatch_mutexes[syncpoint_id]};\n    Increment(syncpoints_host[syncpoint_id], wait_host_cv, host_action_storage[syncpoint_id]);\n}"
assert PIN.replace(old,new).replace(increment_old,increment_new).replace(guest_old,guest_new).replace(host_old,host_new)==ACT

def extract(text,name):
    assert text.count(name)==1,name
    start=text.index(name)
    opening=text.index("{",start)
    depth=0
    for i in range(opening,len(text)):
        if text[i]=="{":depth+=1
        elif text[i]=="}":
            depth-=1
            if depth==0:return text[start:i+1]
    raise AssertionError(name)

names=("SyncpointManager::ActionHandle SyncpointManager::RegisterAction(",
       "void SyncpointManager::DeregisterAction(",
       "void SyncpointManager::DeregisterGuestAction(",
       "void SyncpointManager::IncrementGuest(",
       "void SyncpointManager::Increment(")
def methods(src):
    parts=[extract(src,n) for n in names]
    marker="    if (syncpoint.load(std::memory_order_relaxed) >= expected_value) {"
    assert parts[0].count(marker)==1
    parts[0]=parts[0].replace(marker,marker+
        "\n        late_hits.fetch_add(1,std::memory_order_relaxed);")
    return "\n\n".join(parts)

CPP=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <list>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
using u32=std::uint32_t;
static std::atomic<unsigned> late_hits{};
class SyncpointManager {
public:
    struct RegisteredAction {
        u32 expected_value;
        std::function<void()> action;
        RegisteredAction(u32 n,std::function<void()>&& f)
            :expected_value(n),action(std::move(f)){}
    };
    using ActionHandle=std::list<RegisteredAction>::iterator;
    std::array<std::atomic<u32>,192> syncpoints_guest{};
    std::array<std::list<RegisteredAction>,192> guest_action_storage;
    std::mutex guard;
    std::condition_variable wait_guest_cv;
    template<typename F> ActionHandle RegisterGuestAction(u32 id,u32 expected,F&& f){
        return RegisterAction(syncpoints_guest[id],guest_action_storage[id],
                              expected,std::forward<F>(f));
    }
    ActionHandle RegisterAction(std::atomic<u32>&,std::list<RegisteredAction>&,
                                u32,std::function<void()>&&);
    void DeregisterAction(std::list<RegisteredAction>&,const ActionHandle&);
    void DeregisterGuestAction(u32,const ActionHandle&);
    void IncrementGuest(u32);
    void Increment(std::atomic<u32>&,std::condition_variable&,
                   std::list<RegisteredAction>&);
};
__METHODS__
int main(){
    SyncpointManager m;
    std::atomic<unsigned> late{},nested{};
    std::vector<u32> order;
    m.RegisterGuestAction(5,3,[&]{order.push_back(3);});
    m.RegisterGuestAction(5,1,[&]{order.push_back(1);});
    m.RegisterGuestAction(5,2,[&]{order.push_back(2);});
    auto cancelled=m.RegisterGuestAction(6,1,[&]{assert(false);});
    m.DeregisterGuestAction(6,cancelled);
    m.IncrementGuest(6);
    m.IncrementGuest(5);
    m.IncrementGuest(5);
    m.IncrementGuest(5);
    assert((order==std::vector<u32>{1,2,3}));
    for(unsigned k=0;k<24;k++){
        m.syncpoints_guest[0].store(0,std::memory_order_release);
        std::unique_lock hold{m.guard};
        std::atomic<bool> launched{};
        std::thread t([&]{
            launched.store(true,std::memory_order_release);
            m.RegisterGuestAction(0,1,[&]{
                // Pinned late callback fails; maintained unlocks before call.
                assert(m.guard.try_lock());
                m.guard.unlock();
                m.RegisterGuestAction(5,0,[&]{++nested;});
                ++late;
            });
        });
        while(!launched.load(std::memory_order_acquire))std::this_thread::yield();
        std::this_thread::sleep_for(std::chrono::milliseconds(3));
        // Increment publishes atomically before taking this same mutex.
        m.syncpoints_guest[0].store(1,std::memory_order_release);
        hold.unlock();
        t.join();
    }
    assert(late_hits>=1 && late==24 && nested==24);
    assert(m.guest_action_storage[0].empty());
    std::printf("N04_HOST1X_REENTRANT_LATE_PASS slow=%u callback=%u nested=%u\n",
                late_hits.load(),late.load(),nested.load());
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"Host C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-host1x-") as tmp:
    for name,code,mode in (("current_O0",methods(ACT),"-O0"),
                           ("current_O2",methods(ACT),"-O2"),
                           ("pinned_negative",methods(PIN),"-O0")):
        source=Path(tmp)/(name+".cpp")
        exe=Path(tmp)/name
        source.write_text(CPP.replace("__METHODS__",code))
        built=subprocess.run([compiler,"-std=c++20",mode,"-Wall","-Wextra",
                              "-Werror","-pthread","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(source),"-o",str(exe)],
                             capture_output=True,text=True,timeout=65)
        assert built.returncode==0,(name,built.stderr[-3000:])
        out=subprocess.run([str(exe)],capture_output=True,text=True,timeout=17)
        if name=="pinned_negative":
            assert out.returncode!=0 and "m.guard.try_lock()" in out.stderr,(name,out.stderr[-1200:])
            print("N04_HOST1X_PINNED_NEGATIVE_PASS guarded_callback_rejected")
        else:
            assert out.returncode==0,(name,out.stdout,out.stderr[-1500:])
            print(out.stdout.strip(),name)
print("N04_HOST1X_INCREMENT_CALLBACK_GUARD_UNCHANGED no_end_to_end_certification")
