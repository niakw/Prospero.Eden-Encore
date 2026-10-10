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
    local hash recorded
    hash=$(sha256sum "$patch" | awk '{print $1}')
    if [[ -f $receipt ]]; then
        recorded=$(tr -d '\r\n' < "$receipt")
        if [[ $recorded != "$hash" ]]; then
            # The first Nlib identity patch shipped without an HTTP failure reason.
            # Its subsequent revision ONLY adds httplib error reporting, so migrate
            # that single verified old receipt in place. Never reset source or other
            # cached dependencies for this one-line change; unknown revisions fail.
            if [[ $(basename "$patch") == eden-ps5-net-user-agent.patch &&
                  $recorded == 7117c1c3f353157b7fa46a86c6f77226b1183d9b374462cefe8b8dc5f32bf613 ]]; then
                python3 -B "$root/tools/migrate-net-user-agent-cache.py" "$eden"
                "$validator"
                printf '%s\n' "$hash" > "$receipt"
                echo 'Migrated cached Eden HTTP backport in place (no source-cache reset)'
                return
            fi
            if [[ $(basename "$patch") == eden-ps5-bounded-logging.patch ]]; then
                python3 -B "$root/tools/migrate-bounded-logging-cache.py" "$eden"
                "$validator"
                printf '%s\n' "$hash" > "$receipt"
                echo 'Migrated only the known old PS5 logging flush policy in cached Eden source'
                return
            fi
            echo "Backport changed; reset the Eden source cache: $(basename "$patch")" >&2
            exit 1
        fi
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
    'error_events == 1 || error_events % 64 == 0',
    'entry.log_level >= Level::Critical',
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
# FC27 real-hardware log evidence: account open-context panics, unhandled BSD Ioctl,
# and 0x100-vs-0x10 IPv4 IPC writes. Ship only on the exact pinned Eden tree.
validate_fc27_hle_compat() {
python3 - "$eden" <<'PYFC27'
from pathlib import Path
import sys
r=Path(sys.argv[1]); account=(r/'src/core/hle/service/acc/acc.cpp').read_text()
bsd=(r/'src/core/hle/service/sockets/bsd.cpp').read_text()
for marker in ('{130, &ACC_U0::LoadOpenContext, "LoadOpenContext"}',
               'profile_manager->GetStoredOpenedUsers()', 'profile_manager->OpenUser(user_id)'):
    if marker not in account: raise SystemExit(f'FC27 account HLE missing: {marker}')
for marker in ('{19, &BSD_USA::Ioctl, "Ioctl"}',
               'constexpr u32 kFionbio = 0x8004667e;',
               'BuildErrnoResponse(ctx, Errno::INVAL)',
               'write_buffer.resize(guest_addrin.len);'):
    if marker not in bsd: raise SystemExit(f'FC27 BSD HLE missing: {marker}')
if bsd.count('write_buffer.resize(guest_addrin.len);') != 2:
    raise SystemExit('Both getpeername and getsockname require bounded IPv4 writes')
print('FC27 HLE account/Ioctl/bounded IPv4 backport: PASS')
PYFC27
}
apply_one "$root/headless/backports/eden-fc27-hle-compat.patch" "$eden/.encore-backport-fc27-hle.sha256" validate_fc27_hle_compat
# The host launcher owns Nlib/catalog HTTPS. The guest Switch network must not
# resolve or contact EA/Nintendo/any Internet host, including raw-IP traffic.
validate_guest_offline() {
python3 - "$eden" <<'PYOFFLINE'
from pathlib import Path
import sys
r = Path(sys.argv[1])
p = (r / 'src/core/hle/service/sockets/encore_guest_network_policy.h').read_text()
bsd = (r / 'src/core/hle/service/sockets/bsd.cpp').read_text()
dns = (r / 'src/core/hle/service/sockets/sfdnsres.cpp').read_text()
nifm = (r / 'src/core/hle/service/nifm/nifm.cpp').read_text()
if 'inline constexpr bool kGuestNetworkOffline = true;' not in p:
    raise SystemExit('Guest network policy must be immutable offline')
if 'if (Eden::Encore::kGuestNetworkOffline) return {-1, Errno::NOTCONN};' not in bsd:
    raise SystemExit('Guest BSD socket allocation is not blocked')
if dns.count('if (Eden::Encore::kGuestNetworkOffline) return {0, GetAddrInfoError::NODATA};') != 2:
    raise SystemExit('Both guest DNS entry points must be blocked')
for key in ('enable == 0 || Eden::Encore::kGuestNetworkOffline',
            'if (Eden::Encore::kGuestNetworkOffline || !st.connected)',
            'const auto has_connection = !Eden::Encore::kGuestNetworkOffline'):
    if key not in nifm:
        raise SystemExit('Guest NIFM policy missing: ' + key)
print('Encore guest-only DNS/BSD/NIFM offline isolation: PASS')
PYOFFLINE
}
apply_one "$root/headless/backports/eden-ps5-guest-offline.patch" "$eden/.encore-backport-guest-offline.sha256" validate_guest_offline
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
validate_launcher_http_budget() {
    grep -Fq 'const std::size_t timeout_seconds = url == "https://api.nlib.cc" ? 3 : 5;' "$eden/src/common/net/net.cpp" || {
        echo "Launcher network response-time budget missing" >&2; return 1;
    }
}
apply_one "$root/headless/backports/eden-ps5-launcher-fast-http.patch" "$eden/.encore-backport-launcher-http.sha256" validate_launcher_http_budget
apply_one "$root/headless/backports/eden-ps5-bounded-logging.patch" "$eden/.encore-backport-ps5-bounded-logging.sha256" validate_ps5_bounded_logging
validate_ps5_gpu_memory_mapping() {
python3 - "$eden" <<'PYGPU'
from pathlib import Path
import sys
src=(Path(sys.argv[1])/'src/core/device_memory_manager.inc').read_text()
for token in ('invalid.continuity_tracker = 0;', 'valid.continuity_tracker = 0;',
              'entry.continuity_tracker = 0;', 'observed == first_backing + n',
              'tracked_entries[first_page + i].compressed_physical_ptr != backing + i',
              'if (addr >= device_as_size || size > device_as_size - addr)',
              'if (address >= device_as_size) return nullptr;',
              '::Eden::GpuFault::ShouldReportRead()', '::Eden::GpuFault::ShouldReportWrite()'):
    if token not in src:
        raise SystemExit(f'Pinned PS5 GPU memory backport missing: {token}')
if src.count('#ifndef PS5_NATIVE') < 4:
    raise SystemExit('PS5 shared translation-cache bypass absent')
print('PS5 GPU remap/continuity backport: PASS')
PYGPU
}
apply_one "$root/headless/backports/eden-ps5-gpu-memory-mapping.patch" "$eden/.encore-backport-ps5-gpu-memory-mapping.sha256" validate_ps5_gpu_memory_mapping
validate_ps5_gpu_remap_reverse() {
python3 - "$eden" <<'PYREMAP'
from pathlib import Path
import sys
code=(Path(sys.argv[1])/'src/core/device_memory_manager.inc').read_text()
for token in ('previous_physical == replacement_physical',
              'compressed_device_addr.GetAndFault(previous_physical - 1U)',
              'impl->multi_dev_address.Unregister(', '::Eden::GpuFault::remap_replaced.fetch_add',
              'EDEN_GPU_REMAP_REVERSE_MISMATCH'):
    if token not in code: raise SystemExit('GPU remap reverse-index fix missing: '+token)
print('PS5 GPU Map reverse-mapping replacement: PASS')
PYREMAP
}
apply_one "$root/headless/backports/eden-ps5-gpu-remap-reverse.patch" "$eden/.encore-backport-ps5-gpu-remap-reverse.sha256" validate_ps5_gpu_remap_reverse
validate_ps5_gpu_unmap_reverse() {
python3 - "$eden" <<'PYUNMAP'
from pathlib import Path
import sys
code=(Path(sys.argv[1])/'src/core/device_memory_manager.inc').read_text()
for token in ('base_dev != retiring_page', 'EDEN_GPU_UNMAP_REVERSE_MISMATCH',
              'ShouldReportRemapMismatch()'):
    if token not in code: raise SystemExit('PS5 GPU Unmap reverse-map guard missing: '+token)
print('Pinned PS5 GPU reverse-map unmap guard: PASS')
PYUNMAP
}
apply_one "$root/headless/backports/eden-ps5-gpu-unmap-reverse-guard.patch" "$eden/.encore-backport-ps5-gpu-unmap-reverse-guard.sha256" validate_ps5_gpu_unmap_reverse
validate_ps5_gpu_multi_missing() {
python3 - "$eden" <<'PYMULTI'
from pathlib import Path
import sys
s=(Path(sys.argv[1])/'src/core/device_memory_manager.inc').read_text()
for token in ('bool Contains(u32 value, u32 start_entry) const noexcept',
              'steps < storage.size()', 'start_entry > storage.size()',
              'EDEN_GPU_REMAP_MULTI_MISSING', 'EDEN_GPU_UNMAP_MULTI_MISSING'):
    if token not in s: raise SystemExit('PS5 reverse multi-map safe unlink missing: '+token)
print('PS5 multi reverse-map unregistration hardening: PASS')
PYMULTI
}
apply_one "$root/headless/backports/eden-ps5-gpu-multi-missing-guard.patch" "$eden/.encore-backport-ps5-gpu-multi-missing-guard.sha256" validate_ps5_gpu_multi_missing
validate_ps5_guest_mapping_diagnostics() {
python3 - "$eden" <<'PYMAP'
from pathlib import Path
import sys
source=(Path(sys.argv[1])/'src/core/memory.cpp').read_text()
for token in ('EDEN_GUEST_MAP_POINTER_ZERO', 'EDEN_GUEST_MAPPED_NULL_POINTER',
              'ShouldReportGuestMapZero()', 'ShouldReportGuestNullMapped()'):
    if token not in source:
        raise SystemExit('Pinned guest CPU memory diagnostic missing: '+token)
print('PS5 guest page-table storm reports bounded: PASS')
PYMAP
}
apply_one "$root/headless/backports/eden-ps5-guest-mapping-diagnostics.patch" "$eden/.encore-backport-ps5-guest-mapping-diagnostics.sha256" validate_ps5_guest_mapping_diagnostics
validate_ps5_guest_walk_memory() {
python3 - "$eden" <<'PYWALK'
from pathlib import Path
import sys
s=(Path(sys.argv[1])/'src/core/memory.cpp').read_text()
assert 'current_page_table->entries.CommitRegion(page_index, page_index + (size >> YUZU_PAGEBITS) + 1);' in s
assert '// WalkBlock reads PageEntryData; it never writes the page table.' in s
assert 'if (!pointer) {' in s and 'on_unmapped(offset, copy_amount, current_vaddr);' in s
assert 'Preserve the zero-fill / write-discard contract' in s
print('Pinned PS5 guest memory walker: read-only lookup and invalid-pointer guard PASS')
PYWALK
}
apply_one "$root/headless/backports/eden-ps5-guest-walk.patch" "$eden/.encore-backport-ps5-guest-walk.sha256" validate_ps5_guest_walk_memory
validate_ps5_guest_zero_alias() {
python3 - "$eden" <<'PYALIAS'
from pathlib import Path
import sys
s=(Path(sys.argv[1])/'src/core/memory.cpp').read_text()
for token in ('IsDirectBackingAlias(u64 address, std::size_t bytes) const',
              'GetIntendedMemorySize()', 'guest_alias_mapped.fetch_add',
              'guest_alias_access.fetch_add', 'return reinterpret_cast<u8*>(vaddr)',
              'on_memory(offset, copy_amount, reinterpret_cast<u8*>(current_vaddr))'):
    if token not in s:
        raise SystemExit(f'PS5 delta-zero guest pointer alias recovery missing: {token}')
print('Pinned PS5 guest delta-zero pointer alias guard: PASS')
PYALIAS
}
apply_one "$root/headless/backports/eden-ps5-guest-zero-alias.patch" "$eden/.encore-backport-ps5-guest-zero-alias.sha256" validate_ps5_guest_zero_alias
validate_ps5_guest_span() {
python3 - "$eden" <<'PYSPAN'
from pathlib import Path
import sys
source=(Path(sys.argv[1])/'src/core/memory.cpp').read_text()
for needed in ('(addr + size - 1) >> YUZU_PAGEBITS',
               'if (!size || !AddressSpaceContains(*current_page_table, addr, size))',
               'if (p != delta || t != type || b != block) return nullptr;',
               'static_cast<const Impl&>(*this).GetSpan(addr, size)'):
    if needed not in source: raise SystemExit('PS5 guest span validation missing: '+needed)
print('Pinned PS5 GetSpan correct end page and contiguous page guard PASS')
PYSPAN
}
apply_one "$root/headless/backports/eden-ps5-guest-span.patch" "$eden/.encore-backport-ps5-guest-span.sha256" validate_ps5_guest_span
# Citron fixes inform this host-worker SM/audctl proposal. It compiles on the
# pinned Eden source, but PS5 service-init/shutdown behavior is not yet proven.
# Keep it OFF in the baseline; qualify with a separate controlled HLE A/B.
if [[ ${EDEN_EXPERIMENTAL_SM_HOST_WAIT:-OFF} == ON ]]; then
    apply_one "$root/headless/backports/eden-sm-host-wait.patch" "$eden/.encore-backport-sm-host-wait.sha256" validate_sm_host_wait
fi
