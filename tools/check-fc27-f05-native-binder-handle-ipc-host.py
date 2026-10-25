#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05: source-extracted IHOSBinderDriver GetNativeHandle -> producer KEvent.

Executes real Binder IPC handler, BufferQueueProducer::GetNativeHandle and
ProducerReleaseWake C++ against a mock service registry, handle copy and
KReadableEvent. Validates handle identity, rejected IDs, level coalescing,
reset/rearm and producer shutdown. Real HIPC dispatch, guest kernel waiter,
GPU and FC27 are outside this host fixture.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BINDER=(ROOT/"vendor/sources/eden/src/core/hle/service/nvnflinger/hos_binder_driver.cpp").read_text()
PRODUCER=(ROOT/"vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
CMAKE=(ROOT/"headless/CMakeLists.txt").read_text()
assert "EDEN_MAINTAINED_PROFILE_DEQUEUE" in CMAKE

def method(src,signature):
    assert src.count(signature)==1,("source drift",signature)
    at=src.index(signature)
    opening=src.index("{",at)
    depth=0
    for i in range(opening,len(src)):
        if src[i]=="{":depth+=1
        elif src[i]=="}":
            depth-=1
            if depth==0:return src[at:i+1]
    raise AssertionError("unbalanced source "+signature)

native_ipc=method(BINDER,"Result IHOSBinderDriver::GetNativeHandle(")
native_producer=method(PRODUCER,"Kernel::KReadableEvent* BufferQueueProducer::GetNativeHandle(")
start="class ProducerReleaseWake final : public IProducerListener {"
assert PRODUCER.count(start)==1
i=PRODUCER.index(start)
native_wake=PRODUCER[i:PRODUCER.index("\n};",i)+3]
assert "m_server->TryGetBinder(binder_id)" in native_ipc
assert "R_UNLESS(native_handle != nullptr, ResultUnknown);" in native_ipc
assert "*out_handle = binder->GetNativeHandle(type_id);" in native_ipc
assert "return &buffer_wait_event->GetReadableEvent();" in native_producer
assert "event->Signal(kernel);" in native_wake

cpp=r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <unordered_map>
using s32=std::int32_t;
using u32=std::uint32_t;
enum class Result{Success,Unknown};
constexpr Result ResultUnknown=Result::Unknown;
#define R_UNLESS(expr,code) if(!(expr)) return code
#define R_SUCCEED() return Result::Success
#define LOG_DEBUG(...) ((void)0)
namespace Kernel {
struct KernelCore{};
class KReadableEvent {
 bool signaled{};
public:
 unsigned transitions{};
 unsigned resets{};
 void Signal(KernelCore&) {
  if(!signaled){signaled=true;++transitions;}
 }
 bool IsSignaled()const{return signaled;}
 void Reset(){assert(signaled);signaled=false;++resets;}
};
class KEvent {
 KReadableEvent readable{};
public:
 KReadableEvent& GetReadableEvent(){return readable;}
 void Signal(KernelCore& k){readable.Signal(k);}
};
}
template<typename T>struct OutCopyHandle {
 T** output{};
 T*& operator*(){assert(output);return *output;}
};
namespace Service::android {
class IBinder {
public:
 virtual ~IBinder()=default;
 virtual Kernel::KReadableEvent* GetNativeHandle(u32)=0;
};
class IProducerListener{
public:
 virtual ~IProducerListener()=default;
 virtual void OnBufferReleased()=0;
};
class BufferQueueProducer final : public IBinder {
public:
 Kernel::KEvent* buffer_wait_event{};
 unsigned handle_requests{};
 explicit BufferQueueProducer(Kernel::KEvent* e):buffer_wait_event(e){}
 Kernel::KReadableEvent* GetNativeHandle(u32 type_id) override;
};
__NATIVE_PRODUCER__
__NATIVE_WAKE__
}
namespace Service::Nvnflinger {
struct HosBinderDriverServer {
 std::unordered_map<s32,std::shared_ptr<Service::android::IBinder>> table{};
 unsigned lookups{};
 std::shared_ptr<Service::android::IBinder> TryGetBinder(s32 id) {
  ++lookups;
  const auto it=table.find(id);
  return it==table.end()?nullptr:it->second;
 }
};
class IHOSBinderDriver {
 std::shared_ptr<HosBinderDriverServer> m_server;
public:
 explicit IHOSBinderDriver(std::shared_ptr<HosBinderDriverServer> s):m_server(std::move(s)){}
 Result GetNativeHandle(s32,u32,OutCopyHandle<Kernel::KReadableEvent>);
};
__NATIVE_IPC__
}
int main() {
 Kernel::KernelCore kernel;
 Kernel::KEvent event;
 auto server=std::make_shared<Service::Nvnflinger::HosBinderDriverServer>();
 auto producer=std::make_shared<Service::android::BufferQueueProducer>(&event);
 server->table.emplace(77,producer);
 Service::Nvnflinger::IHOSBinderDriver ipc{server};
 Kernel::KReadableEvent* guest_handle=nullptr;
 OutCopyHandle<Kernel::KReadableEvent> copy{&guest_handle};
 assert(ipc.GetNativeHandle(66,0,copy)==Result::Unknown);
 assert(guest_handle==nullptr && server->lookups==1);
 assert(ipc.GetNativeHandle(77,0,copy)==Result::Success);
 assert(guest_handle==&event.GetReadableEvent());
 auto wake=std::make_shared<Service::android::ProducerReleaseWake>(&event,kernel);
 // Guest obtains its copy handle before producer->consumer releases frames.
 for(int i=0;i<260;++i) {
  assert(!guest_handle->IsSignaled());
  wake->OnBufferReleased();
  assert(guest_handle->IsSignaled());
  wake->OnBufferReleased();
  assert(guest_handle->transitions==static_cast<unsigned>(i+1));
  guest_handle->Reset();
 }
 assert(guest_handle->resets==260);
 assert(guest_handle->transitions==260);
 Kernel::KReadableEvent* second_handle=nullptr;
 OutCopyHandle<Kernel::KReadableEvent> second{&second_handle};
 assert(ipc.GetNativeHandle(77,1,second)==Result::Success);
 assert(second_handle==guest_handle);
 // Handle copies reference the same level-triggered kernel object.
 wake->OnBufferReleased();
 assert(second_handle->IsSignaled() && guest_handle->IsSignaled());
 second_handle->Reset();
 wake->Stop();
 wake->OnBufferReleased();
 assert(!guest_handle->IsSignaled());
 server->table.erase(77);
 assert(ipc.GetNativeHandle(77,0,copy)==Result::Unknown);
 assert(producer->handle_requests==0); // source method does not use mock counter
 std::puts("F05_NATIVE_BINDER_HANDLE_IPC_PASS cycles=260 copied_handle_identity=1 "
           "unknown_binder_rejected=1 level_coalescing=1 reset_rearm=260 "
           "same_event_across_copies=1 stopped_callback_quiet=1 "
           "scope=shipping_binder_ipc_and_producer_methods_mock_handle_table");
}
""".replace("__NATIVE_IPC__",native_ipc).replace(
    "__NATIVE_PRODUCER__",native_producer).replace("__NATIVE_WAKE__",native_wake)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f05-binder-handle-") as tmp:
    src=Path(tmp)/"binder.cpp"
    src.write_text(cpp)
    for mode in ("-O0","-O2"):
        exe=Path(tmp)/("binder"+mode)
        b=subprocess.run([compiler,"-std=c++20",mode,"-Wall","-Wextra","-Werror",
                          "-Wno-unused-parameter","-fsanitize=undefined",
                          "-fno-sanitize-recover=all",str(src),"-o",str(exe)],
                         capture_output=True,text=True,timeout=90)
        assert b.returncode==0,(mode,b.stderr[-6000:])
        r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        assert r.returncode==0,(mode,r.stderr[-6000:],r.stdout)
        assert r.stdout.count("F05_NATIVE_BINDER_HANDLE_IPC_PASS") == 1
        print(mode,r.stdout.strip(),flush=True)
print("F05_REAL_HIPC_DISPATCH_GUEST_WAIT_AND_FC27_PROGRESS_NOT_PROVEN")
