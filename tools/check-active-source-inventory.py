#!/usr/bin/env python3
"""Fail if the active C/C++ source catalogue drifts from tracked files.

This verifies file-level coverage and exact graph cross-links only.
It is not a function audit, compiler check or console-test certificate.
"""
from pathlib import Path
import json
import re

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active"
document = (root / "docs/EDEN_ACTIVE_SOURCE_CATALOG.md").read_text()
audit = (root / "docs/EDEN_CORE_AUDIT_DEPENDENCIES.md").read_text()
begin, end = "<!-- ACTIVE_SOURCE_CATALOG_START -->", "<!-- ACTIVE_SOURCE_CATALOG_END -->"
assert document.count(begin) == document.count(end) == 1
section = document.split(begin, 1)[1].split(end, 1)[0]
suffixes = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inc", ".inl", ".s", ".S", ".asm"}
physical = sorted(
    p.relative_to(active).as_posix()
    for p in active.rglob("*")
    if p.is_file() and p.suffix in suffixes
)
graph = {}
for line in audit.splitlines():
    if not re.match(r"^\| [A-Z][0-9]{2} \|", line):
        continue
    fields = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(fields) < 4 or not fields[3].startswith("vendor/encore-active/"):
        continue
    relative = fields[3].removeprefix("vendor/encore-active/")
    graph.setdefault(relative, []).append(fields[0])
def role(path):
    if path.startswith("eden-backports/"):
        return "shipping-backport"
    if path.startswith("ps5-mesa/"):
        return "driver-fork"
    return "maintained-override"
expected = [
    f"| `{path}` | `{role(path)}` | {','.join(graph[path]) if path in graph else '—'} |"
    for path in physical
]
present = [line for line in section.splitlines() if line.startswith("| `")]
assert present == expected, (
    "Active source catalogue stale or exact graph linkage changed",
    len(present), len(expected),
    next(((a, b) for a, b in zip(present, expected) if a != b), None),
)
# The shipping backport manifest also carries two build recipes that are not
# C/C++ source files; track them explicitly rather than silently omitting them.
manifest = json.loads((active / "eden-backports/manifest.json").read_text())
shipping = set(manifest["entries"])
shipping_cpp = {"src/" + p.removeprefix("eden-backports/src/")
                for p in physical if p.startswith("eden-backports/src/")}
build_recipes = {"src/common/CMakeLists.txt", "src/core/CMakeLists.txt"}
assert shipping == shipping_cpp | build_recipes, (
    "Shipping backport source/build manifest coverage drift",
    sorted(shipping ^ (shipping_cpp | build_recipes)),
)
assert len(shipping) == 83 and len(manifest["shipping_receipts"]) == 43
assert manifest["excluded_experimental"] == ["EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS"]
# All nine selected Vulkan cost translation units have exact graph owners.
# This is source-ownership coverage, not evidence of GPU progress.
vulkan_recipe = (root/"headless/vulkan.cmake").read_text()
cost_modules = ("vk_fence_manager", "vk_buffer_cache", "vk_texture_cache",
                "vk_descriptor_buffer", "vk_multi_range_buffer", "vk_compute_pass",
                "vk_graphics_pipeline", "vk_compute_pipeline", "vk_pipeline_cache")
assert "foreach(name " + " ".join(cost_modules) + ")" in vulkan_recipe
assert 'list(APPEND video_sources "${PORT_BUILD_DIR}/${name}_cost.cpp")' in vulkan_recipe
for module in cost_modules:
    relative = "eden-vulkan/" + module + "_cost.cpp"
    assert (active/relative).is_file(), ("missing selected Vulkan cost source", relative)
    assert relative in graph, ("missing indexed Vulkan cost source", relative)
print("ENCORE_VULKAN_COST_OWNER_PASS", f"selected={len(cost_modules)}")

# Keep the native GPU/guest memory header overrides distinguishable from
# the pinned and materialized backport copies. Selection is native-only.
native_cmake = (root/"headless/CMakeLists.txt").read_text()
assert 'set(EDEN_NATIVE_DIRTY_HEADER_ROOT' in native_cmake
assert 'target_include_directories(core BEFORE PUBLIC "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in native_cmake
assert 'target_include_directories(video_core BEFORE PRIVATE "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in native_cmake
native_mem = ("device_memory_manager.inc", "gpu_dirty_memory_manager.h", "guest_memory.h")
for name in native_mem:
    rel = "eden-core/overrides/core/" + name
    assert (active/rel).is_file(), ("missing native memory override", rel)
    assert rel in graph, ("native memory override lacks active function owner", rel)
    assert '${EDEN_NATIVE_DIRTY_HEADER_ROOT}/core/' + name in native_cmake
print("ENCORE_NATIVE_MEMORY_OWNER_PASS", f"headers={len(native_mem)}")

# Maintained core code and headers must never be silently omitted from the
# function-owner register. Do not confuse an indexed path with a HOST proof.
maintained_core_paths = [path for path in physical if path.startswith("eden-core/")]
assert len(maintained_core_paths) == 36, ("maintained core source set changed", len(maintained_core_paths))
assert all(path in graph for path in maintained_core_paths), (
    "uncatalogued maintained core source paths",
    [path for path in maintained_core_paths if path not in graph],
)
print("ENCORE_MAINTAINED_CORE_OWNER_PASS", f"files={len(maintained_core_paths)}")

# GPU variants and the coordinated HLE header overlays are not optional
# catalogue blind spots, even if selected only by a native build flag.
for family, size in (("eden-gpu/", 4), ("eden-threading/", 12)):
    members = [path for path in physical if path.startswith(family)]
    assert len(members) == size, ("maintained family footprint changed", family, len(members))
    assert all(path in graph for path in members), (
        "uncatalogued maintained family file", family,
        [path for path in members if path not in graph],
    )
print("ENCORE_GPU_THREADING_OWNER_PASS", "gpu=4", "threading=12")

# The surface lifecycle and bounded local-memory shader are already
# maintained sources; require their REAL source selection, not a second copy.
shader_rel = "eden-shader/src/shader_recompiler/frontend/maxwell/translate/impl/load_store_local_shared.cpp"
surface_rel = "eden-surface-lifecycle/src/core/hle/service/nvnflinger/surface_flinger.cpp"
for rel in (shader_rel, surface_rel):
    assert rel in graph and (active / rel).is_file(), ("missing active owner", rel)
shader_recipe = (root / "headless/CMakeLists.txt").read_text()
assert 'list(APPEND eden_shader_sources "${EDEN_MAINTAINED_SHADER_LOCAL}")' in shader_recipe
assert 'set_property(TARGET shader_recompiler PROPERTY SOURCES "${eden_shader_sources}")' in shader_recipe
surface_installer = (root / "tools/install-vendored-surface-lifecycle.py").read_text()
surface_prepare = (root / "tools/prepare-build.sh").read_text()
assert 'ORIGINAL_GIT_BLOB = "a6136c111d96d2660c28b27c6881e3b671e7eed8"' in surface_installer
assert 'WaitForComposite();' in surface_installer and 'm_composer.RemoveLayerLocked(' in surface_installer
assert 'tools/install-vendored-surface-lifecycle.py "$eden"' in surface_prepare
assert 'if existing not in (before, replacement)' in surface_installer
print("ENCORE_SHADER_SURFACE_SOURCE_OWNER_PASS sources=2")

# Core native Vulkan device, query and presentation implementation units
# are versioned sources selected into the disposable build tree by the Vulkan
# recipe. Exact source ownership is not a successful native GPU execution.
native_vk_sources = (
    "vulkan_device.cpp", "vulkan_query_cache.cpp", "vulkan_blit_screen.cpp",
    "vulkan_window_adapt_pass.cpp", "vulkan_wrapper.cpp",
)
for unit in native_vk_sources:
    rel = "eden-vulkan/" + unit
    assert rel in graph and (active / rel).is_file(), ("uncatalogued Vulkan unit", rel)
    assert '"${PORT_BUILD_DIR}/' + unit + '"' in vulkan_recipe, ("source selection lost", unit)
print("ENCORE_VULKAN_DEVICE_PRESENT_OWNER_PASS", f"sources={len(native_vk_sources)}")

# Vulkan headers are shipped as an ABI-consistent set with the selected
# maintained translation units; do not let include-root owners disappear.
assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in vulkan_recipe
assert 'target_include_directories(video_core BEFORE PUBLIC "${PORT_BUILD_DIR}/include")' in vulkan_recipe
abi_headers = ("vk_scheduler.h", "vk_present_manager.h", "vk_descriptor_buffer.h",
               "vk_blit_screen.h", "renderer_vulkan.h")
for header in abi_headers:
    rel = "eden-vulkan/include/video_core/renderer_vulkan/" + header
    assert (active/rel).is_file() and rel in graph, ("missing selected Vulkan ABI owner", rel)
print("ENCORE_VULKAN_SHARED_ABI_OWNER_PASS", f"headers={len(abi_headers)}")

# Summary prose is itself an audit contract, not a manually stale count.
linked_count = sum(path in graph for path in physical)
assert f"**{len(physical)} fichiers** de code" in document
assert f"**{linked_count} fichiers** possèdent" in document
assert f"**{len(physical)-linked_count} fichiers** n'ont" in document
root_cmake = (root / "headless/CMakeLists.txt").read_text()
root_generator_count = len(re.findall(r'write_derived\(\s*"', root_cmake))
assert f"L'inventaire des {root_generator_count} générateurs CMake" in document
print("ENCORE_ACTIVE_CATALOG_SUMMARY_PASS",
      f"files={len(physical)}", f"covered={linked_count}",
      f"cmake_primary_generators={root_generator_count}")

# Every versioned Vulkan source and ABI header selected through the fork's
# configure-time copy has an exact source ownership record. This guards
# coverage, not GPU forward progress or successful native device tests.
vulkan_family = [p for p in physical if p.startswith("eden-vulkan/")]
assert len(vulkan_family) == 40, ("Vulkan maintained footprint changed", len(vulkan_family))
assert all(p in graph for p in vulkan_family), (
    "Vulkan maintained source lacks owner", [p for p in vulkan_family if p not in graph],
)
assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in vulkan_recipe
print("ENCORE_VULKAN_WHOLE_FAMILY_OWNER_PASS", f"files={len(vulkan_family)}")

assert len(physical) == len(set(physical))
print("ENCORE_ACTIVE_SOURCE_CATALOG_PASS",
      f"files={len(physical)}",
      f"graph_exact={sum(path in graph for path in physical)}",
      f"unlinked={sum(path not in graph for path in physical)}",
      f"shipping_sources={len(shipping_cpp)}",
      f"shipping_build_recipes={len(build_recipes)}")
