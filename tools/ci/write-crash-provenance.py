#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bind an uploaded unstripped ELF to the *same staged native test app*.

This is build-output bookkeeping only; no SDK, signing or native execution.
A match in these hashes documents provenance, NOT that the signed SELF's
internal code was reconstructed or that the ELF identifies a system-library
RIP. The crash symbolizer still rejects mismatching .text sizes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]


def checked(path: Path, expected_dir: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.parent.resolve() != expected_dir.resolve():
        raise ValueError(f"missing/untrusted build output: {path}")
    size = path.stat().st_size
    if not 128 <= size <= 1024 * 1024 * 1024:
        raise ValueError(f"unreasonable build output size: {path}")
    return path.read_bytes()


def text_size(elf: bytes) -> int:
    if len(elf) < 64 or elf[:4] != b"\x7fELF" or elf[4] != 2 or elf[5] != 1:
        raise ValueError("not a little-endian 64-bit ELF")
    shoff = struct.unpack_from("<Q", elf, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", elf, 0x3A)
    if not shnum or shentsize < 64 or shstrndx >= shnum or shoff + shentsize * shnum > len(elf):
        raise ValueError("bad ELF section table")
    entries = [struct.unpack_from("<IIQQQQIIQQ", elf, shoff + shentsize * i)
               for i in range(shnum)]
    names_off, names_size = entries[shstrndx][4:6]
    if names_off + names_size > len(elf):
        raise ValueError("bad ELF section names")
    for entry in entries:
        name_idx, _, _, _, offset, size, *_ = entry
        if name_idx >= names_size:
            raise ValueError("ELF section name out of bounds")
        end = elf.find(b"\0", names_off + name_idx, names_off + names_size)
        if end < 0:
            raise ValueError("unterminated ELF section name")
        if elf[names_off + name_idx:end] == b".text":
            if not size or offset + size > len(elf):
                raise ValueError("invalid .text section extent")
            return size
    raise ValueError("missing ELF .text section")


def write_manifest(app: Path, native: Path, output: Path, title_id: str) -> dict:
    if app.resolve() != (ROOT / "build/dev/PPSA99008").resolve():
        raise ValueError("not the isolated development title")
    if native.resolve() != (ROOT / "build/headless-native").resolve():
        raise ValueError("not the current native build output directory")
    if output.resolve() != (native / "crash-provenance.json").resolve() or output.exists() or output.is_symlink():
        raise ValueError("output must be a new crash-provenance.json in native build")
    if len(title_id) != 16 or any(ch not in "0123456789abcdefABCDEF" for ch in title_id):
        raise ValueError("invalid title ID")
    paths = {"unstripped_elf": native / "llvm-pie.elf",
             "link_map": native / "link.map",
             "staged_eboot": app / "eboot.bin"}
    data = {name: checked(path, path.parent) for name, path in paths.items()}
    if len(data["unstripped_elf"]) <= 1024 * 1024 or len(data["staged_eboot"]) <= 1024 * 1024:
        raise ValueError("native executable or symbol ELF unexpectedly small")
    manifest = {
        "schema": 1,
        "source": "same-run compiled outputs, not PS5 hardware verification",
        "test_title_id": title_id.upper(),
        "source_commit": os.getenv("GITHUB_SHA", "unknown"),
        "workflow_run": os.getenv("GITHUB_RUN_ID", "local"),
        "elf_text_size_hex": f"0x{text_size(data['unstripped_elf']):x}",
        "files": {
            name: {"name": paths[name].name, "size_bytes": len(contents),
                   "sha256": hashlib.sha256(contents).hexdigest()}
            for name, contents in data.items()
        },
        "confirmed_same_console_binary": False,
        "native_ps5_execution_verified": False,
    }
    with output.open("x", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, sort_keys=True)
        file.write("\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test-title", required=True)
    args = parser.parse_args()
    try:
        receipt = write_manifest(args.app, args.native, args.output, args.test_title)
        print("EDEN_CRASH_SYMBOL_PROVENANCE " + json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError, struct.error) as error:
        print(f"EDEN_CRASH_SYMBOL_PROVENANCE_REJECTED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
