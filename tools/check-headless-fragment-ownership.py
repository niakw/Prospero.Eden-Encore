#!/usr/bin/env python3
"""Audit remaining headless .inc consumers and maintained OpenGL DEV fragment.

Scope is code/config in app headless/, local src/, and maintained vendor
encore-active/. Does not claim to scan pinned vendor/sources or external
SDK caches; this is a source-graph contract, not hardware qualification.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
headless = ROOT / "headless"
fragments = sorted(p.name for p in headless.glob("*.inc") if p.is_file())
assert fragments == ["gpu_native_probe.inc", "gpu_probe.inc"], (
    "Unexpected unclassified headless fragment", fragments)
old = headless/"dev_render_passes.inc"
maintained = ROOT/"vendor/encore-active/eden-core/src/video_core/renderer_opengl/dev_render_passes.inc"
dev_rasterizer = ROOT/"vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_rasterizer_dev.cpp"
normal_rasterizer = ROOT/"vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_rasterizer.cpp"
assert not old.exists(), "DEV diagnostic fragment must have exactly one Encore owner"
assert maintained.is_file()
assert "static void CaptureDevelopmentPass()" in maintained.read_text()
assert dev_rasterizer.read_text().startswith('#include "dev_render_passes.inc"')
assert dev_rasterizer.read_text().count("CaptureDevelopmentPass();") == 1
assert '#include "dev_render_passes.inc"' not in normal_rasterizer.read_text()
graphics = (headless/"graphics.cpp").read_text(encoding="utf-8")
probe = (headless/"gpu_probe.inc").read_text(encoding="utf-8")
assert '#ifdef EDEN_GPU_PROBE\n#include "gpu_probe.inc"\n#endif' in graphics
assert '#include "gpu_native_probe.inc"' in probe

# The DEV rasterizer is the one expected consumer. Detect new competing
# includes or untracked calls anywhere in the active app/Encore source tree.
patterns = ("dev_render_passes.inc", "CaptureDevelopmentPass(")
extensions = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".inc",
              ".cmake", ".sh"}
scan_roots = (ROOT/"headless", ROOT/"src", ROOT/"vendor/encore-active")
found = []
scanned = 0
for source_root in scan_roots:
    for path in source_root.rglob("*"):
        if not path.is_file() or path.suffix not in extensions:
            continue
        if path == maintained:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(p in text for p in patterns):
            found.append(str(path.relative_to(ROOT)))
assert found == [str(dev_rasterizer.relative_to(ROOT))], (
    "OpenGL DEV fragment must have one direct maintained rasterizer owner", found)
assert not (headless/"macro_recovery.cmake").exists()
assert not (headless/"slot_vector_recovery.cmake").exists()
assert (ROOT/"vendor/encore-active/eden-core/src/video_core/macro.cpp").is_file()
assert (ROOT/"vendor/encore-active/eden-core/overrides/slot-vector/common/slot_vector.h").is_file()
print(f"ENCORE_HEADLESS_FRAGMENT_OWNERSHIP_PASS fragments=2 "
      f"consumed_probe_fragments=2 maintained_dev_gl=1 "
      f"retired_X01_X02=2 scanned_inputs={scanned}")
