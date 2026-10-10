#!/usr/bin/env python3
"""Refresh ONLY a fully identified stale C++20 GPU atomic Eden source cache.

The PS5 native renderer compiles C++17, but previously restored source trees
contained std::atomic_ref patch bodies and corresponding application receipts.
Do not change SDK, RADV, ccache, console files or unrelated dependency caches.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PIN = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
OLD = (
    "std::atomic_ref<const u32>(page.compressed_physical_ptr).load(",
    "std::atomic_ref<u32>(page.compressed_physical_ptr).store(",
    "std::atomic_ref<const u32>(page.continuity_tracker).load(",
    "std::atomic_ref<u32>(page.continuity_tracker).store(",
    "std::atomic_ref<const VAddr>(page.cpu_backing_address).load(",
    "std::atomic_ref<VAddr>(page.cpu_backing_address).store(",
    "std::atomic_ref<const u32>(slot).load(",
    "std::atomic_ref<u32>(slot).store(",
)
NEW = (
    "__atomic_load_n(&page.compressed_physical_ptr, __ATOMIC_ACQUIRE)",
    "__atomic_store_n(&page.compressed_physical_ptr, value, __ATOMIC_RELEASE)",
    "__atomic_load_n(&slot, __ATOMIC_ACQUIRE)",
    "__atomic_store_n(&slot, value, __ATOMIC_RELEASE)",
)
RECEIPTS = (
    ".encore-backport-ps5-gpu-atomic-forward-table.sha256",
    ".encore-backport-ps5-gpu-atomic-reverse-table.sha256",
)

def refresh(scratch: Path, archive: Path, owner: Path) -> bool:
    scratch = scratch.resolve(strict=True)
    owner = owner.resolve(strict=True)
    if not scratch.name.startswith("ps5-eden-headless."):
        raise RuntimeError("Not an Encore-owned build-cache directory")
    if (scratch / "owner").read_text().strip() != str(owner):
        raise RuntimeError("Eden cache belongs to a different checkout")
    source = scratch / "source"
    if source.is_symlink():
        raise RuntimeError("Refusing symlinked Eden source cache")
    if not (source / "CMakeLists.txt").is_file():
        return False
    if (source / "GIT-COMMIT").read_text().strip() != PIN:
        raise RuntimeError("Cannot repair unknown Eden snapshot")
    header = source / "src/core/device_memory_manager.h"
    if not header.is_file() or header.is_symlink():
        raise RuntimeError("Cached GPU manager header missing or symlinked")
    content = header.read_text()
    observed = tuple(v in content for v in OLD)
    if not any(observed):
        return False  # normal pristine or already C++17 cache
    if not all(observed) or any(v in content for v in NEW):
        raise RuntimeError("GPU atomic cache is mixed/partial; refusing repair")
    if not all((source / receipt).is_file() for receipt in RECEIPTS):
        raise RuntimeError("Old GPU atomic cache lacks patch receipts")
    if not archive.is_file():
        raise RuntimeError("Pinned Eden source archive missing")
    backup = scratch / ".eden-stale-atomic-backup"
    if backup.exists() or backup.is_symlink():
        raise RuntimeError("Stale GPU cache backup exists; manual recovery required")
    # Inspect the pristine, pinned archive before replacing any live source.
    with tempfile.TemporaryDirectory(prefix=".eden-fresh-atomic-", dir=scratch) as temp:
        fresh = Path(temp)
        subprocess.run(("tar", "-xzf", str(archive), "--strip-components=1",
                        "-C", str(fresh)), check=True, timeout=120)
        fresh_header = fresh / "src/core/device_memory_manager.h"
        if not (fresh / "CMakeLists.txt").is_file() or not fresh_header.is_file():
            raise RuntimeError("Pinned Eden archive missing expected files")
        pristine = fresh_header.read_text()
        if any(v in pristine for v in (*OLD, *NEW)):
            raise RuntimeError("Expected a pristine pinned Eden archive")
        # The pinned archive itself has no GIT-COMMIT receipt. Persist the
        # already-verified pin before the atomic source swap so migration
        # is idempotent even without the outer prepare-build.sh lifecycle.
        (fresh / "GIT-COMMIT").write_text(PIN + "\n")
        store = source / ".cache"
        if store.is_symlink():
            raise RuntimeError("Refusing symlinked upstream CPM store")
        if store.exists() and (fresh / ".cache").exists():
            raise RuntimeError("Pristine source archive contains unexpected .cache store")
        source.rename(backup)
        try:
            fresh.rename(source)
            if (backup / ".cache").exists():
                (backup / ".cache").rename(source / ".cache")
        except Exception:
            # Preserve the backup to diagnose interruption; never claim success.
            raise
        shutil.rmtree(backup)
    print("EDEN_ATOMIC_CACHE_REFRESH pinned source reconstructed for C++17; "
          "CPM dependencies, SDK, RADV and native caches retained", flush=True)
    return True

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: refresh-eden-atomic-source-cache.py <scratch> <pinned-tar.gz> <owner>")
    try:
        refresh(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    except (OSError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as err:
        raise SystemExit("EDEN_ATOMIC_CACHE_REFRESH_REFUSED: " + str(err)) from err
