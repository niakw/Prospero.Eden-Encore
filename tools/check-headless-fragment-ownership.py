#!/usr/bin/env python3
"""Audit remaining headless .inc consumers and orphaned local diagnostics.

Scope is code/config in app headless/, local src/, and maintained vendor
encore-active/. Does not claim to scan pinned vendor/sources or external
SDK caches; this is a source-graph contract, not hardware qualification.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
headless = ROOT / "headless"
fragments = sorted(p.name for p in headless.glob("*.inc") if p.is_file())
assert fragments == [
    "dev_render_passes.inc", "gpu_native_probe.inc", "gpu_probe.inc"
], ("Unexpected unclassified headless fragments", fragments)
graphics = (headless/"graphics.cpp").read_text(encoding="utf-8")
probe = (headless/"gpu_probe.inc").read_text(encoding="utf-8")
assert '#ifdef EDEN_GPU_PROBE\n#include "gpu_probe.inc"\n#endif' in graphics
assert '#include "gpu_native_probe.inc"' in probe

# If the previously orphaned diagnostic becomes reachable, require an
# explicit reclassification rather than calling a hidden include a test.
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
        if path == headless/"dev_render_passes.inc":
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(p in text for p in patterns):
            found.append(str(path.relative_to(ROOT)))
assert not found, ("OpenGL pass diagnostic has new active consumers; "
                   "requalify its source ownership before build", found)
assert not (headless/"macro_recovery.cmake").exists()
assert not (headless/"slot_vector_recovery.cmake").exists()
assert (ROOT/"vendor/encore-active/eden-core/src/video_core/macro.cpp").is_file()
assert (ROOT/"vendor/encore-active/eden-core/overrides/slot-vector/common/slot_vector.h").is_file()
print(f"ENCORE_HEADLESS_FRAGMENT_OWNERSHIP_PASS fragments=3 "
      f"consumed_probe_fragments=2 orphaned_local_diagnostics=1 "
      f"retired_X01_X02=2 scanned_inputs={scanned}")
