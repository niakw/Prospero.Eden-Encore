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

apply_one "$root/headless/backports/eden-4473-4477.patch" "$eden/.encore-backport-gpu.sha256" validate_gpu
apply_one "$root/headless/backports/eden-4436-spinlock-mutex.patch" "$eden/.encore-backport-4436.sha256" validate_spinlock_mutex
apply_one "$root/headless/backports/eden-fw23-services.patch" "$eden/.encore-backport-fw23.sha256" validate_fw23
apply_one "$root/headless/backports/eden-runtime-hid.patch" "$eden/.encore-backport-runtime-hid.sha256" validate_runtime_hid
apply_one "$root/headless/backports/eden-ps5-hid-watchdog.patch" "$eden/.encore-backport-ps5-hid-watchdog.sha256" validate_ps5_hid_watchdog
