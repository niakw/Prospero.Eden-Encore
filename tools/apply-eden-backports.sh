#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Apply Encore's audited backports to the exact Eden source snapshot.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
eden=${1:?usage: apply-eden-backports.sh <eden-source>}
expected=5f142c7926d0c7fcbbd0ce30794d72f638a43b2a
[[ -f $eden/CMakeLists.txt ]] || { echo "Eden source missing: $eden" >&2; exit 1; }
[[ -f $eden/GIT-COMMIT ]] || { echo "Eden pin receipt missing: $eden/GIT-COMMIT" >&2; exit 1; }
[[ $(tr -d '\r\n' < "$eden/GIT-COMMIT") == "$expected" ]] || {
    echo "Encore backports require Eden $expected" >&2; exit 1;
}

validate_gpu() {
python3 - "$eden" <<'PY'
from pathlib import Path
import sys
r=Path(sys.argv[1])
checks={
 'src/video_core/dma_pusher.cpp':['kepler_payload','macro_payload','dma_state.method_count'],
 'src/video_core/engines/kepler_compute.cpp':['upload_dirty = current_dirty','data.was_dirty || source_dirty'],
 'src/video_core/engines/kepler_compute.h':['bool upload_dirty{};','bool was_dirty;'],
 'src/video_core/buffer_cache/buffer_cache.h':['SynchronizeBufferWrites','gpu_modified_ranges.ForEachInRange','runtime.IsFree(buffer_tick)'],
 'src/video_core/buffer_cache/buffer_cache_base.h':['SynchronizeBufferWrites','needs_sync = false'],
 'src/video_core/fence_manager.h':['IsGPUFenceBehaviorAccurate()'],
 'src/video_core/renderer_vulkan/vk_buffer_cache.cpp':['return scheduler.CurrentTick();','return scheduler.IsFree(tick);'],
}
for rel, needles in checks.items():
    text=(r/rel).read_text()
    for n in needles:
        if n not in text: raise SystemExit(f'GPU backport missing from {rel}: {n}')
if 'enable_gpu_buffer_readback' in (r/'src/common/settings.h').read_text():
    raise SystemExit('obsolete GPU buffer readback setting survived')
print('Eden audited GPU backports #4473/#4477: PASS')
PY
}

validate_fw23() {
python3 - "$eden" <<'PY'
from pathlib import Path
import sys
r=Path(sys.argv[1])
checks={
 'src/core/hle/api_version.h':['HOS_VERSION_MAJOR = 23','DISPLAY_VERSION[0x18] = "23.0.0"'],
 'src/core/hle/service/bpc/bpc.cpp':['"bpc:ams"'],
 'src/core/hle/service/nfp/nfp.cpp':['StartDetectionWithFilter'],
 'src/core/hle/service/ns/application_manager_interface.cpp':['Unknown4105'],
 'src/core/hle/service/ns/read_only_application_control_data_interface.cpp':['{23, D<&IReadOnlyApplicationControlDataInterface::GetApplicationControlData3>'],
 'src/core/hle/service/olsc/transfer_task_list_controller.cpp':['GetTransferTaskProgress'],
 'src/core/hle/service/sm/sm.cpp':['max_sessions'],
}
for rel, needles in checks.items():
    text=(r/rel).read_text()
    for n in needles:
        if n not in text: raise SystemExit(f'FW23/service backport missing from {rel}: {n}')
print('Eden audited FW23/service/max_sessions backports: PASS')
PY
}

validate_spinlock_mutex() {
python3 - "$eden" <<'PY2'
from pathlib import Path
import sys
r=Path(sys.argv[1])
thread=(r/'src/core/hle/kernel/k_thread.h').read_text()
slab=(r/'src/core/hle/kernel/k_slab_heap.h').read_text()
cmake=(r/'src/common/CMakeLists.txt').read_text()
for rel,text,needle in [
    ('k_thread.h',thread,'std::mutex m_context_guard{};'),
    ('k_slab_heap.h',slab,'std::mutex m_lock;'),
]:
    if needle not in text: raise SystemExit(f'Eden #4436 missing from {rel}: {needle}')
if 'common/spin_lock.h' in thread or 'common/spin_lock.h' in slab:
    raise SystemExit('Eden #4436 incomplete: kernel still includes Common::SpinLock')
if 'spin_lock.h' in cmake:
    raise SystemExit('Eden #4436 incomplete: spin_lock.h still registered in common CMake')
print('Eden audited kernel mutex backport #4436: PASS')
PY2
}

validate_runtime_hid() {
python3 - "$eden" <<'PY'
from pathlib import Path
import sys
r=Path(sys.argv[1])
checks={
 'src/core/frontend/applets/controller.cpp':['keep_connected','max_supported_players'],
 'src/core/hle/kernel/k_scheduler.cpp':['m_context_guard.try_lock()'],
 'src/core/hle/service/am/frontend/applets.cpp':['std::erase(caller_applet->child_applets'],
 'src/core/hle/service/am/service/library_applet_accessor.cpp':['RequestFocusStateChangedNotification'],
 'src/hid_core/resources/npad/npad.cpp':['ReadCurrentEntry().state.sampling_number'],
 'src/video_core/control/channel_state_cache.h':['P* channel_state = nullptr;'],
}
for rel, needles in checks.items():
    text=(r/rel).read_text()
    for n in needles:
        if n not in text: raise SystemExit(f'Runtime/HID backport missing from {rel}: {n}')
print('Eden audited runtime/HID backports: PASS')
PY
}

apply_one() {
    local patch=$1 receipt=$2 validator=$3
    [[ -s $patch ]] || { echo "Backport patch missing: $patch" >&2; exit 1; }
    local hash
    hash=$(sha256sum "$patch" | awk '{print $1}')
    if [[ -f $receipt ]]; then
        [[ $(tr -d '\r\n' < "$receipt") == "$hash" ]] || {
            echo "Backport changed; reset the Eden source cache: $(basename "$patch")" >&2; exit 1;
        }
        "$validator"
        return
    fi
    if "$validator" >/dev/null 2>&1; then
        printf '%s\n' "$hash" > "$receipt"
        "$validator"
        return
    fi
    (cd "$eden" && git apply --check "$patch") || {
        echo "Pinned Eden source no longer matches $(basename "$patch")" >&2; exit 1;
    }
    (cd "$eden" && git apply "$patch")
    "$validator"
    printf '%s\n' "$hash" > "$receipt"
}

validate_ps5_hid_watchdog() {
python3 - "$eden" <<'PY'
from pathlib import Path
import sys
text=(Path(sys.argv[1])/'src/hid_core/resources/npad/npad.cpp').read_text()
for needle in ['EDEN_HID_NPAD update={}', 'eden_watchdog_sample', 'eden_watchdog_buttons']:
    if needle not in text: raise SystemExit(f'PS5 HID watchdog missing: {needle}')
print('Encore PS5 HID progress watchdog: PASS')
PY
}


validate_ps5_bounded_logging() {
python3 - "$eden" <<'PYLOG'
from pathlib import Path
import sys
text=(Path(sys.argv[1])/'src/common/logging.cpp').read_text()
for needle in [
    'constexpr auto write_limit = 8_MiB;',
    'void RotatePs5() noexcept',
    'log tail rotated; storage remains bounded',
    'first_filename += ".first.txt"',
    'file->SetSize(0)',
    'FS::SeekOrigin::SetOrigin',
]:
    if needle not in text:
        raise SystemExit(f'Encore bounded PS5 Eden logging missing: {needle}')
ps5=text[text.index('#ifdef PS5_NATIVE', text.index('using namespace Common::Literals;')):
         text.index('#else', text.index('#ifdef PS5_NATIVE', text.index('using namespace Common::Literals;')))]
if 'enabled = false' in ps5:
    raise SystemExit('PS5 log cap must rotate, not disable logging')
print('Encore bounded rotating PS5 Eden logging: PASS')
PYLOG
}

validate_ps5_net_user_agent() {
python3 - "$eden" <<'PYNET'
from pathlib import Path
import sys
text=(Path(sys.argv[1])/'src/common/net/net.cpp').read_text()
for needle in ['Prospero.Eden-Encore/1', 'request.headers.emplace("User-Agent"', 'request.headers.emplace("Accept"',
               'httplib::to_string(result.error())']:
    if needle not in text: raise SystemExit(f'Encore PS5 HTTP identity missing: {needle}')
print('Encore PS5 HTTP identity backport: PASS')
PYNET
}

validate_dummy_thread_waits() {
python3 - "$eden" <<'PYDW'
from pathlib import Path
import sys
r=Path(sys.argv[1])
lock=(r/'src/core/hle/kernel/k_light_lock.cpp').read_text()
thread=(r/'src/core/hle/kernel/k_thread.cpp').read_text()
for needle in [
    'cur_thread->RequestDummyThreadWait(m_kernel);',
    'cur_thread->GetState() != ThreadState::Waiting || cur_thread->IsDummyThread()',
    'cur_thread->ClearWaitQueue();',
]:
    if needle not in lock: raise SystemExit(f'Dummy-thread KLightLock wait fix missing: {needle}')
for needle in [
    'if (m_wait_queue != nullptr)',
    'this->SetWaitResult(wait_result);',
    'this->SetState(kernel, ThreadState::Runnable);',
]:
    if needle not in thread: raise SystemExit(f'Dummy-thread EndWait fix missing: {needle}')
print('Eden dummy host-thread kernel waits backport: PASS')
PYDW
}

validate_dynarmic_icache() {
python3 - "$eden" <<'PYIC'
from pathlib import Path
import sys
r=Path(sys.argv[1])
a64=(r/'src/core/arm/dynarmic/arm_dynarmic_64.cpp').read_text()
a32=(r/'src/core/arm/dynarmic/arm_dynarmic_32.cpp').read_text()
for needle in [
    '#include "core/arm/debug.h"',
    'Core::InvalidateInstructionCacheRange(m_process, cache_line_start, ICACHE_LINE_SIZE);',
    'case Dynarmic::A64::InstructionCacheOperation::InvalidateAllToPoUInnerSharable:',
]:
    if needle not in a64: raise SystemExit(f'Dynarmic A64 i-cache coherence missing: {needle}')
for text,name in ((a64,'A64'),(a32,'A32')):
    marker='void ArmDynarmic'+name[1:]+'::InvalidateCacheRange'
    block=text[text.index(marker):text.index('}', text.index(marker))+1]
    if 'm_cb->last_code_addr = u64(-1);' not in block:
        raise SystemExit(f'Dynarmic {name} cached code page survives range invalidation')
print('Eden Dynarmic cross-core i-cache coherence backport: PASS')
PYIC
}

apply_one "$root/headless/backports/eden-4473-4477.patch" "$eden/.encore-backport-gpu.sha256" validate_gpu
apply_one "$root/headless/backports/eden-4436-spinlock-mutex.patch" "$eden/.encore-backport-4436.sha256" validate_spinlock_mutex
apply_one "$root/headless/backports/eden-fw23-services.patch" "$eden/.encore-backport-fw23.sha256" validate_fw23
apply_one "$root/headless/backports/eden-runtime-hid.patch" "$eden/.encore-backport-runtime-hid.sha256" validate_runtime_hid
# Quarantine: this dummy-thread wait proposal can clear a wait-queue pointer
# while ThreadState::Waiting still holds. NotifyAvailable/CancelWait in pinned Eden
# may dereference that pointer. A patch-apply test is NOT a correctness test.
# Keep the patch for isolated analysis; never ship it automatically.
if [[ ${EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS:-OFF} == ON ]]; then
    apply_one "$root/headless/backports/eden-dummy-thread-waits.patch" "$eden/.encore-backport-dummy-thread-waits.sha256" validate_dummy_thread_waits
fi
# Cross-core guest I-cache invalidation is separate from FC27's proven waits.
# Qualify as its own controlled A/B, not in the first stability baseline.
if [[ ${EDEN_EXPERIMENTAL_ICACHE_COHERENCE:-OFF} == ON ]]; then
    apply_one "$root/headless/backports/eden-dynarmic-icache-coherence.patch" "$eden/.encore-backport-dynarmic-icache.sha256" validate_dynarmic_icache
fi
validate_sm_host_wait() {
python3 - "$eden" <<'PYSM'
from pathlib import Path
import sys
r=Path(sys.argv[1])
sm=(r/'src/core/hle/service/sm/sm.h').read_text()
audio=(r/'src/core/hle/service/audio/audio_controller.cpp').read_text()
audio_h=(r/'src/core/hle/service/audio/audio_controller.h').read_text()
for needle in ['Kernel::GetCurrentThread(kernel).IsDummyThread()', 'std::this_thread::sleep_for(1ms)',
               'SessionRequestHandlerFactory factory', 'std::scoped_lock']:
    if needle not in sm:
        raise SystemExit(f'Eden host-thread-safe blocking GetService missing: {needle}')
if 'kernel.IsShuttingDown()' in sm:
    raise SystemExit('blocking GetService must not return nullptr merely because shutdown began')
if 'm_set_sys =\n        system.ServiceManager().GetService' in audio:
    raise SystemExit('audctl constructor still blocks on set:sys')
for needle in ['IAudioController::GetSetSys()', 'std::call_once(m_set_sys_once',
               'GetSetSys()->GetAudioOutputMode', 'GetSetSys()->SetAudioOutputMode']:
    if needle not in audio:
        raise SystemExit(f'lazy audctl set:sys lookup missing: {needle}')
for needle in ['std::once_flag m_set_sys_once', 'GetSetSys();']:
    if needle not in audio_h:
        raise SystemExit(f'lazy audctl declaration missing: {needle}')
print('Eden host-thread-safe service waits + lazy audctl lookup: PASS')
PYSM
}

apply_one "$root/headless/backports/eden-ps5-hid-watchdog.patch" "$eden/.encore-backport-ps5-hid-watchdog.sha256" validate_ps5_hid_watchdog
apply_one "$root/headless/backports/eden-ps5-net-user-agent.patch" "$eden/.encore-backport-ps5-net-user-agent.sha256" validate_ps5_net_user_agent
apply_one "$root/headless/backports/eden-ps5-bounded-logging.patch" "$eden/.encore-backport-ps5-bounded-logging.sha256" validate_ps5_bounded_logging
# Citron fixes inform this host-worker SM/audctl proposal. It compiles on the
# pinned Eden source, but PS5 service-init/shutdown behavior is not yet proven.
# Keep it OFF in the baseline; qualify with a separate controlled HLE A/B.
if [[ ${EDEN_EXPERIMENTAL_SM_HOST_WAIT:-OFF} == ON ]]; then
    apply_one "$root/headless/backports/eden-sm-host-wait.patch" "$eden/.encore-backport-sm-host-wait.sha256" validate_sm_host_wait
fi
