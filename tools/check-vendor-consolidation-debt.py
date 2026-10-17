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
assert counts["write_derived("] <= 70, counts
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
assert len(recorded) + len(module_recorded) == 91
print(f"VENDOR_MODULE_GENERATOR_INVENTORY_PASS entries={len(module_recorded)}")



print(f"VENDOR_SOURCE_PINNED roots={len(root_names)} manifest_items={len(deps)} "
      f"active_forks={len(fork_names)}")
print("VENDOR_REWRITE_DEBT_PARTIAL " +
      " ".join(f"{name}={value}" for name, value in counts.items()) +
      " (ceilings, not a declaration of completion)")
print("VENDOR_NATIVE_VULKAN_SOURCE tracked active copy; generator only comparison oracle")
