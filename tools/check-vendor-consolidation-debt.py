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
    ),
}
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
print(f"VENDOR_SOURCE_PINNED roots={len(root_names)} manifest_items={len(deps)} "
      f"active_forks={len(fork_names)}")
print("VENDOR_REWRITE_DEBT_PARTIAL " +
      " ".join(f"{name}={value}" for name, value in counts.items()) +
      " (ceilings, not a declaration of completion)")
print("VENDOR_NATIVE_VULKAN_SOURCE tracked active copy; generator only comparison oracle")
