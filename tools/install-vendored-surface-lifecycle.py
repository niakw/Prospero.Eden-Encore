#!/usr/bin/env python3
"""Install the complete R352 PS5 NVNflinger lifecycle source, not a text patch.

The pristine Eden tree and the 43 independent shipping backport receipts remain
intact. Only the full checked-in SurfaceFlinger translation unit is installed
into the disposable, preconfigured Eden source tree.
"""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PATH = Path("src/core/hle/service/nvnflinger/surface_flinger.cpp")
ORIGINAL = ROOT / "vendor/sources/eden" / PATH
ACTIVE = ROOT / "vendor/encore-active/eden-surface-lifecycle" / PATH
ORIGINAL_GIT_BLOB = "a6136c111d96d2660c28b27c6881e3b671e7eed8"
EDEN_COMMIT = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"


def blob_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def check() -> tuple[bytes, bytes]:
    before = ORIGINAL.read_bytes()
    replacement = ACTIVE.read_bytes()
    if blob_sha(before) != ORIGINAL_GIT_BLOB:
        raise RuntimeError("Wrong original pinned Eden SurfaceFlinger source")
    if not replacement.startswith(before[:100]):
        raise RuntimeError("Active SurfaceFlinger source header no longer matches upstream")
    text = replacement.decode()
    for marker in (
        "void SurfaceFlinger::RemoveDisplay(",
        "void SurfaceFlinger::DestroyLayer(",
        "void SurfaceFlinger::RemoveLayerFromDisplayStack(",
        "void SurfaceFlinger::AddLayerToDisplayStack(",
        "WaitForComposite();",
        "m_composer.RemoveLayerLocked(",
    ):
        if marker not in text:
            raise RuntimeError("Lost critical display release operation: " + marker)
    add_method = text.split("void SurfaceFlinger::AddLayerToDisplayStack(", 1)[1].split(
        "void SurfaceFlinger::RemoveLayerFromDisplayStack(", 1)[0]
    assert "std::any_of(display->stack.layers.begin()" in add_method
    assert "return attached->consumer_id == consumer_binder_id;" in add_method
    assert add_method.index("std::any_of(") < add_method.index("emplace_back(")
    if text.count("WaitForComposite();") != 2:
        raise RuntimeError("Unexpected number of explicit composite fence waits")
    print("SURFACE_LIFECYCLE_VERSIONED_OK exact Eden input SHA and complete source")
    return before, replacement


def install(destination: Path) -> None:
    before, replacement = check()
    if (destination / "GIT-COMMIT").read_text().strip() != EDEN_COMMIT:
        raise RuntimeError("Refusing SurfaceFlinger source replacement on unknown Eden pin")
    target = destination / PATH
    existing = target.read_bytes()
    if existing not in (before, replacement):
        raise RuntimeError("Unknown SurfaceFlinger input: refusing unsafe overwrite")
    if existing != replacement:
        temporary = target.with_name(target.name + ".encore-" + str(os.getpid()))
        try:
            shutil.copy2(ACTIVE, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    if target.read_bytes() != replacement:
        raise RuntimeError("Compiled SurfaceFlinger input did not match active source")
    print("SURFACE_LIFECYCLE_INSTALLED idempotent exact-source replacement")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("destination", nargs="?", type=Path)
    args = parser.parse_args()
    if args.check:
        check()
    if args.destination:
        install(args.destination)
    if not args.check and args.destination is None:
        parser.error("requires --check or disposable Eden source directory")
