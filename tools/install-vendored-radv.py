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
)

# Only an *exact*, previously published Encore active source is accepted as
# cached compiler input. Unlike a global bypass this does not trust arbitrary
# patches from a stale or contaminated cache. Confirmed against the Git blob
# 6e77c7e40de7158fe46774221934622c9411fbd7 at native R398 SHA ab1ed98a.
LEGACY_COMPILER_SHA256 = {
    'src/vulkan/wsi/wsi_common_videoout.c': frozenset({
        '6d54b8d68cc383faa9bbd910e327824689b5315e7ee5617d8981f582c47c2eaa',
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
