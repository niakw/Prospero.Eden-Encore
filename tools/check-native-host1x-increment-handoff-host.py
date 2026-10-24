#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""N04/F05: native Host1x Increment claim/dispatch and cancellation witness.

Compile actual source-extracted Host1x C++ methods at -O0 and -O2. Callback
ordering and pending cancellation are preserved; ready actions are claimed
before releasing the mutex and cannot subsequently be cancelled. The pinned
source MUST fail reentrance. No GPU scanout/guest IPC or TSAN certification.
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
COMMAND="python3 -B tools/check-native-host1x-increment-handoff-host.py"
assert COMMAND in FAST and COMMAND in FULL
assert 'list(APPEND video_sources "' in CM and "EDEN_MAINTAINED_HOST1X_SYNCPOINT" in CM
assert 'list(REMOVE_ITEM video_sources host1x/syncpoint_manager.cpp)' in CM
assert ACT.count("ready_actions.splice(")==1 and ACT.count("ready.action();")==1
assert ACT.index("ready.action();") < ACT.index("wait_cv.notify_all();", ACT.index("ready.action();"))
assert "ready_actions" not in PIN
hs=ACT.index("namespace {\n// Each domain")
he=ACT.index("\nSyncpointManager::ActionHandle",hs)
helpers=ACT[hs:he]
assert "GuestDispatchLocks()" in helpers and "HostDispatchLocks()" in helpers
def extract(source, name):
    assert source.count(name)==1,name
    a=source.index(name)
    opening=source.index("{",a)
    depth=0
    for k in range(opening,len(source)):
        if source[k]=="{":depth+=1
        elif source[k]=="}":
            depth-=1
            if not depth:return source[a:k+1]
    raise AssertionError(name)
signatures=("SyncpointManager::ActionHandle SyncpointManager::RegisterAction(",
            "void SyncpointManager::DeregisterAction(",
            "void SyncpointManager::DeregisterGuestAction(",
            "void SyncpointManager::DeregisterHostAction(",
            "void SyncpointManager::IncrementGuest(",
            "void SyncpointManager::IncrementHost(",
            "void SyncpointManager::Increment(",
            "void SyncpointManager::WaitGuest(",
            "void SyncpointManager::WaitHost(",
            "void SyncpointManager::Wait(")
def methods(src):
    return "\n\n".join(extract(src,n) for n in signatures)
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
class SyncpointManager {
public:
 struct RegisteredAction {
    u32 expected_value;
    std::function<void()> action;
    RegisteredAction(u32 v,std::function<void()>&& a)
      :expected_value(v),action(std::move(a)){}
 };
 using ActionHandle=std::list<RegisteredAction>::iterator;
 std::array<std::atomic<u32>,192> syncpoints_guest{},syncpoints_host{};
 std::array<std::list<RegisteredAction>,192> guest_action_storage,host_action_storage;
 std::mutex guard;
 std::condition_variable wait_guest_cv,wait_host_cv;
 template<typename F> ActionHandle RegisterGuestAction(u32 id,u32 value,F&& f) {
    return RegisterAction(syncpoints_guest[id],guest_action_storage[id],
                          value,std::forward<F>(f));
 }
 template<typename F> ActionHandle RegisterHostAction(u32 id,u32 value,F&& f) {
    return RegisterAction(syncpoints_host[id],host_action_storage[id],
                          value,std::forward<F>(f));
 }
 ActionHandle RegisterAction(std::atomic<u32>&,std::list<RegisteredAction>&,
                             u32,std::function<void()>&&);
 void DeregisterAction(std::list<RegisteredAction>&,const ActionHandle&);
 void DeregisterGuestAction(u32,const ActionHandle&);
 void DeregisterHostAction(u32,const ActionHandle&);
 void IncrementGuest(u32);
 void IncrementHost(u32);
 void Increment(std::atomic<u32>&,std::condition_variable&,
                std::list<RegisteredAction>&);
 void WaitGuest(u32,u32);
 void WaitHost(u32,u32);
 void Wait(std::atomic<u32>&,std::condition_variable&,u32);
};
__NATIVE__
int main(){
 SyncpointManager m;
 std::atomic<unsigned> callbacks{},nested{},independent{};
 // The pinned Increment calls its callback while holding the action mutex.
 // This deterministic negative fails instead of deadlocking.
 m.RegisterGuestAction(1,1,[&]{
    assert(m.guard.try_lock());
    m.guard.unlock();
    m.RegisterGuestAction(4,0,[&]{++nested;});
    ++callbacks;
 });
 m.IncrementGuest(1);
 assert(callbacks==1 && nested==1);
 std::vector<u32> ordered;
 m.RegisterGuestAction(2,3,[&]{ordered.push_back(3);});
 m.RegisterGuestAction(2,1,[&]{ordered.push_back(1);});
 m.RegisterGuestAction(2,2,[&]{ordered.push_back(2);});
 auto removed=m.RegisterGuestAction(2,4,[&]{assert(false);});
 m.IncrementGuest(2);
 m.IncrementGuest(2);
 m.IncrementGuest(2);
 m.DeregisterGuestAction(2,removed);
 m.IncrementGuest(2);
 assert((ordered==std::vector<u32>{1,2,3}));
 // On the async GPU renderer path callback work can block. Claiming the
 // entire ready set under guard permits unrelated Host1x work to progress.
 std::mutex mutex;
 std::condition_variable cv;
 bool entered{},released{};
 std::atomic<unsigned> claimed{},cancelled{},progress{};
 // RegisterAction inserts equal thresholds at the front (LIFO).
 // Register the counted callback first, so the blocker becomes first.
 auto ready=m.RegisterGuestAction(5,1,[&]{++claimed;});
 m.RegisterGuestAction(5,1,[&]{
    std::unique_lock lk(mutex);
    entered=true;
    cv.notify_all();
    cv.wait(lk,[&]{return released;});
 });
 auto future=m.RegisterGuestAction(5,3,[&]{++cancelled;});
 std::thread pending([&]{m.IncrementGuest(5);});
 {
    std::unique_lock lk(mutex);
    cv.wait(lk,[&]{return entered;});
 }
 // Preserve same-syncpoint order under concurrent IncrementGuest.
 // A second increment must not run its callback before the blocked first.
 std::atomic<unsigned> same_id{};
 m.RegisterGuestAction(5,2,[&]{
    std::lock_guard lk(mutex);
    assert(released);
    ++same_id;
 });
 std::atomic<bool> same_started{};
 std::thread same_increment([&]{
    same_started.store(true,std::memory_order_release);
    m.IncrementGuest(5);
 });
 while(!same_started.load(std::memory_order_acquire)) std::this_thread::yield();
 std::this_thread::sleep_for(std::chrono::milliseconds(4));
 assert(m.syncpoints_guest[5].load(std::memory_order_acquire)==1);
 assert(same_id==0);
 // The first two actions have been atomically claimed. The third remains
 // cancellable, and a different host syncpoint must not be blocked.
 m.DeregisterGuestAction(5,ready);
 m.DeregisterGuestAction(5,future);
 m.RegisterHostAction(7,1,[&]{++independent;});
 m.IncrementHost(7);
 m.WaitHost(7,1);
 assert(independent==1 && claimed==0 && cancelled==0);
 {
    std::lock_guard lk(mutex);
    released=true;
 }
 cv.notify_all();
 pending.join();
 same_increment.join();
 assert(same_id==1);
 m.IncrementGuest(5);
 m.IncrementGuest(5);
 assert(claimed==1 && cancelled==0);
 assert(m.guest_action_storage[5].empty());
 // Queue reclamation must survive repeated claimed callbacks without
 // missing or double triggering frames.
 for(u32 i=1;i<=256;++i){
    m.RegisterGuestAction(9,i,[&]{++progress;});
    m.IncrementGuest(9);
 }
 assert(progress==256);
 std::printf("N04_HOST1X_INCREMENT_HANDOFF_PASS ordered=3 nested=1 "
             "claimed=1 pending_cancelled=1 independent=1 same_id_serial=1 stress=256\n");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-host1x-handoff-") as tmp:
    for name,src,opt in (("active-O0",ACT,"-O0"),("active-O2",ACT,"-O2"),
                         ("pinned-negative",PIN,"-O0")):
        source=Path(tmp)/(name+".cpp")
        executable=Path(tmp)/name
        source.write_text(CPP.replace("__NATIVE__", (helpers if name!="pinned-negative" else "") + "\n" + methods(src)))
        result=subprocess.run([compiler,"-std=c++20",opt,"-pthread",
                               "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                               "-fno-sanitize-recover=all",str(source),"-o",str(executable)],
                              capture_output=True,text=True,timeout=55)
        assert result.returncode==0,(name,result.stderr[-5000:])
        run=subprocess.run([str(executable)],capture_output=True,text=True,timeout=25)
        if name=="pinned-negative":
            assert run.returncode!=0 and "m.guard.try_lock()" in run.stderr,(
                "pinned source failed to demonstrate guard held",run.stderr[-1400:])
            print("N04_HOST1X_INCREMENT_PINNED_NEGATIVE_PASS guard_blocks_callback")
        else:
            assert run.returncode==0,(name,run.stdout,run.stderr[-3000:])
            print(run.stdout.strip(),name)
print("N04_HOST1X_INCREMENT_GUEST_PROGRESS_UNVERIFIED only_host_scheduling")
