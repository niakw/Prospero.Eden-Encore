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
    'src/amd/vulkan/radv_descriptor_update_template.c',
    'src/amd/vulkan/radv_descriptor_update_template.h',
    'src/amd/vulkan/radv_physical_device.c',
    'src/amd/vulkan/meta/radv_meta_clear.c',
    'src/amd/vulkan/meta/radv_meta_resolve.c',
    'src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c',
    'src/amd/vulkan/winsys/ps5/radv_ps5_platform.c',
    'src/util/disk_cache_os.c',
)

# Only exact, Git-verified prior Encore build inputs are accepted.
# A cache restored from an old Actions run can contain complete R343 active
# RADV units mixed with R398 WSI. Each historical byte stream is archived in
# tools/fixtures and checked against its SHA256 in check-vendored-radv-fork.py.
# Never accept arbitrary native cache edits and never mutate immutable Mesa.
# R343 source commit: 1c874ff951b02cf6ea8cef7ce4b110258727575c
# R398 WSI was byte-identical to the R343 WSI.
LEGACY_COMPILER_SHA256 = {
    'src/vulkan/wsi/wsi_common_videoout.c': frozenset({
        '6d54b8d68cc383faa9bbd910e327824689b5315e7ee5617d8981f582c47c2eaa',
    }),
    'src/amd/vulkan/radv_cmd_buffer.c': frozenset({
        '27e4953853887778ca9fae7ef4114ec42e275b550754d6f6b2d218a692e867f5',
    }),
    'src/amd/vulkan/radv_physical_device.c': frozenset({
        '56aed8905eea35687a7e263375ad216843eb5cc4c474f4eb791addaa2599341d',
    }),
    'src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c': frozenset({
        '0aa478ae4c4d3331177185e7a42386c0dc23fc9ff3869333c34ffaafe5e213b0',
    }),
    'src/amd/vulkan/winsys/ps5/radv_ps5_platform.c': frozenset({
        '8112c2b41a600043d3096a0198c4e3c2d7dcf6b56e8f738f6ce8eb537943725c',
    }),
}


def approved_compiler_input(relative: str, compiled_sha: str, raw_sha: str, active_sha: str) -> bool:
    return (compiled_sha in (raw_sha, active_sha) or
            compiled_sha in LEGACY_COMPILER_SHA256.get(relative, ()))


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
        if not approved_compiler_input(relative, before, raw_sha, fork_sha):
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
