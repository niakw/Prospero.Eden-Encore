#!/usr/bin/env python3
"""Bind a reused native graphics archive to *all* maintained compiler inputs.

The Mesa commit SHA alone is insufficient: Encore replaces 12 native Mesa
source units after staging, while the old binary cache checked only the WSI
file. Fingerprint every maintained translation unit, then stamp only after
a successful RADV rebuild with those exact staged bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import runpy
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "vendor/encore-active/ps5-mesa"
INSTALLER = ROOT / "tools/install-vendored-radv.py"
PATHS = tuple(runpy.run_path(str(INSTALLER))["PATHS"])
assert len(PATHS) == len(set(PATHS)) == 12


def fingerprint(base: Path) -> str:
    h = hashlib.sha256()
    for relative in PATHS:
        data = (base / relative).read_bytes()
        h.update(relative.encode("utf-8"))
        h.update(b"\0")
        h.update(len(data).to_bytes(8, "big"))
        h.update(hashlib.sha256(data).digest())
    return h.hexdigest()


def matches(stamp: Path) -> bool:
    try:
        recorded = stamp.read_text().strip()
    except FileNotFoundError:
        return False
    return recorded == fingerprint(ACTIVE)


def write_if_compiled(stage: Path, archive: Path, stamp: Path) -> str:
    if not archive.is_file() or archive.stat().st_size == 0:
        raise RuntimeError("Cannot stamp graphics inputs without a built driver archive")
    expected = fingerprint(ACTIVE)
    staged = fingerprint(stage)
    if staged != expected:
        raise RuntimeError("Native driver staged sources differ from the maintained source set")
    stamp.parent.mkdir(parents=True, exist_ok=True)
    temporary = stamp.with_name(stamp.name + ".new")
    try:
        temporary.write_text(expected + "\n")
        os.replace(temporary, stamp)
    finally:
        temporary.unlink(missing_ok=True)
    assert matches(stamp)
    return expected


def self_test():
    with tempfile.TemporaryDirectory(prefix="encore-native-input-stamp-") as td:
        d = Path(td)
        stage = d / "stage"
        marker = d / "source-inputs.sha256"
        archive = d / "driver.a"
        for relative in PATHS:
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ACTIVE / relative, target)
        assert fingerprint(stage) == fingerprint(ACTIVE)
        assert not matches(marker)
        try:
            write_if_compiled(stage, archive, marker)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Never stamp sources without a completed archive")
        archive.write_bytes(b"fake compiled archive for stamp contract only")
        write_if_compiled(stage, archive, marker)
        assert matches(marker)
        target = stage / PATHS[-1]
        original = target.read_bytes()
        target.write_bytes(original + b"\n/* cache drift fixture */\n")
        try:
            write_if_compiled(stage, archive, marker)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Refuse to stamp staged code that differs from active")
        target.write_bytes(original)
        assert fingerprint(stage) == fingerprint(ACTIVE)
        marker.write_text("0" * 64 + "\n")
        assert not matches(marker)
        # Each individual source mutation must invalidate the complete set.
        for relative in PATHS:
            target = stage / relative
            original = target.read_bytes()
            target.write_bytes(original + b"!")
            assert fingerprint(stage) != fingerprint(ACTIVE)
            target.write_bytes(original)
            assert fingerprint(stage) == fingerprint(ACTIVE)
    script = (ROOT / "tools/prepare-build.sh").read_text()
    build = (ROOT / "tools/build-radv-dependencies.sh").read_text()
    assert 'radv-active-inputs.py --check' in script
    assert 'radv-active-inputs.py" --stamp' in build  # absolute script path is quoted
    assert 'EDEN_ACTIVE_INPUTS_SHA256' in script and 'EDEN_ACTIVE_INPUTS_SHA256' in build
    print(f"DRIVER_SOURCE_CACHE_KEY_PASS maintained_compiler_units={len(PATHS)} stale_archive_rejected")


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", type=Path, metavar="STAMP")
    actions.add_argument("--stamp", type=Path, metavar="STAGE")
    actions.add_argument("--self-test", action="store_true")
    parser.add_argument("paths", type=Path, nargs="*")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.check:
        if args.paths: parser.error("--check accepts only the stamp filename")
        if not matches(args.check):
            raise SystemExit("STALE_DRIVER_INPUTS: rebuilt source stamp is absent or mismatched")
        print(f"DRIVER_COMPILER_INPUTS_MATCH units={len(PATHS)}")
    else:
        if len(args.paths) != 2:
            parser.error("--stamp needs DRIVER_ARCHIVE and STAMP paths")
        digest = write_if_compiled(args.stamp, args.paths[0], args.paths[1])
        print(f"DRIVER_COMPILER_INPUTS_STAMPED units={len(PATHS)} sha256=" + digest)


if __name__ == "__main__":
    main()
