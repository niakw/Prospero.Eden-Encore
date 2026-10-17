#!/usr/bin/env python3
"""Do not confuse offline source closure with elimination of source rewrites.

This is a fail-on-regression, NOT a claim that every native source already
builds without a CMake-generated derived unit.
"""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
vendor = root / "vendor"
sources = vendor / "sources"
active = vendor / "encore-active"
c = (root / "headless/CMakeLists.txt").read_text()
vulkan = (root / "headless/vulkan.cmake").read_text()
deps = json.loads((root / "tools/deps.json").read_text())["items"]
root_names = {entry.name for entry in sources.iterdir() if entry.is_dir()}
for dep in deps:
    name = dep["name"]
    if name == "pacbrew":
        assert (vendor / "objects/pacbrew").is_dir(), "pacbrew binary archive not vendored"
    else:
        assert name in root_names, f"missing pinned dependency source: {name}"
for extra in ("eden-cpm", "boilerplate-setup-0"):
    assert extra in root_names, extra
fork_names = {entry.name for entry in active.iterdir() if entry.is_dir()}
for name in ("eden-backports", "eden-build", "eden-core", "eden-gpu",
             "eden-surface-lifecycle", "eden-vulkan", "ps5-mesa"):
    assert name in fork_names, f"missing active patched tree: {name}"
assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in vulkan
assert (active/"eden-build/src/CMakeLists.txt").is_file(), "missing maintained native CMake"
assert 'execute_process(COMMAND python3 "${PORT_ROOT}/tools/prepare-vulkan-port.py"' not in vulkan
baseline = {"write_derived(": 77, "file(READ": 87, "string(REPLACE": 225}
counts = {name: c.count(name) for name in baseline}
# One source-pinned fatal GPU worker wait needs a checked CMake input and
# two exact-method rewrites. Do not relax the historical ceilings for any
# other vendor-derived source. Each exception must occur exactly once.
approved_sync = {
    "file(READ": (
        'file(READ "${EDEN_PORT_DIR}/gpu_sync_failure_wait.inc" gpu_sync_wait_replacement)',
    ),
    "string(REPLACE": (
        'string(REPLACE "${gpu_sync_wait_original}" "${gpu_sync_wait_replacement}"',
        'string(REPLACE "${gpu_tick_lock_original}" "${gpu_tick_lock_safe}"',
        'string(REPLACE "${gpu_block_wait_original}" "${gpu_block_wait_checked}"',
        'string(REPLACE "${gpu_enqueue_fence_original}" "${gpu_enqueue_fence_atomic}"',
        'string(REPLACE "${gpu_read_capture_original}"',
        # Native memory is already a derived translation unit for the
        # per-title unmapped-access limiter and optional checked fastmem.
        # Preserve its pinned 2-KiB dirty-collector correction as ONE
        # audited exception, never an anonymous increase of the budget.
        'string(REPLACE "${eden_dirty_raw}" [=[',
        # This pinned native read-only exception prevents out-of-bounds
        # guest-core indexing by auxiliary host threads.
        'string(REPLACE "${eden_read_original}" "${eden_read_native}"',
        # End-exclusive guest spans must not probe a one-past-last page.
        'string(REPLACE "${eden_span_original}" [=[',
        # Two exact, drift-checked native command queue slot lifecycle rewrites.
        # Count both separately; leave the historical <=225 ceiling unchanged.
        'string(REPLACE "${queue_slot_construct}" "__ENCORE_GPU_QUEUE_SLOT__"',
        'string(REPLACE "__ENCORE_GPU_QUEUE_SLOT__" "${queue_slot_repair}"',
    ),
}
# The dirty-range rewrite is allowed only while the source-derived native
# gate and its sanitizer regression remain present and wired to CI.
assert c.count("Pinned native GPUDirty Collect call changed") == 1
assert c.count("gpu_dirty_managers[core].Collect(subaddress, span);") == 1
assert c.count("Pinned native guest CPU read scratch/slot contract changed") == 1
assert c.count("Pinned native guest span page-boundary contract changed") == 1
assert 'write_derived("${eden_gpu_span_tu}"' not in c
assert 'native_gpu_granular_bounds.cmake' not in c
assert not (root / "headless/native_gpu_granular_bounds.cmake").exists()
assert c.count("Pinned GPU read callback lifetime changed") == 1
assert c.count('RequestSyncOperation([this, raster_area]() {') == 1
assert (root / "tools/check-native-gpu-read-capture-host.py").is_file()
assert "python3 -B tools/check-native-gpu-read-capture-host.py" in (
    root / ".github/workflows/encore-core-preflight.yml").read_text()
assert c.count('list(REMOVE_ITEM video_sources "memory_manager.cpp")') == 1
assert c.count('list(APPEND video_sources "${EDEN_NATIVE_GPU_MEMORY_MANAGER}")') == 1
assert (root / "tools/check-native-gpu-span-range-host.py").is_file()
assert "python3 -B tools/check-native-gpu-span-range-host.py" in (
    root / ".github/workflows/encore-core-preflight.yml").read_text()
assert c.count("const auto end_page = (addr + size - 1) >> YUZU_PAGEBITS;") == 1
assert (root / "tools/check-native-guest-span-host.py").is_file()
assert "python3 -B tools/check-native-guest-span-host.py" in (
    root / ".github/workflows/encore-core-preflight.yml").read_text()
assert c.count("thread_local Common::ScratchBuffer<u32> read_scratch;") == 1
assert c.count("VideoCore::RasterizerDownloadArea auxiliary_read_area{};") == 1
assert (root / "tools/check-native-gpu-read-core-host.py").is_file()
assert "python3 -B tools/check-native-gpu-read-core-host.py" in (
    root / ".github/workflows/encore-core-preflight.yml").read_text()
assert (root / "tools/check-native-gpu-dirty-subregion-host.py").is_file()
assert "python3 -B tools/check-native-gpu-dirty-subregion-host.py" in (
    root / ".github/workflows/encore-core-preflight.yml").read_text()
approved_counts = {}
for name, fragments in approved_sync.items():
    for fragment in fragments:
        assert c.count(fragment) == 1, f"missing pinned GPU sync generation: {fragment}"
    approved_counts[name] = len(fragments)
for name, limit in baseline.items():
    effective_count = counts[name] - approved_counts.get(name, 0)
    assert effective_count <= limit, (
        f"new CMake source override added: {name}: "
        f"baseline={effective_count} > {limit}, total={counts[name]}; "
        "integrate sources under vendor/encore-active instead"
    )

# Regression oracle: the maintained diagnostic IFile TU must be exactly the
# old pinned file + its former CMake replacement (apart from the normalized
# include path); prevent silent semantic drift while removing string rewrites.
fs_rel = "core/hle/service/filesystem/fsp/fs_i_file.cpp"
fs_pinned = (sources / "eden/src" / fs_rel).read_text()
fs_maintained = (active / "eden-core/src" / fs_rel).read_text()
fs_old = """    R_RETURN(
        backend->Read(reinterpret_cast<size_t*>(out_size.Get()), offset, out_buffer.data(), size));"""
fs_new = """    const auto fs_start = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed) ? ::Eden::Performance::NowNs() : 0;
    const Result fs_result =
        backend->Read(reinterpret_cast<size_t*>(out_size.Get()), offset, out_buffer.data(), size);
    if (fs_start) {
        ::Eden::Performance::AddSince(::Eden::Performance::guest_fs_file, fs_start);
        ::Eden::Performance::guest_fs_file_bytes.fetch_add(static_cast<unsigned long long>(*out_size.Get()), std::memory_order_relaxed);
    // Diagnostic only: avoid formatting every file read while quiet.
        LOG_WARNING(Service_FS, "EDEN_FS_FILE_READ offset={:#x} size={} read={} result={:#x} ns={}", offset, size, *out_size.Get(), fs_result.raw, ::Eden::Performance::NowNs() - fs_start);
    }
    R_RETURN(fs_result);"""
assert fs_pinned.count(fs_old) == 1
assert fs_maintained == '#include "performance.h"\n' + fs_pinned.replace(fs_old, fs_new), (
    "Maintained IFile profile TU diverges from the already-audited generated source")
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_FS_FILE}")') == 1
assert 'list(REMOVE_ITEM core_sources "hle/service/filesystem/fsp/fs_i_file.cpp")' in c
assert 'target_include_directories(core PRIVATE "${EDEN_PORT_DIR}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/fs_i_file.cpp"' not in c
assert "fs_file_source" not in c

storage_rel = "core/hle/service/filesystem/fsp/fs_i_storage.cpp"
storage_pinned = (sources / "eden/src" / storage_rel).read_text()
storage_maintained = (active / "eden-core/src" / storage_rel).read_text()
storage_old = "    backend->Read(out_bytes.data(), length, offset);"
storage_new = """    const auto fs_start = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed) ? ::Eden::Performance::NowNs() : 0;
    const auto fs_read = backend->Read(out_bytes.data(), length, offset);
    if (fs_read != static_cast<std::size_t>(length))
        LOG_ERROR(Service_FS, "EDEN_FS_SHORT_STORAGE offset={:#x} length={} read={} size={}", offset, length, fs_read, backend->GetSize());
    if (fs_start) {
        ::Eden::Performance::AddSince(::Eden::Performance::guest_fs_storage, fs_start);
        ::Eden::Performance::guest_fs_storage_bytes.fetch_add(static_cast<unsigned long long>(length), std::memory_order_relaxed);
    }"""
assert storage_pinned.count(storage_old) == 1
assert storage_maintained == '#include "performance.h"\n' + storage_pinned.replace(storage_old, storage_new), (
    "Maintained IStorage profile TU diverges from the earlier CMake-generated source")
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_FS_STORAGE}")') == 1
assert 'write_derived("${PORT_BUILD_DIR}/fs_i_storage.cpp"' not in c
assert "fs_storage_source" not in c
assert counts["write_derived("] <= 63, counts
print("VENDOR_MAINTAINED_FS_ISTORAGE_PARITY_PASS: read, short read, quiet policy")


# FS open diagnostics used to be a CMake loop patching three calls.
# Compare maintained C++ with that exact previous generated content.
fs_system_rel = "core/hle/service/filesystem/fsp/fs_i_filesystem.cpp"
fs_system_pinned = (sources / "eden/src" / fs_system_rel).read_text()
fs_system_maintained = (active / "eden-core/src" / fs_system_rel).read_text()
fs_system_expected = '#include "performance.h"\n' + fs_system_pinned
fs_system_calls = (
    ("file", """backend->OpenFile(&vfs_file, FileSys::Path(path->str),
                            static_cast<FileSys::OpenMode>(mode))"""),
    ("directory", """backend->OpenDirectory(&vfs_dir, FileSys::Path(path->str),
                                 static_cast<FileSys::OpenDirectoryMode>(mode))"""),
    ("entry", "backend->GetEntryType(&vfs_entry_type, FileSys::Path(path->str))"),
)
for kind, expression in fs_system_calls:
    before = f"    R_TRY({expression});"
    after = (f"    const Result fs_open_result = {expression};\n"
             "    if (::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed))\n"
             f'        LOG_WARNING(Service_FS, "EDEN_FS_OPEN kind={kind} path={{}} result={{:#x}}", path->str, fs_open_result.raw);\n'
             "    R_TRY(fs_open_result);")
    assert fs_system_expected.count(before) == 1, ("unpinned FS-open call", kind)
    fs_system_expected = fs_system_expected.replace(before, after)
assert fs_system_maintained == fs_system_expected, (
    "Maintained IFileSystem diagnostic diverges from former CMake-generated TU")
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_FS_SYSTEM}")') == 1
assert c.count('list(REMOVE_ITEM core_sources "hle/service/filesystem/fsp/fs_i_filesystem.cpp")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_FS_SYSTEM}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/fs_i_filesystem.cpp"' not in c
assert "fs_system_source" not in c
print("VENDOR_MAINTAINED_FS_IFILESYSTEM_PARITY_PASS: three opens, quiet guard, DEV selection")


# Native host-syncpoint callback diagnostic: exact old-generated TU parity.
nvctrl_rel = "core/hle/service/nvdrv/devices/nvhost_ctrl.cpp"
nvctrl_pinned = (sources / "eden/src" / nvctrl_rel).read_text()
nvctrl_maintained = (active / "eden-core/src" / nvctrl_rel).read_text()
nvctrl_old = """    event.wait_handle =
        host1x_syncpoint_manager.RegisterHostAction(fence_id, target_value, [this, slot]() {
            auto& event_ = events[slot];"""
nvctrl_new = """    const auto wait_start = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed) ? ::Eden::Performance::NowNs() : 0;
    event.wait_handle =
        host1x_syncpoint_manager.RegisterHostAction(fence_id, target_value, [this, slot, wait_start]() {
            if (wait_start) ::Eden::Performance::AddSince(::Eden::Performance::guest_sync_wait, wait_start);
            auto& event_ = events[slot];"""
assert nvctrl_pinned.count(nvctrl_old) == 1
assert nvctrl_maintained == '#include "performance.h"\n' + nvctrl_pinned.replace(nvctrl_old, nvctrl_new), (
    "Maintained nvhost_ctrl source diverges from original event-wait instrumentation")
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_NVCTRL}")') == 1
assert c.count('list(REMOVE_ITEM core_sources "hle/service/nvdrv/devices/nvhost_ctrl.cpp")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_NVCTRL}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/nvhost_ctrl.cpp"' not in c
assert "ctrl_source" not in c and "ctrl_old" not in c

# The previous one-line CMake wrapper of DequeueBuffer's blocking wait is
# now a real maintained source, identical apart from the necessary include.
dequeue_rel = "core/hle/service/nvnflinger/buffer_queue_producer.cpp"
dequeue_pinned = (sources / "eden/src" / dequeue_rel).read_text()
dequeue_maintained = (active / "eden-core/src" / dequeue_rel).read_text()
dequeue_old = "        Status status = WaitForFreeSlotThenRelock(async, &found, &return_flags, lock);"
dequeue_new = """        const auto dequeue_start = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed) ? ::Eden::Performance::NowNs() : 0;
        Status status = WaitForFreeSlotThenRelock(async, &found, &return_flags, lock);
        if (dequeue_start) ::Eden::Performance::AddSince(::Eden::Performance::guest_dequeue_wait, dequeue_start);"""
assert dequeue_pinned.count(dequeue_old) == 1
assert dequeue_maintained == '#include "performance.h"\n' + dequeue_pinned.replace(dequeue_old, dequeue_new), (
    "Maintained queue-dequeue diagnostic diverges from prior generated source")
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_DEQUEUE}")') == 1
assert c.count('list(REMOVE_ITEM core_sources "hle/service/nvnflinger/buffer_queue_producer.cpp")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_PROFILE_DEQUEUE}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/buffer_queue_producer.cpp"' not in c
assert "producer_source" not in c and "producer_old" not in c
print("VENDOR_MAINTAINED_DEQUEUE_PARITY_PASS: wait timing, quiet guard, DEV selection")

print("VENDOR_MAINTAINED_NVCTRL_PARITY_PASS: async callback capture, quiet clock, DEV selection")

print("VENDOR_MAINTAINED_FS_IFILE_PARITY_PASS: pinned native DEV source, no CMake rewrite")



# HLE request dispatch: reproduce both historical CMake substitutions against
# the pinned file. The filesystem caller probe is applied to BOTH dispatch
# wrappers, even though we intentionally make no new runtime behavior changes.
hle_rel = "core/hle/service/service.cpp"
hle_pinned = (sources / "eden/src" / hle_rel).read_text()
hle_maintained = (active / "eden-core/src" / hle_rel).read_text()
hle_expected = '#include "performance.h"\n#include "core/arm/debug.h"\n' + hle_pinned
hle_calls = ("        InvokeRequest(ctx);", "            InvokeRequestTipc(ctx);")
hle_metric = """            if (profile_hle)
                ::Eden::Performance::RecordHle(service_name, ctx.GetCommand(), ::Eden::Performance::NowNs() - hle_start);
"""
for call in hle_calls:
    assert hle_expected.count(call) == 1, ("missing pinned HLE request dispatch", call)
    wrapper = ("""        {
            const bool profile_hle = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed);
            const auto hle_start = profile_hle ? ::Eden::Performance::NowNs() : 0;
""" + call + "\n" + hle_metric + "        }")
    hle_expected = hle_expected.replace(call, wrapper)
assert hle_expected.count(hle_metric) == 2
hle_trace = """            if (::Eden::Performance::trace_fs_callers.load(std::memory_order_relaxed) && std::string_view{service_name} == "IFileSystem") {
                std::string frames;
                for (const auto& entry : Core::GetBacktrace(&ctx.GetThread()))
                    frames += fmt::format(" {}+{:X}", entry.module, entry.offset);
                LOG_WARNING(Service_FS, "EDEN_FS_CALLER command={} thread={} name={} frames={}", ctx.GetCommand(),
                            ctx.GetThread().GetThreadId(), Core::GetThreadName(&ctx.GetThread()).value_or("-"), frames);
            }
"""
hle_expected = hle_expected.replace(hle_metric, hle_metric + hle_trace)
assert hle_maintained == hle_expected, "Maintained service dispatch diverges from former CMake-generated HLE source"
# Synchronous IPC: request ID and timing are captured BEFORE the potentially
# blocking call; the exact historical body is maintained, not regenerated.
ipc_rel = "core/hle/kernel/svc/svc_ipc.cpp"
ipc_pinned = (sources / "eden/src" / ipc_rel).read_text()
ipc_maintained = (active / "eden-core/src" / ipc_rel).read_text()
ipc_old = "    R_RETURN(session->SendSyncRequest(kernel, message, buffer_size));"
ipc_new = """    const bool ipc_profile = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed);
    const auto ipc_start = ipc_profile ? ::Eden::Performance::NowNs() : 0;
    const auto ipc_tid = ipc_profile ? GetCurrentThread(kernel).GetThreadId() : 0;
    auto* const ipc_slot = ipc_profile ? ::Eden::Performance::BeginGuestIpc(ipc_tid, ipc_start) : nullptr;
    const Result ipc_result = session->SendSyncRequest(kernel, message, buffer_size);
    if (ipc_profile) ::Eden::Performance::FinishGuestIpc(ipc_slot, ipc_tid, ipc_start, ::Eden::Performance::NowNs() - ipc_start);
    R_RETURN(ipc_result);"""
assert ipc_pinned.count(ipc_old) == 1
assert ipc_maintained == '#include "performance.h"\n' + ipc_pinned.replace(ipc_old, ipc_new), (
    "Maintained IPC source diverges from former generated source")
for name, pinned_path in (
        ("HLE_SERVICE", "hle/service/service.cpp"),
        ("SVC_IPC", "hle/kernel/svc/svc_ipc.cpp")):
    assert f'set(EDEN_MAINTAINED_PROFILE_{name}' in c
    assert ('"${EDEN_MAINTAINED_PROFILE_' + name + '}"') in c
    assert f'"{pinned_path}"' in c
    assert ('write_derived("${PORT_BUILD_DIR}' + "/" + ("hle_service" if name == "HLE_SERVICE" else "svc_ipc") + '.cpp"') not in c
assert c.count('list(REMOVE_ITEM core_sources "hle/service/service.cpp" "hle/kernel/svc/svc_ipc.cpp")') == 1
for name in ("hle_source", "ipc_source", "hle_call", "ipc_old"):
    assert name not in c, ("legacy configure-time HLE rewrite still referenced", name)
print("VENDOR_MAINTAINED_HLE_IPC_PARITY_PASS: both dispatches, caller traces, guest IPC attribution, DEV selection")

# Native common/runtime unit selection must be real maintained C++, not
# transient CMake string-rewritten source. Exact source parity is checked,
# with the former absolute include replaced by the tracked include directory.
thread_rel = "common/thread.cpp"
thread_original = (sources / "eden/src" / thread_rel).read_text()
thread_maintained = (active / "eden-core/src" / thread_rel).read_text()
thread_old = "void SetCurrentThreadName(const char* name) {"
thread_new = thread_old + "\n    ::Eden::Performance::RegisterWorker(name);"
assert thread_original.count(thread_old) == 1
assert thread_maintained == '#include "performance.h"\n' + thread_original.replace(thread_old, thread_new)
assert c.count('list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_THREAD}")') == 1
assert 'list(REMOVE_ITEM common_sources thread.cpp)' in c
assert 'write_derived("${PORT_BUILD_DIR}/thread.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/common/thread.cpp" thread_source)' not in c
fs_native_rel = "common/fs/fs.cpp"
fs_native_original = (sources / "eden/src" / fs_native_rel).read_text()
fs_native_maintained = (active / "eden-core/src" / fs_native_rel).read_text()
fs_native_old = "fs::directory_iterator(path, ec)"
assert fs_native_original.count(fs_native_old) == 2
fs_native_expected = '#include "native_directory.h"\n' + fs_native_original.replace(
    fs_native_old, "Eden::ReadNativeDirectory(path, ec)")
assert fs_native_maintained == fs_native_expected
assert c.count('list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_FS}")') == 1
assert 'list(REMOVE_ITEM common_sources fs/fs.cpp)' in c
assert 'write_derived("${PORT_BUILD_DIR}/fs.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/common/fs/fs.cpp" fs_source)' not in c
assert 'target_include_directories(common PRIVATE "${EDEN_PORT_DIR}")' in c
# Verify native common sources are selected exactly once and originals removed.
native_common_block = c.split("    get_target_property(common_sources common SOURCES)", 1)[1].split(
    '    set_property(TARGET common PROPERTY SOURCES "${common_sources}")', 1)[0]
assert native_common_block.count("list(REMOVE_ITEM common_sources thread.cpp)") == 1
assert native_common_block.count("list(REMOVE_ITEM common_sources fs/fs.cpp)") == 1
assert native_common_block.count("list(APPEND common_sources") == 4
for former_read in ("thread_source", "fs_source"):
    assert former_read not in native_common_block
for name in ("EDEN_MAINTAINED_NATIVE_THREAD", "EDEN_MAINTAINED_NATIVE_FS"):
    assert ('if(NOT EXISTS "${' + name + '}")') in native_common_block

print("VENDOR_MAINTAINED_COMMON_RUNTIME_PARITY_PASS: thread name, two iterators, native-only selection")

# Native CPU feature detection: move the CPUID 0x15 fallback out of its
# leaf-specific block without changing the existing host frequency heuristic.
cpu_rel = "common/cpu_features.cpp"
cpu_pinned = (sources / "eden/src" / cpu_rel).read_text()
cpu_active = (active / "eden-core/src" / cpu_rel).read_text()
cpu_fallback = """        } else {
            caps.tsc_frequency = X64::EstimateRDTSCFrequency();
        }"""
cpu_leaf16 = "    if (max_std_fn >= 0x16) {"
cpu_leaf16_new = """    if (caps.invariant_tsc && caps.tsc_frequency < 1'000'000'000ULL) {
        caps.tsc_frequency = X64::EstimateRDTSCFrequency();
    }

    if (max_std_fn >= 0x16) {"""
assert cpu_pinned.count(cpu_fallback) == cpu_pinned.count(cpu_leaf16) == 1
cpu_expected = cpu_pinned.replace(cpu_fallback, "        }").replace(cpu_leaf16, cpu_leaf16_new)
assert cpu_active == cpu_expected, "TSC source differs from previous configure-time transformation"
assert c.count('list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_CPU_FEATURES}")') == 1
assert 'list(REMOVE_ITEM common_sources cpu_features.cpp)' in c
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_CPU_FEATURES}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/cpu_features.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/common/cpu_features.cpp" features_source)' not in c

# Native writable/cache/config roots and the legacy-compatibility folder.
# Header normalization is safe because the common target carries the same
# EDEN_PORT_DIR private include root used by the previous generated file.
paths_rel = "common/fs/path_util.cpp"
paths_pinned = (sources / "eden/src" / paths_rel).read_text()
paths_active = (active / "eden-core/src" / paths_rel).read_text()
paths_old = "#else\n        eden_path = GetCurrentDir() / PORTABLE_DIR;"
paths_new = """#elif defined(PS5_NATIVE)
        eden_path = Eden::UserDir();
        eden_path_cache = eden_path / CACHE_DIR;
        eden_path_config = eden_path / CONFIG_DIR;
#else
        eden_path = GetCurrentDir() / PORTABLE_DIR;"""
legacy_old = "#else\n        // In Ryujinx's infinite wisdom"
legacy_new = """#elif defined(PS5_NATIVE)
        GenerateLegacyPath(EmuPath::RyujinxDir, eden_path / RYUJINX_DIR);
#else
        // In Ryujinx's infinite wisdom"""
assert paths_pinned.count(paths_old) == paths_pinned.count(legacy_old) == 1
paths_expected = '#include "storage_paths.h"\n' + paths_pinned.replace(
    paths_old, paths_new).replace(legacy_old, legacy_new)
assert paths_active == paths_expected, "Native user/config path source differs from prior generator"
assert c.count('list(APPEND common_sources "${EDEN_MAINTAINED_NATIVE_PATHS}")') == 1
assert 'list(REMOVE_ITEM common_sources fs/path_util.cpp)' in c
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_PATHS}")' in c
assert 'target_include_directories(common PRIVATE "${EDEN_PORT_DIR}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/path_util.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/common/fs/path_util.cpp" paths_source)' not in c
print("VENDOR_MAINTAINED_NATIVE_TSC_PATH_PARITY_PASS: CPUID fallback, native roots, DEV build selection")

# Native getifaddrs interface provider: exactly three platform-branch
# substitutions used to be emitted as a generated CMake translation unit.
interfaces_rel = "core/internal_network/network_interface.cpp"
interfaces_pinned = (sources / "eden/src" / interfaces_rel).read_text()
interfaces_active = (active / "eden-core/src" / interfaces_rel).read_text()
interface_replacements = (
    ("defined(__linux__) || defined(__ANDROID__)",
     "defined(__linux__) || defined(__ANDROID__) || defined(__FreeBSD__)"),
    ("defined(__ANDROID__) || defined(__linux__)",
     "defined(__ANDROID__) || defined(__linux__) || defined(__FreeBSD__)"),
    ("#ifdef __ANDROID__", "#if defined(__ANDROID__) || defined(__FreeBSD__)"),
)
interface_expected = interfaces_pinned
for old_branch, native_branch in interface_replacements:
    assert interface_expected.count(old_branch) == 1, ("native interface branch changed", old_branch)
    interface_expected = interface_expected.replace(old_branch, native_branch)
assert interfaces_active == interface_expected, "Native network interfaces diverge from previous CMake source"
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_NATIVE_NET_INTERFACES}")') == 1
assert 'list(REMOVE_ITEM core_sources internal_network/network_interface.cpp)' in c
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_NET_INTERFACES}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/network_interface.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/internal_network/network_interface.cpp" interfaces_source)' not in c
print("VENDOR_MAINTAINED_NATIVE_NET_INTERFACES_PARITY_PASS: getifaddrs branch, native-only selection")





# Firmware system root: preserved transformation and selected native C++.
native_fs_rel = "core/hle/service/filesystem/filesystem.cpp"
native_fs_pinned = (sources / "eden/src" / native_fs_rel).read_text()
native_fs_active = (active / "eden-core/src" / native_fs_rel).read_text()
native_fs_old = "nand_directory, std::move(load_directory), std::move(dump_directory));"
native_fs_new = ('nand_directory, std::move(load_directory), std::move(dump_directory), '
                 'vfs.OpenDirectory(Eden::AssetsPath("firmware"), FileSys::OpenMode::Read));')
assert native_fs_pinned.count(native_fs_old) == 1
assert native_fs_active == ('#include "assets_dir.h"\n'
                           + native_fs_pinned.replace(native_fs_old, native_fs_new))
assert c.count('list(REMOVE_ITEM core_sources hle/service/filesystem/filesystem.cpp)') == 1
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_NATIVE_FILESYSTEM}")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_NATIVE_FILESYSTEM}")' in c
assert 'target_include_directories(core PRIVATE "${EDEN_PORT_DIR}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/filesystem.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/service/filesystem/filesystem.cpp" fs_service)' not in c
print("VENDOR_MAINTAINED_NATIVE_FILESYSTEM_PARITY_PASS: firmware and selection")

# Source parity for non-owning RomFS builder parents: the old CMake
# substitutions targeted TWO directory/file contexts and TWO assignments.
romfs_rel = "core/file_sys/fsmitm_romfsbuild.cpp"
romfs_pinned = (sources / "eden/src" / romfs_rel).read_text()
romfs_active = (active / "eden-core/src" / romfs_rel).read_text()
romfs_rewrites = (
    ("    std::shared_ptr<RomFSBuildDirectoryContext> parent;",
     "    RomFSBuildDirectoryContext* parent = nullptr;"),
    ("parent = std::move(parent_dir_ctx);", "parent = parent_dir_ctx.get();"),
)
for old,new in romfs_rewrites:
    assert romfs_pinned.count(old) == 2, ("pinned RomFS parent drift", old)
    romfs_pinned = romfs_pinned.replace(old,new)
assert romfs_active == romfs_pinned, "maintained RomFS builder differs from former CMake unit"
assert c.count('list(REMOVE_ITEM core_sources file_sys/fsmitm_romfsbuild.cpp)') == 1
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_ROMFS_BUILDER}")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_ROMFS_BUILDER}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/fsmitm_romfsbuild.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/file_sys/fsmitm_romfsbuild.cpp"' not in c
print("VENDOR_MAINTAINED_ROMFS_BUILDER_PARITY_PASS: two non-owning links, two assignments")

# Native BISFactory is a coordinated header/source pair: constructors and
# firmware root, plus the lookup-only mod directory behavior, match the
# former configure-time substitutions byte-for-byte.
bis_header_pinned = (sources / "eden/src/core/file_sys/bis_factory.h").read_text()
bis_header_maintained = (active / "eden-core/include/core/file_sys/bis_factory.h").read_text()
bis_header_old = "VirtualDir dump_root);"
bis_header_new = "VirtualDir dump_root, VirtualDir firmware_root = {});"
assert bis_header_pinned.count(bis_header_old) == 1
assert bis_header_maintained == bis_header_pinned.replace(bis_header_old,bis_header_new)
bis_cpp_pinned = (sources / "eden/src/core/file_sys/bis_factory.cpp").read_text()
bis_cpp_maintained = (active / "eden-core/src/core/file_sys/bis_factory.cpp").read_text()
bis_rewrites = (
    ("VirtualDir dump_root_)", "VirtualDir dump_root_, VirtualDir firmware_root)"),
    ('GetOrCreateDirectoryRelative(nand_root, "/system/Contents/registered")',
     'firmware_root ? std::move(firmware_root) : GetOrCreateDirectoryRelative(nand_root, "/system/Contents/registered")'),
    ('    return GetOrCreateDirectoryRelative(load_root, fmt::format("/{:016X}", title_id));\n'
     '}\n\nVirtualDir BISFactory::GetModificationDumpRoot',
     '    const auto wanted = fmt::format("{:016X}", title_id);\n'
     '    if (load_root != nullptr)\n'
     '        for (const auto& folder : load_root->GetSubdirectories())\n'
     '            if (Common::ToUpper(folder->GetName()) == wanted) return folder;\n'
     '    return nullptr;\n'
     '}\n\nVirtualDir BISFactory::GetModificationDumpRoot'),
)
for old,new in bis_rewrites:
    assert bis_cpp_pinned.count(old) == 1, ("pinned BISFactory contract drift",old)
    bis_cpp_pinned = bis_cpp_pinned.replace(old,new)
assert bis_cpp_maintained == '#include "common/string_util.h"\n' + bis_cpp_pinned
assert c.count('list(REMOVE_ITEM core_sources file_sys/bis_factory.cpp)') == 1
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_BIS_SOURCE}")') == 1
assert 'target_include_directories(core BEFORE PUBLIC "${EDEN_MAINTAINED_BIS_INCLUDE_ROOT}")' in c
assert 'file(REMOVE "${PORT_BUILD_DIR}/include/core/file_sys/bis_factory.h")' in c
assert 'write_derived("${PORT_BUILD_DIR}/bis_factory.cpp"' not in c
assert 'write_derived("${PORT_BUILD_DIR}/include/core/file_sys/bis_factory.h"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/file_sys/bis_factory.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/file_sys/bis_factory.h"' not in c
print("VENDOR_MAINTAINED_BIS_PAIR_PARITY_PASS: API, firmware root, mods and native selection")

# Renderer factory parity: Vulkan keeps the untouched source while the
# OpenGL-only native profile selects the tracked two-removal variant.
pinned_factory = (sources / "eden/src/video_core/video_core.cpp").read_text()
maintained_gl_factory = (active / "eden-core/src/video_core/video_core_opengl.cpp").read_text()
gl_removals = (
    '#include "video_core/renderer_vulkan/renderer_vulkan.h"',
    '    case Settings::RendererBackend::Vulkan:\n'
    '        return std::make_unique<Vulkan::RendererVulkan>(emu_window, device_memory, gpu, std::move(context));\n',
)
for removed in gl_removals:
    assert pinned_factory.count(removed) == 1, ("pinned factory drift",removed)
    pinned_factory = pinned_factory.replace(removed, "")
assert maintained_gl_factory == pinned_factory
factory_select = ('list(REMOVE_ITEM video_sources video_core.cpp gpu.cpp)\n'
                  'if(EDEN_PS5_VULKAN)\n'
                  '    list(APPEND video_sources video_core.cpp)\n'
                  'else()\n'
                  '    list(APPEND video_sources "${EDEN_MAINTAINED_GL_VIDEO_FACTORY}")\n'
                  'endif()')
assert factory_select in c
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_GL_VIDEO_FACTORY}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/video_core.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/video_core.cpp" video_factory)' not in c
print("VENDOR_VIDEO_FACTORY_SELECTION_PASS: pinned Vulkan and maintained OpenGL")

# RendererOpenGL previously passed through an identity CMake file copy.
# The pinned source already belongs to video_core; do not duplicate objects.
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/renderer_opengl/renderer_opengl.cpp" renderer_source)' not in c
assert 'write_derived("${PORT_BUILD_DIR}/renderer_opengl.cpp"' not in c
assert 'list(REMOVE_ITEM video_sources renderer_opengl/renderer_opengl.cpp)' not in c
assert 'list(APPEND video_sources "${PORT_BUILD_DIR}/renderer_opengl.cpp")' not in c
assert 'renderer_opengl/renderer_opengl.cpp' in (sources / "eden/src/video_core/CMakeLists.txt").read_text()
# Stale generated renderer must not remain an explicit Vulkan rebuild dependency.
assert '${PORT_BUILD_DIR}/renderer_opengl.cpp' not in vulkan
assert '${PROJECT_SOURCE_DIR}/src/video_core/renderer_opengl/renderer_opengl.cpp' in vulkan
print("VENDOR_OPENGL_RENDERER_IDENTITY_COPY_REMOVED: pinned source selected")

# GL source parity and conditional selection: exact old CMake substitutions.
native_gl_buffer = "video_core/renderer_opengl/gl_buffer_cache.cpp"
native_gl_query = "video_core/renderer_opengl/gl_query_cache.cpp"
pinned_gl_buffer = (sources/"eden/src"/native_gl_buffer).read_text()
pinned_gl_query = (sources/"eden/src"/native_gl_query).read_text()
old_buf = "static_cast<GLsizeiptr>(size), GL_RED, GL_UNSIGNED_INT, &value);"
new_buf = "static_cast<GLsizeiptr>(size), GL_RED_INTEGER, GL_UNSIGNED_INT, &value);"
old_qry = "const bool slice_counter = WaitPending() && stream.IsEnabled();"
new_qry = "const bool slice_counter = false; // PS5: do not split cached query reads."
assert pinned_gl_buffer.count(old_buf) == 1
assert pinned_gl_query.count(old_qry) == 1
assert (active/"eden-core/src"/native_gl_buffer).read_text() == pinned_gl_buffer.replace(old_buf,new_buf)
assert (active/"eden-core/src"/native_gl_query).read_text() == pinned_gl_query.replace(old_qry,new_qry)
assert c.count('list(APPEND video_sources "${EDEN_MAINTAINED_GL_BUFFER_CACHE}")') == 1
assert c.count('list(APPEND video_sources "${EDEN_MAINTAINED_GL_QUERY_CACHE}")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_GL_BUFFER_CACHE}")' in c
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_GL_QUERY_CACHE}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/gl_buffer_cache.cpp"' not in c
assert 'write_derived("${PORT_BUILD_DIR}/gl_query_cache.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/renderer_opengl/gl_buffer_cache.cpp" buffer_source)' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/renderer_opengl/gl_query_cache.cpp" query_source)' not in c
print("VENDOR_MAINTAINED_GL_CACHE_PARITY_PASS buffer=1 native_query=1")

# The native compiler-rt TLS unit is maintained, not rewritten by CMake.
emutls_upstream = (sources/"compiler-rt/emutls.c").read_text()
emutls_original = "#define EMUTLS_SKIP_DESTRUCTOR_ROUNDS 0"
emutls_updated = "#define EMUTLS_SKIP_DESTRUCTOR_ROUNDS 1"
assert emutls_upstream.count(emutls_original) == 1
assert (active/"compiler-rt/emutls.c").read_text() == emutls_upstream.replace(emutls_original,emutls_updated)
assert c.count('target_sources(common PRIVATE "${EDEN_MAINTAINED_EMUTLS}" "${COMPILER_RT}/cpu_model_x86.c")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_EMUTLS}")' in c
assert 'target_include_directories(common PRIVATE "${COMPILER_RT}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/emutls.c"' not in c
assert 'file(READ "${COMPILER_RT}/emutls.c" emutls)' not in c
print("VENDOR_COMPILER_RT_EMUTLS_PARITY_PASS native_rounds=1")

# Native development GL texture diagnostics: preserve old CMake output.
gl_src = (sources / "eden/src/video_core/renderer_opengl/gl_texture_cache.cpp").read_text()
gl_anchor = "dst_origin.y, dst_origin.z, region.width, region.height, region.depth);"
gl_trace = "        static unsigned copy_errors = 0;\n        const GLenum copy_error = copy_errors < 8 ? glGetError() : GL_NO_ERROR;\n        if (copy_error && copy_errors++ < 8) {\n            GLint sw = 0, dw = 0;\n            glGetTextureLevelParameteriv(src_name, src_origin.level, GL_TEXTURE_WIDTH, &sw);\n            glGetTextureLevelParameteriv(dst_name, dst_origin.level, GL_TEXTURE_WIDTH, &dw);\n            std::printf(\"EDEN_DEV_COPY error=%x src=%u target=%x level=%d x=%d width=%d dst=%u target=%x level=%d x=%d width=%d extent=%dx%dx%d\\n\", copy_error, src_name, src_target, src_origin.level, src_origin.x, sw, dst_name, dst_target, dst_origin.level, dst_origin.x, dw, region.width, region.height, region.depth);\n        }"
assert gl_src.count(gl_anchor) == 1, "Pinned development GL copy site drift"
gl_old_generated = "#include <cstdio>\n" + gl_src.replace(gl_anchor, gl_anchor + "\n" + gl_trace)
assert (active / "eden-core/src/video_core/renderer_opengl/gl_texture_cache.cpp").read_text() == gl_old_generated
assert c.count('list(APPEND video_sources "${EDEN_MAINTAINED_DEV_GL_TEXTURE}")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_DEV_GL_TEXTURE}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/gl_texture_cache.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/renderer_opengl/gl_texture_cache.cpp" texture_source)' not in c
assert 'renderer_opengl/gl_texture_cache.cpp' in (sources / "eden/src/video_core/CMakeLists.txt").read_text()
print("MAINTAINED_GL_TEXTURE_DEV_PARITY_PASS: bounded copy instrumentation")

# A32 fastmem must derive from the *installed shipping backport*, not from
# the original pinned Eden file that is overwritten before CMake configure.
shipping_memory = (active / "eden-backports/src/core/memory.cpp").read_text()
a32_memory = (active / "eden-core/src/core/memory.cpp").read_text()
old_fastmem_guard = "        if (process.IsApplication() && Settings::IsFastmemEnabled()) {"
new_fastmem_guard = "        if (process.IsApplication() && !process.Is64Bit() && Settings::IsFastmemEnabled()) {"
assert shipping_memory.count(old_fastmem_guard) == 1, "shipping memory ABI/input changed"
assert a32_memory == shipping_memory.replace(old_fastmem_guard, new_fastmem_guard)
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_A32_MEMORY}")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_A32_MEMORY}")' in c
assert 'if(EDEN_A32_FASTMEM)' in c
assert 'write_derived("${PORT_BUILD_DIR}/memory.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/memory.cpp" arena_source)' not in c
print("MAINTAINED_A32_MEMORY_PARITY_PASS: complete installed backport source")

# Maintained nvdrv session ownership must match the exact pinned generator.
nvdrv_rel = "core/hle/service/nvdrv/core/container.cpp"
nvdrv_pinned = (sources / "eden/src" / nvdrv_rel).read_text()
nvdrv_expected = "#include \"core/core.h\"\n#include <utility>\n" + nvdrv_pinned
for before, after in (
    ("    session.is_active = true;",
     "    process->Open(impl->host1x.System().Kernel()); // Paired with the final CloseSession after SMMU unregistration.\n    session.is_active = true;"),
    ("void Container::CloseSession(SessionId session_id) {\n    std::scoped_lock lk(impl->session_guard);",
     "void Container::CloseSession(SessionId session_id) {\n    std::unique_lock lk(impl->session_guard);"),
    ("    impl->id_pool.emplace_front(session_id.id);",
     "    impl->id_pool.emplace_front(session_id.id);\n    auto* process = std::exchange(session.process, nullptr);\n    lk.unlock(); // Process finalization may close other services.\n    process->Close(impl->host1x.System().Kernel());"),
):
    assert nvdrv_expected.count(before) == 1, ("nvdrv source anchor drift", before)
    nvdrv_expected = nvdrv_expected.replace(before, after)
assert (active / "eden-core/src" / nvdrv_rel).read_text() == nvdrv_expected
assert c.count('list(APPEND core_sources "${EDEN_MAINTAINED_NVDRV_CONTAINER}")') == 1
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_NVDRV_CONTAINER}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/nvdrv_container.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/service/nvdrv/core/container.cpp" nvcontainer)' not in c
print("VENDOR_MAINTAINED_NVDRV_SESSION_PARITY_PASS source=1 selections=1")

# The direct controller TU must reproduce the previous CMake-generated TU.
rumble_original = (sources / "eden/src/hid_core/frontend/emulated_controller.cpp").read_text()
rumble_site = "    output_params[LeftIndex] = left_joycon;\n    output_params[RightIndex] = right_joycon;\n"
rumble_insert = "    if (output_params[LeftIndex].Get(\"engine\", \"\").empty()) {\n        const auto rumble_port = std::to_string(Service::HID::NpadIdTypeToIndex(npad_id_type));\n        output_params[LeftIndex] = Common::ParamPackage{\"engine:virtual_gamepad,port:\" + rumble_port + \",pad:1\"};\n        output_params[RightIndex] = Common::ParamPackage{\"engine:virtual_gamepad,port:\" + rumble_port + \",pad:2\"};\n    }\n"
assert rumble_original.count(rumble_site) == 1, "pinned rumble source site changed"
rumble_generated = "#include <string>\n" + rumble_original.replace(rumble_site, rumble_site + rumble_insert)
assert (active / "eden-core/src/hid_core/frontend/emulated_controller.cpp").read_text() == rumble_generated
assert 'list(APPEND controller_sources "${EDEN_MAINTAINED_RUMBLE_CONTROLLER}")' in c
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_RUMBLE_CONTROLLER}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/emulated_controller.cpp"' not in c
print("MAINTAINED_RUMBLE_UNIT_PARITY_PASS selection=hid_core")


# Exact old-source parity for NPad: this must reproduce the former build
# generator applied to the immutable shipping-backport snapshot, not an
# independently rewritten input implementation.
npad_shipping = (active / "eden-backports/src/hid_core/resources/npad/npad.cpp").read_text()
npad_old_pair = "        auto& controller = controller_data[aruid_index][controller_idx];\n        const auto is_connected = controller.device->IsConnected();"
npad_new_pair = "        auto& controller = controller_data[aruid_index][controller_idx];\n        if (controller.device == nullptr) {\n            continue;  // ProsperoEden: this applet resource is not activated yet\n        }\n        const auto is_connected = controller.device->IsConnected();"
npad_old_entry = "void NPad::ControllerUpdate(Kernel::KernelCore& kernel, Core::HID::ControllerTriggerType type, std::size_t controller_idx) {\n"
npad_new_entry = "void NPad::ControllerUpdate(Kernel::KernelCore& kernel, Core::HID::ControllerTriggerType type, std::size_t controller_idx) {\n    if (applet_resource_holder.applet_resource == nullptr) {\n        return;\n    }\n"
assert npad_shipping.count(npad_old_pair) == npad_shipping.count(npad_old_entry) == 1
npad_expected = npad_shipping.replace(npad_old_pair, npad_new_pair).replace(
    npad_old_entry, npad_new_entry)
assert (active / "eden-core/src/hid_core/resources/npad/npad.cpp").read_text() == npad_expected, (
    "Maintained NPad differs from previous CMake source generator")
assert c.count('list(APPEND npad_sources "${EDEN_NPAD_SELECTED}")') == 1
assert c.count('list(FILTER npad_sources EXCLUDE REGEX "(^|/)npad\\\\.cpp$")') == 1
assert 'write_derived("${PORT_BUILD_DIR}/npad.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/hid_core/resources/npad/npad.cpp" npad_source)' not in c
print("MAINTAINED_NPAD_SOURCE_PARITY_PASS guards=2 selection=hid_core")

# Dev NPad is not another instrumented CMake-generated translation unit.
# It is the guarded normal source with one scoped Fullkey event witness.
npad_dev = (active / "eden-core/src/hid_core/resources/npad/npad_pause_diag.cpp").read_text()
npad_prefix = "#include <atomic>\\n#include <cstdio>\\n".replace("\\n", "\n")
assert npad_dev.startswith(npad_prefix)
npad_dev_body = npad_dev[len(npad_prefix):]
fullkey_start = "                npad->fullkey_lifo.WriteNextEntry(pad_state);\n"
fullkey_end = "                break;\n            case Core::HID::NpadStyleIndex::Handheld:"
assert npad_expected.count(fullkey_start + fullkey_end) == 1
assert npad_dev_body.count(fullkey_end) == 1
loc = npad_dev_body.index(fullkey_start + "                {")
tail = npad_dev_body.index(fullkey_end, loc)
instrumentation = npad_dev_body[loc+len(fullkey_start):tail]
for essential in (
    "eden_fullkey_writes.fetch_add(", "eden_fullkey_plus_edges.fetch_add(",
    "eden_fullkey_last_plus.exchange(", "EDEN_NPAD_PLUS_LIFO edges=%llu",
    "EDEN_NPAD_PROGRESS fullkey_writes=%llu", "std::memory_order_relaxed",
):
    assert essential in instrumentation, ("diagnostic NPad witness missing", essential)
assert instrumentation.startswith("                {\n") and instrumentation.endswith("                }\n")
assert npad_dev_body[:loc+len(fullkey_start)] + npad_dev_body[tail:] == npad_expected, (
    "DEV NPad diverges outside the Fullkey diagnostic witness")
assert npad_dev_body.count(npad_new_pair) == 1 and npad_dev_body.count(npad_new_entry) == 1
assert 'set(EDEN_NPAD_SELECTED "${EDEN_MAINTAINED_NPAD_DEV}")' in c
assert 'set(EDEN_NPAD_SELECTED "${EDEN_MAINTAINED_NPAD}")' in c
assert c.count('list(APPEND npad_sources "${EDEN_NPAD_SELECTED}")') == 1
assert 'write_derived("${PORT_BUILD_DIR}/npad_pause_diag.cpp"' not in c
assert 'list(APPEND eden_npad_sources "${PORT_BUILD_DIR}/npad_pause_diag.cpp")' not in c
print("MAINTAINED_NPAD_DEV_PARITY_PASS guards=2 scoped_fullkey_witness=1 selection=exclusive")




# Exact parity with the four former pinned CMake patch-manager replacements.
pm_base = (root / "vendor/sources/eden/src/core/file_sys/patch_manager.cpp").read_text()
pm_pairs = [["std::vector<VirtualDir> patch_dirs = {sdmc_load_dir};","std::vector<VirtualDir> patch_dirs;\n    if (sdmc_load_dir) patch_dirs.push_back(sdmc_load_dir);"],["    std::vector<VirtualDir> patch_dirs = load_dir->GetSubdirectories();\n    if (std::find(disabled.cbegin(), disabled.cend(), \"SDMC\") == disabled.cend()) {","    std::vector<VirtualDir> patch_dirs;\n    if (load_dir != nullptr) patch_dirs = load_dir->GetSubdirectories();\n    if (sdmc_load_dir != nullptr && std::find(disabled.cbegin(), disabled.cend(), \"SDMC\") == disabled.cend()) {"],["const auto this_build_id = fmt::format(\"{:0<64}\", name.substr(0, name.find('.')));","const auto this_build_id = fmt::format(\"{:0<64}\", Common::ToUpper(name.substr(0, name.find('.'))));"],["        LOG_ERROR(Loader, \"Cannot load mods for invalid title_id={:016X}\", title_id);\n",""]]
pm_expected = pm_base
for pos, (old, new) in enumerate(pm_pairs):
    assert pm_expected.count(old) == (1, 1, 1, 3)[pos], ("pinned patch manager drift", pos)
    pm_expected = pm_expected.replace(old, new)
assert (active / "eden-core/src/core/file_sys/patch_manager.cpp").read_text() == pm_expected
assert 'list(APPEND core_sources "${PORT_BUILD_DIR}/ips_layer.cpp" "${EDEN_MAINTAINED_PATCH_MANAGER}")' in c
assert 'write_derived("${PORT_BUILD_DIR}/patch_manager.cpp"' not in c
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/file_sys/patch_manager.cpp" patch_source)' not in c
print("MAINTAINED_PATCH_MANAGER_PARITY_PASS four substitutions three logs")


# Former X02 slot-vector source generation: exact pinned input replacement.
slot_base = (root / "vendor/sources/eden/src/common/slot_vector.h").read_text()
slot_old = "[[nodiscard]] SlotId insert(Args&&... args) noexcept {\n        const u32 index = FreeValueIndex();\n        new (&values[index].object) T(std::forward<Args>(args)...);"
slot_new = "[[nodiscard]] SlotId insert(Args&&... args) {\n        const u32 index = FreeValueIndex();\n        try {\n            new (&values[index].object) T(std::forward<Args>(args)...);\n        } catch (...) {\n            free_list.push_back(index); // Restores the popped slot without allocating.\n            throw;\n        }"
assert slot_base.count(slot_old) == 1, "Pinned SlotVector constructor changed"
slot_expected = slot_base.replace(slot_old, slot_new)
slot_maintained = active / "eden-core/overrides/slot-vector/common/slot_vector.h"
assert slot_maintained.read_text() == slot_expected, "Maintained SlotVector does not match former CMake"
assert 'target_include_directories(common BEFORE PUBLIC "${EDEN_MAINTAINED_SLOT_VECTOR_ROOT}")' in c
assert 'target_include_directories(video_core BEFORE PRIVATE "${EDEN_MAINTAINED_SLOT_VECTOR_ROOT}")' in c
assert "slot_vector_recovery.cmake" not in c
print("MAINTAINED_SLOT_VECTOR_PARITY_PASS header=common/slot_vector.h")


# X01 historical MacroJIT recovery -- complete source equals old generator.
macro_original = (root / "vendor/sources/eden/src/video_core/macro.cpp").read_text()
macro_replacements = [["        u32 carry_flag{};","        u32 carry_flag{};\n        std::exception_ptr failure;\n        bool failed{};"],["    program(&state, parameters.data(), parameters.data() + parameters.size());","    program(&state, parameters.data(), parameters.data() + parameters.size());\n    if (state.failure) std::rethrow_exception(state.failure);"],["static void MacroJIT_SendThunk(Core::System* system, Engines::Maxwell3D* maxwell3d, Macro::MethodAddress method_address, u32 value) {\n    maxwell3d->CallMethod(*system, method_address.address, value, true);\n}","static void MacroJIT_SendThunk(MacroJITx64Impl::JITState* state, Macro::MethodAddress method_address, u32 value) noexcept {\n    try {\n        state->maxwell3d->CallMethod(*state->system, method_address.address, value, true);\n    } catch (...) {\n        state->failure = std::current_exception();\n        state->failed = true;\n    }\n}"],["    mov(Common::X64::ABI_PARAM1, qword[STATE + offsetof(JITState, system)]);\n    mov(Common::X64::ABI_PARAM2, qword[STATE + offsetof(JITState, maxwell3d)]);\n    mov(Common::X64::ABI_PARAM3.cvt32(), METHOD_ADDRESS);\n    mov(Common::X64::ABI_PARAM4.cvt32(), value);","    mov(Common::X64::ABI_PARAM3.cvt32(), value);\n    mov(Common::X64::ABI_PARAM2.cvt32(), METHOD_ADDRESS);\n    mov(Common::X64::ABI_PARAM1, STATE);"],["    Common::X64::ABI_PopRegistersAndAdjustStack(*this, PersistentCallerSavedRegs(), 0);\n\n    Xbyak::Label dont_process{};","    Common::X64::ABI_PopRegistersAndAdjustStack(*this, PersistentCallerSavedRegs(), 0);\n    cmp(byte[STATE + offsetof(JITState, failed)], 0);\n    jne(end_of_code, T_NEAR);\n\n    Xbyak::Label dont_process{};"]]
macro_derived = "#include <exception>\n" + macro_original
for idx, (before, after) in enumerate(macro_replacements):
    assert macro_derived.count(before) == 1, ("MacroJIT pinned hunk drift", idx)
    macro_derived = macro_derived.replace(before, after)
assert (active / "eden-core/src/video_core/macro.cpp").read_text() == macro_derived
assert 'list(APPEND video_sources "${EDEN_MAINTAINED_MACRO}")' in c
assert 'macro_recovery.cmake' not in c
print("MAINTAINED_MACRO_RECOVERY_PARITY_PASS anchors=5")


# A single canonical override root does not mean every native frontend .inc
# is an upstream patch. Make ALL headless CMake modules and fragments visible,
# so no additional source mutation can appear without review.
single_source_doc = (root / "docs/EDEN_OVERRIDE_SOURCE_OF_TRUTH.md").read_text()
def single_source_table(begin_tag, end_tag):
    assert single_source_doc.count(begin_tag) == single_source_doc.count(end_tag) == 1
    return [
        line.split("`", 2)[1]
        for line in single_source_doc.split(begin_tag)[1].split(end_tag)[0].splitlines()
        if line.startswith("| `headless/")
    ]
candidates_modules = sorted(p.relative_to(root).as_posix() for p in (root/"headless").rglob("*.cmake"))
candidates_fragments = sorted(p.relative_to(root).as_posix() for p in (root/"headless").rglob("*.inc"))
assert single_source_table("<!-- SINGLE_SOURCE_CMAKE_START -->", "<!-- SINGLE_SOURCE_CMAKE_END -->") == candidates_modules, (
    "undocumented headless CMake code/override module", candidates_modules)
assert single_source_table("<!-- SINGLE_SOURCE_FRAGMENTS_START -->", "<!-- SINGLE_SOURCE_FRAGMENTS_END -->") == candidates_fragments, (
    "undocumented headless injected fragment", candidates_fragments)
assert len(candidates_modules) == 13 and len(candidates_fragments) == 12
assert "**47 générateurs**" in single_source_doc and "**21 générateurs**" in single_source_doc
assert "**68 sites**" in single_source_doc
assert "**215 sources et en-têtes suivis**" in single_source_doc
for deleted_module in ("headless/macro_recovery.cmake", "headless/slot_vector_recovery.cmake"):
    assert not (root/deleted_module).exists(), ("legacy source generator reintroduced", deleted_module)
print("ENCORE_SINGLE_SOURCE_SCOPE_PASS", f"modules={len(candidates_modules)}", f"fragments={len(candidates_fragments)}")


# Byte-exact relocation of six shared-JIT inputs. Do not permit another
# physical owner under headless after moving the authoritative source.
import subprocess


def check_canonical_git_object(source, expected, label):
    """Prove stored Git object identity and working-tree consistency."""
    relative = source.relative_to(root).as_posix()
    actual = subprocess.run(
        ["git", "rev-parse", f"HEAD:{relative}"], cwd=root,
        check=True, capture_output=True, text=True).stdout.strip()
    assert actual == expected, (label, "Git source blob drift", relative, actual)
    # git diff uses tracked text filters, so this does not mistake a
    # checkout EOL conversion for an intentional source modification.
    result = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", relative], cwd=root)
    assert result.returncode == 0, (label, "dirty canonical source", relative)


shared_jit_blobs = {
    "jit_group.h": "50e7f0993ea3db6902bd11bfac496659dce54fb3",
    "jit_group_support.inc": "22cf4c406003cbe2fe1295503dc879086f2ee65e",
    "jit_impl.inc": "d13505bab1908a05503fcf7bd802f1c3ac626d3",
    "jit_links.inc": "7dfe9cf7eabaabe90c61e74e1242c7712cec3503",
    "jit_push_rsb.inc": "08d4ab5765ef788748ba1c7b283a9cbcfad0d047",
    "jit_state_args.inc": "bee5fe16657a46647690f69c73596b8ee1d03ea4",
}
for filename, original_blob in shared_jit_blobs.items():
    source = active / "eden-core/dynarmic/shared-jit" / filename
    assert source.is_file() and not (root / "headless/dynarmic" / filename).exists(), (
        "duplicate shared JIT fragment or missing canonical owner", filename)
    check_canonical_git_object(source, original_blob, "JIT")
shared_jit_selector = (root / "headless/dynarmic/shared-jit.cmake").read_text()
assert 'set(EDEN_SHARED_JIT_DIR "${PORT_ROOT}/vendor/encore-active/eden-core/dynarmic/shared-jit")' in shared_jit_selector
print("ENCORE_SHARED_JIT_SOURCE_OWNERS_PASS", len(shared_jit_blobs))


# Scalar Dynarmic fragments have one physical authority in encore-active.
# These are original Git blobs, not regenerated C++ from CMake strings.
scalar_canonical_blobs = {
    "scalar-fold.inc": "00dcb6ae900c314c396b61013e2adf9ec42a0fa8",
    "scalar-memory-read.inc": "4c3c1ad419af0fbd01bb64b2aac9be65b7b31fc0",
    "scalar-memory-write.inc": "3d86e3e8ca2294a4dfe244063950db583dc22af9",
}
for filename, expected in scalar_canonical_blobs.items():
    source = active / "eden-core/dynarmic/scalar" / filename
    assert source.is_file() and not (root / "headless" / filename).exists(), (
        "scalar injection has duplicate or missing authority", filename)
    check_canonical_git_object(source, expected, "scalar")
scalar_module = (root / "headless/scalar-memory.cmake").read_text()
assert 'file(READ "${EDEN_SCALAR_INPUT_DIR}/scalar-memory-${lower}.inc" scalar_access)' in scalar_module
assert 'file(READ "${EDEN_SCALAR_INPUT_DIR}/scalar-fold.inc" scalar_fold)' in c
assert 'set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${EDEN_SCALAR_INPUTS})' in c
assert 'set(EDEN_SCALAR_INPUT_DIR' in c
print("ENCORE_SCALAR_CANONICAL_INPUTS_PASS", len(scalar_canonical_blobs))


# The five previous Vulkan injection fragments are retained solely as
# historical comparison fixtures, never inputs to the shipping renderer.
vulkan_oracle_sources = {
    "vulkan_loading.inc": "e96a289531ca44282cd1f2e24fea0c2003c9a08b",
    "vulkan_hud_prepare.inc": "36c585ed6726206722450450be7f0c5bb3cafb2d",
    "vulkan_hud_draw.inc": "794563c243b53ecccc4191f2a7de1b7dad0d2b2a",
    "vulkan_gc_downloads.inc": "77c5ce6e536bfb039e2cbd48795d5f5f0059ebc0",
    "vulkan_download_batch.inc": "f3e36e0432f7026a65620329f79cbbe20e1c898a",
}
for filename, expected_git_blob in vulkan_oracle_sources.items():
    oracle = active / "eden-vulkan-oracles" / filename
    assert oracle.is_file() and not (root / "headless" / filename).exists()
    check_canonical_git_object(oracle, expected_git_blob, "Vulkan oracle")
    assert filename not in vulkan, ("test fixture is still a native CMake input", filename)
assert (active / "eden-vulkan/vulkan_renderer.cpp").is_file()
print("ENCORE_VULKAN_ORACLE_SCOPE_PASS", len(vulkan_oracle_sources))


# GPU memory manager: exact reconstruction of the retired native CMake source.
# This is an offline witness, never an alternate generated production file.
gpu_expected = (root / "vendor/sources/eden/src/video_core/memory_manager.cpp").read_text()
gpu_hunks = [
    ("    if (!IsContinuousRange(src_addr, size)) {", "    if (size == 0 || src_addr >= address_space_size ||\n        size > address_space_size - src_addr ||\n        !IsContinuousRange(src_addr, size)) {", 2),
    ("bool MemoryManager::IsGranularRange(GPUVAddr gpu_addr, std::size_t size) const {\n", "bool MemoryManager::IsGranularRange(GPUVAddr gpu_addr, std::size_t size) const {\n    if (gpu_addr >= address_space_size || size == 0 || size > address_space_size - gpu_addr) {\n        return false;\n    }\n", 1),
    ("            const std::size_t page{(page_index & big_page_mask) + size};\n            return page <= big_page_size;", "            return size <= big_page_size - (gpu_addr & big_page_mask);", 1),
    ("const std::size_t page{(gpu_addr & Core::DEVICE_PAGEMASK) + size};\n", "", 2),
    ("return page <= Core::DEVICE_PAGESIZE;", "return size <= Core::DEVICE_PAGESIZE - (gpu_addr & Core::DEVICE_PAGEMASK);", 2),
]
for index, (before, after, expected_count) in enumerate(gpu_hunks):
    assert gpu_expected.count(before) == expected_count, ("GPU pinned anchor drift", index)
    gpu_expected = gpu_expected.replace(before, after)
gpu_maintained = active / "eden-core/src/video_core/memory_manager.cpp"
assert gpu_maintained.is_file() and gpu_maintained.read_text() == gpu_expected, (
    "maintained native GPU memory source differs from retired CMake result")
assert 'list(APPEND video_sources "${EDEN_NATIVE_GPU_MEMORY_MANAGER}")' in c
assert c.count('list(REMOVE_ITEM video_sources "memory_manager.cpp")') == 1
assert 'write_derived("${eden_gpu_span_tu}"' not in c
print("MAINTAINED_GPU_MEMORY_MANAGER_PARITY_PASS patches=5 sites=8 selection=video_core")

# Keep the generator inventory synchronized with every future source migration.
# It catalogs CMake invocations, not physical output files from variable loops.
import re
inventory = (root / "docs/EDEN_OVERRIDE_MIGRATION_INVENTORY.md").read_text()
# Do not hide active non-CMake source transforms behind the CMake-only
# generator counter. The matching inventory names real build entrypoints,
# historical replayers and independent source-equivalence oracles.
assert "## Overrides et générateurs hors CMake principal" in inventory
for relative in (
    "tools/prepare-build.sh", "tools/install-vendored-eden-backports.py",
    "tools/install-vendored-eden-build-flags.py",
    "tools/install-vendored-surface-lifecycle.py",
    "tools/install-vendored-radv.py", "tools/install-active-core-backports.py",
    "tools/apply-eden-backports.sh", "tools/prepare-vulkan-port.py",
    "tools/patch-radv-wsi.py", "tools/sync-encore-overrides.py",
    "tools/sync-glyph-overrides.py", "tools/launcher/strings.py",
    "tools/build-headless-host.sh", "tools/build-opengl-sdk.sh",
    "tools/build-headless-native.sh", "tools/materialize-openssl-cert.py",
    "tools/build-radv-dependencies.sh", "tools/radv-active-inputs.py",
):
    assert (root / relative).is_file(), ("untracked script entrypoint", relative)
    assert "`" + relative + "`" in inventory, ("script override not catalogued", relative)
staging = (root / "tools/prepare-build.sh").read_text()
assert 'python3 -B tools/install-active-core-backports.py "$eden"' in staging
active_core_installer = (root / "tools/install-active-core-backports.py").read_text()
assert 'ACTIVE = ROOT / "vendor/encore-active/eden-core"' in active_core_installer
assert "shutil.copyfile(maintained, tmp)" in active_core_installer
assert "maintained.read_bytes() != new" in active_core_installer
assert 'python3 -B tools/install-vendored-eden-backports.py "$eden"' in staging
assert 'python3 -B tools/install-vendored-eden-build-flags.py "$eden"' in staging
assert 'python3 -B tools/install-vendored-surface-lifecycle.py "$eden"' in staging
assert 'tools/prepare-vulkan-port.py' not in vulkan
radv_legacy = (root / "tools/patch-radv-wsi.py").read_text()
assert "if not oracle:" in radv_legacy and "Legacy RADV source rewrite disabled" in radv_legacy
assert 'patch-radv-wsi.py --check' in staging
native_builder = (root / "tools/build-headless-native.sh").read_text()
assert 'tools/materialize-openssl-cert.py' in native_builder
radv_builder = (root / "tools/build-radv-dependencies.sh").read_text()
assert "current.write_text(derived)" in radv_builder
assert "trap restore_cross_ini EXIT" in radv_builder
assert 'tools/install-vendored-radv.py' in radv_builder

print("VENDOR_SCRIPTED_TRANSFORM_ENTRYPOINTS_PASS staged=5 oracles=2 profile_generators=2")

begin = "<!-- OVERRIDE_GENERATORS_START -->"
end = "<!-- OVERRIDE_GENERATORS_END -->"
assert inventory.count(begin) == inventory.count(end) == 1
recorded = re.findall(r"^\| G\d\d \| \x60([^\x60]+)\x60 \|",
                      inventory.split(begin)[1].split(end)[0], re.M)
current = re.findall(r'write_derived\(\s*"([^"]+)"', c)
assert recorded == current, "CMake-generated override inventory changed: re-inventory targets"
assert len(current) == counts["write_derived("], "dynamic or unquoted generator not cataloged"
print(f"VENDOR_GENERATOR_INVENTORY_PASS entries={len(recorded)}")

# Indirect CMake includes can generate more source units than the primary
# CMake file. Keep the second table exhaustive and order-stable as well.
module_begin = "<!-- MODULE_GENERATORS_START -->"
module_end = "<!-- MODULE_GENERATORS_END -->"
assert inventory.count(module_begin) == inventory.count(module_end) == 1
module_recorded = re.findall(
    r"^\| M\d\d \| \x60([^\x60]+)\x60 \| \x60([^\x60]+)\x60 \|",
    inventory.split(module_begin)[1].split(module_end)[0], re.M)
module_files = (
    "headless/dynarmic/reg_alloc.cmake",
    "headless/dynarmic/shared-jit.cmake",
    "headless/gpu_native_observability.cmake",
    "headless/guest_write_deferred_bridge.cmake",
    "headless/jit-alias.cmake",
    "headless/scalar-memory.cmake",
)
module_current = []
for module in module_files:
    content = (root / module).read_text()
    module_current.extend((module, target) for target in
                          re.findall(r'write_derived\(\s*"([^"]+)"', content))
assert module_recorded == module_current, "Module CMake source generator inventory is stale"
assert len(module_current) == 21, len(module_current)
# Indirect X01/X02 are no longer CMake generators: full source units
# live under encore-active, and the parity witnesses above verify them.
for old_module in ("headless/macro_recovery.cmake", "headless/slot_vector_recovery.cmake"):
    assert not (root / old_module).exists(), ("removed CMake mutator returned", old_module)
assert len(recorded) + len(module_recorded) == 67
print(f"VENDOR_MODULE_GENERATOR_INVENTORY_PASS entries={len(module_recorded)}")

# Separate ledger: these modules modify source without calling write_derived
# locally. Two materialize an output directly; five mutate source variables
# that a root CMake generator subsequently writes. Never count them as extra
# write_derived call sites, but never silently drop them from the inventory.
indirect_begin, indirect_end = "<!-- INDIRECT_OVERRIDES_START -->", "<!-- INDIRECT_OVERRIDES_END -->"
assert inventory.count(indirect_begin) == inventory.count(indirect_end) == 1
indirect_recorded = re.findall(
    r"^\| X\d\d \| \x60([^\x60]+)\x60 \|",
    inventory.split(indirect_begin)[1].split(indirect_end)[0], re.M)
indirect_expected = (
    ("headless/checked-fastmem.cmake", ("string(REPLACE", "memory_source", "memory_emitter")),
    ("headless/native_guest_range_overflow.cmake", ("string(REPLACE", "eden_cpu_memory")),
    ("headless/native_jit_memory_read_guard.cmake", ("string(REPLACE", "wrapper")),
    ("headless/physical_core_interrupt_atomic.cmake", ("string(REPLACE", "physical_core_source")),
)
assert indirect_recorded == [entry[0] for entry in indirect_expected], (
    "Unlisted or reordered indirect CMake override; recheck files and symbols")
for module, required in indirect_expected:
    content = (root / module).read_text()
    assert all(token in content for token in required), ("indirect override changed", module)
assert len(indirect_recorded) == 4
print(f"VENDOR_INDIRECT_OVERRIDE_INVENTORY_PASS modules={len(indirect_recorded)} (not generator sites)")

# Third independent source-change mechanism: pinned backport patch replays.
# Count checked calls, not the number of files they touch or optional runs.
replay_begin = "<!-- SOURCE_PATCH_REPLAYS_START -->"
replay_end = "<!-- SOURCE_PATCH_REPLAYS_END -->"
assert inventory.count(replay_begin) == inventory.count(replay_end) == 1
registered_patches = re.findall(
    r"^\| P\d\d \| \x60([^\x60]+\.patch)\x60 \|",
    inventory.split(replay_begin)[1].split(replay_end)[0], re.M)
legacy_replay_source = (root / "tools/apply-eden-backports.sh").read_text()
legacy_calls = re.findall(
    r'^[ \t]*apply_one "\$root/headless/backports/([^"]+\.patch)"',
    legacy_replay_source, re.M)
active_core_installer = (root / "tools/install-active-core-backports.py").read_text()
patch_names = {p.name for p in (root / "headless/backports").glob("*.patch")}
assert len(legacy_calls) == len(set(legacy_calls)) == 44
active_core_patches = sorted(patch_names.difference(legacy_calls))
assert active_core_patches == [
    "eden-dynarmic-icache-coherence.patch",
    "eden-sm-host-wait.patch",
]
assert all(f'headless/backports/{name}' in active_core_installer
           for name in active_core_patches)
assert "if len(names) != 5:" in active_core_installer
assert "git apply --check" not in legacy_replay_source or "git apply" in legacy_replay_source
assert 'git apply "$patch"' in legacy_replay_source
assert "EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS:-OFF" in legacy_replay_source
assert len(patch_names) == len(registered_patches) == 46
assert registered_patches == legacy_calls + active_core_patches
assert set(registered_patches) == patch_names
print("VENDOR_SOURCE_PATCH_REPLAY_INVENTORY_PASS: 44 replay calls, 2 active-core patches, 46 files")

# Independent source-target audit: 46 registered patches may touch more
# physical translation units than the high-priority function graph names.
# This reports EXACT path gaps; it does not assert all unlisted functions
# have never been checked, nor that the pinned file is selected at runtime.
audit_register = (root / "docs/EDEN_CORE_AUDIT_DEPENDENCIES.md").read_text()
audit_paths = set()
for audit_line in audit_register.splitlines():
    if audit_line.startswith("| ") and len(audit_line.split("|")) > 4 and re.fullmatch(r"[A-Z][0-9]{2}", audit_line.split("|")[1].strip()):
        fields = audit_line.split("|")
        if len(fields) >= 5:
            audit_paths.add(fields[4].strip())
patch_target_map = {}
for patch_name in sorted(patch_names):
    patch_body = (root / "headless/backports" / patch_name).read_text()
    target_paths = {line[6:] for line in patch_body.splitlines() if line.startswith("+++ b/")}
    assert target_paths, ("patch has no target paths", patch_name)
    patch_target_map[patch_name] = target_paths
all_patch_targets = set().union(*patch_target_map.values())
def has_exact_audit_path(relative):
    return any(prefix + relative in audit_paths for prefix in (
        "vendor/sources/eden/", "vendor/encore-active/eden-core/",
        "vendor/encore-active/eden-backports/",
        "vendor/encore-active/eden-vulkan/", "vendor/encore-active/eden-gpu/",
        "vendor/encore-active/eden-threading/",
        "vendor/encore-active/eden-sync/",
        "vendor/encore-active/eden-shader/",
    ))
shipping_manifest = json.loads((active / "eden-backports/manifest.json").read_text())
shipping_build_recipes = {"src/common/CMakeLists.txt", "src/core/CMakeLists.txt"}
assert shipping_build_recipes <= set(shipping_manifest["entries"])
unmatched_patch_targets = sorted(path for path in all_patch_targets
                                 if path not in shipping_build_recipes
                                 and not has_exact_audit_path(path))
assert not unmatched_patch_targets, ("unowned source patch targets", unmatched_patch_targets)
assert len(patch_target_map) == 46
print("VENDOR_PATCH_TARGET_FOOTPRINT_PASS "
      f"patches={len(patch_target_map)} "
      f"touched_paths={len(all_patch_targets)} "
      f"unmatched_exact_graph={len(unmatched_patch_targets)}")
for missing_path in unmatched_patch_targets:
    print("VENDOR_PATCH_TARGET_NEEDS_OWNER", missing_path)









print(f"VENDOR_SOURCE_PINNED roots={len(root_names)} manifest_items={len(deps)} "
      f"active_forks={len(fork_names)}")
print("VENDOR_REWRITE_DEBT_PARTIAL " +
      " ".join(f"{name}={value}" for name, value in counts.items()) +
      " (ceilings, not a declaration of completion)")
print("VENDOR_NATIVE_VULKAN_SOURCE tracked active copy; generator only comparison oracle")
