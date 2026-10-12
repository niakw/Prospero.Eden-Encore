#!/usr/bin/env python3
"""Install complete checked-in, PS5-patched RADV translation units into Meson's staging tree.

Does NOT mutate the source-controlled upstream Mesa snapshot, and never executes
old replacement expressions as part of the production PS5 build.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import argparse
import json
import os
import shutil

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / 'vendor/sources/ps5-mesa'
ACTIVE = ROOT / 'vendor/encore-active/ps5-mesa'
PATHS = (
    'src/vulkan/wsi/wsi_common_videoout.c',
    'src/amd/vulkan/radv_cmd_buffer.c',
    'src/amd/vulkan/radv_pipeline.c',
    'src/amd/vulkan/radv_physical_device.c',
    'src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c',
    'src/amd/vulkan/winsys/ps5/radv_ps5_platform.c',
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(destination: Path, provenance: Path | None) -> None:
    installed = {}
    changed = False
    for relative in PATHS:
        original = ORIGINAL / relative
        canonical = ACTIVE / relative
        compiled = destination / relative
        if not original.is_file() or not canonical.is_file() or not compiled.is_file():
            raise RuntimeError(f'RADV source missing before installation: {relative}')
        before = digest(compiled)
        raw_sha = digest(original)
        fork_sha = digest(canonical)
        if before not in (raw_sha, fork_sha):
            raise RuntimeError(f'Unrecognized RADV compiler input (refusing to clobber): {relative}, sha256={before}')
        if before != fork_sha:
            # Atomic replacement allows incremental Ninja to detect only the
            # translated units whose behavior actually differs from upstream.
            temporary = compiled.with_name(compiled.name + f'.active-{os.getpid()}')
            try:
                shutil.copy2(canonical, temporary)
                temporary.replace(compiled)
            finally:
                temporary.unlink(missing_ok=True)
            changed = True
        installed[relative] = fork_sha
    if changed and provenance is not None and provenance.exists():
        provenance.replace(provenance.with_suffix('.base.txt'))
    # Always check the final bytes, independently of the chosen source path.
    for relative, expected in installed.items():
        if digest(destination / relative) != expected:
            raise RuntimeError(f'RADV built source changed after active install: {relative}')
    print(f'VENDORED_RADV_INSTALLED changed={changed} files={len(installed)} wsi_sha256={installed[PATHS[0]]}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path, help='Existing mihawk-vulkan-review/.deps/work/radv-src')
    parser.add_argument('--provenance', type=Path)
    args = parser.parse_args()
    install(args.destination, args.provenance)
