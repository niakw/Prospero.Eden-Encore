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
    "write_derived(": (
        'write_derived("${eden_gpu_span_tu}" "${eden_gpu_span_src}")',
    ),
    "file(READ": (
        'file(READ "${EDEN_PORT_DIR}/gpu_sync_failure_wait.inc" gpu_sync_wait_replacement)',
        'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/memory_manager.cpp" eden_gpu_span_src)',
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
        'string(REPLACE "${eden_gpu_span_original}" [=[',
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
assert c.count("Pinned native GPU guest span range gate changed") == 1
assert c.count("Pinned GPU read callback lifetime changed") == 1
assert c.count('RequestSyncOperation([this, raster_area]() {') == 1
assert (root / "tools/check-native-gpu-read-capture-host.py").is_file()
assert "python3 -B tools/check-native-gpu-read-capture-host.py" in (
    root / ".github/workflows/encore-core-preflight.yml").read_text()
assert c.count('list(REMOVE_ITEM video_sources "memory_manager.cpp")') == 1
assert c.count('list(APPEND video_sources "${eden_gpu_span_tu}")') == 1
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

# Keep the generator inventory synchronized with every future source migration.
# It catalogs CMake invocations, not physical output files from variable loops.
import re
inventory = (root / "docs/EDEN_OVERRIDE_MIGRATION_INVENTORY.md").read_text()
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
for module in ("headless/macro_recovery.cmake", "headless/slot_vector_recovery.cmake"):
    text = (root / module).read_text()
    assert 'file(WRITE ' in text and 'configure_file(' in text, module
assert len(recorded) + len(module_recorded) == 83
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
    ("headless/macro_recovery.cmake", ("file(WRITE ", "configure_file(")),
    ("headless/slot_vector_recovery.cmake", ("file(WRITE ", "configure_file(")),
    ("headless/checked-fastmem.cmake", ("string(REPLACE", "memory_source", "memory_emitter")),
    ("headless/native_gpu_granular_bounds.cmake", ("string(REPLACE", "eden_gpu_span_src")),
    ("headless/native_guest_range_overflow.cmake", ("string(REPLACE", "eden_cpu_memory")),
    ("headless/native_jit_memory_read_guard.cmake", ("string(REPLACE", "wrapper")),
    ("headless/physical_core_interrupt_atomic.cmake", ("string(REPLACE", "physical_core_source")),
)
assert indirect_recorded == [entry[0] for entry in indirect_expected], (
    "Unlisted or reordered indirect CMake override; recheck files and symbols")
for module, required in indirect_expected:
    content = (root / module).read_text()
    assert all(token in content for token in required), ("indirect override changed", module)
assert len(indirect_recorded) == 7
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
        "vendor/encore-active/eden-vulkan/", "vendor/encore-active/eden-gpu/",
        "vendor/encore-active/eden-threading/",
        "vendor/encore-active/eden-sync/",
        "vendor/encore-active/eden-shader/",
    ))
unmatched_patch_targets = sorted(path for path in all_patch_targets
                                 if not has_exact_audit_path(path))
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
