#!/usr/bin/env python3
"""Install the complete R352 PS5 NVNflinger lifecycle source, not a text patch.

The pristine Eden tree and the independent shipping backport receipts remain
intact. Exact maintained SurfaceFlinger and HardwareComposer translation units
are installed into the disposable preconfigured Eden source tree.
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
COMPOSER_PATH = Path("src/core/hle/service/nvnflinger/hardware_composer.cpp")
COMPOSER_ORIGINAL = ROOT / "vendor/sources/eden" / COMPOSER_PATH
COMPOSER_ACTIVE = ROOT / "vendor/encore-active/eden-surface-lifecycle" / COMPOSER_PATH
COMPOSER_ORIGINAL_GIT_BLOB = "5decb791e1bb1ab2420f386e3fdbdd2b8628a324"

ORIGINAL_GIT_BLOB = "a6136c111d96d2660c28b27c6881e3b671e7eed8"
# Exact predecessor on the same maintained branch. Staged/offline build inputs
# can already contain it; all other unknown edits still fail closed.
PREVIOUS_ACTIVE_GIT_BLOB = "a9fb2da699b1786cdea176d1089f1aea1e5cf351"
EDEN_COMMIT = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"


def blob_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()



# Reconstruct the maintained composer verbatim from the pinned original. No
# changed build input, stale cached composition rule or external file accepted.
COMPOSER_RELEASED_OLD = "        } else {\n            // We didn't acquire a new item, but we can reuse the slot.\n            return CacheStatus::CachedBufferReused;\n        }"
COMPOSER_RELEASED_NEW = "        }\n        // The previous buffer was already RELEASED to the producer. If no\n        // replacement is ready it can no longer be safely sampled: the\n        // producer may be writing into it. Reuse is legal only while acquired.\n        return CacheStatus::NoBufferAvailable;"


def check_composer() -> tuple[bytes, bytes]:
    before = COMPOSER_ORIGINAL.read_bytes()
    after = COMPOSER_ACTIVE.read_bytes()
    if blob_sha(before) != COMPOSER_ORIGINAL_GIT_BLOB:
        raise RuntimeError("Wrong original pinned Eden HardwareComposer source")
    before_text = before.decode()
    if before_text.count(COMPOSER_RELEASED_OLD) != 1:
        raise RuntimeError("Pinned HardwareComposer released-slot branch changed")
    if after != before_text.replace(COMPOSER_RELEASED_OLD, COMPOSER_RELEASED_NEW).encode():
        raise RuntimeError("Maintained HardwareComposer differs from reviewed transformation")
    check_text = after.decode()
    acquired = check_text.split("HardwareComposer::CacheStatus HardwareComposer::CacheFramebufferLocked(", 1)[1]
    if acquired.index("if (it->second.is_acquired)") > acquired.index("return CacheStatus::NoBufferAvailable;"):
        raise RuntimeError("Lost still-acquired frame reuse")
    print("HARDWARE_COMPOSER_PINNED_REPRODUCTION_PASS source and released-slot gate")
    return before, after


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
    check_composer()
    print("SURFACE_LIFECYCLE_VERSIONED_OK exact Eden input SHA and complete sources")
    return before, replacement


def install(destination: Path) -> None:
    before, replacement = check()
    composer_before, composer_replacement = check_composer()
    if (destination / "GIT-COMMIT").read_text().strip() != EDEN_COMMIT:
        raise RuntimeError("Refusing lifecycle source replacement on unknown Eden pin")

    # Verify ALL existing files before writing either one. Cached staged trees
    # may carry the exact previous SurfaceFlinger release, but nothing else.
    sources = (
        (PATH, ACTIVE, before, replacement, PREVIOUS_ACTIVE_GIT_BLOB, "SurfaceFlinger"),
        (COMPOSER_PATH, COMPOSER_ACTIVE, composer_before, composer_replacement, None, "HardwareComposer"),
    )
    for rel, source, original, maintained, previous, label in sources:
        existing = (destination / rel).read_bytes()
        if existing not in (original, maintained) and (
            previous is None or blob_sha(existing) != previous
        ):
            raise RuntimeError("Unknown " + label + " input: refusing unsafe overwrite")

    for rel, source, original, maintained, previous, label in sources:
        target = destination / rel
        if target.read_bytes() != maintained:
            temporary = target.with_name(target.name + ".encore-" + str(os.getpid()))
            try:
                shutil.copy2(source, temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        if target.read_bytes() != maintained:
            raise RuntimeError("Compiled " + label + " input did not match active source")
    print("SURFACE_LIFECYCLE_INSTALLED idempotent exact-source replacement units=2")


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
