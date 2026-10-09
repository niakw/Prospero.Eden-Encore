#!/usr/bin/env python3
"""Bounded, READ-ONLY Nintendo SARC/BLARC archive member/offset inventory.

Accepts only already decompressed SARC v0x100 files. TotK .blarc.zs requires
separate dictionary-aware Zstandard decompression using a user-provided game
dictionary; this tool never decrypts/dumps games, extracts or edits members.
Reports names and absolute byte offsets, NOT sprite pixel positions.
Format: https://nintendo-formats.com/libs/sead/sarc.html
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

MAX_BYTES = 128 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_NAME = 512
HINTS = ("button", "btn", "controller", "prompt", "input",
         "icon", "key", "hud", "ui", "texture", "tex", "font", "layout")


class InvalidSarc(ValueError):
    pass


def require(valid: bool, message: str) -> None:
    if not valid:
        raise InvalidSarc(message)


def inventory(file: Path) -> dict:
    require(file.is_file() and not file.is_symlink(), "not a regular archive")
    size = file.stat().st_size
    require(0x20 <= size <= MAX_BYTES, "archive size outside bounds")
    data = file.read_bytes()
    require(len(data) == size, "incomplete archive read")
    require(data[:4] == b"SARC",
            "not an uncompressed SARC (a .zs file needs dictionary-aware decompression first)")
    bom = data[6:8]
    require(bom in (b"\xff\xfe", b"\xfe\xff"), "unsupported byte order")
    endian = "<" if bom == b"\xff\xfe" else ">"

    def u16(offset: int) -> int:
        require(0 <= offset <= size - 2, "truncated u16")
        return struct.unpack_from(endian + "H", data, offset)[0]

    def u32(offset: int) -> int:
        require(0 <= offset <= size - 4, "truncated u32")
        return struct.unpack_from(endian + "I", data, offset)[0]

    header_size = u16(4)
    require(header_size == 0x14, "unsupported SARC header")
    require(u32(8) == size, "declared SARC size mismatch")
    data_start = u32(0x0c)
    require(u16(0x10) == 0x100, "unsupported SARC version")
    require(data[header_size:header_size + 4] == b"SFAT", "missing SFAT")
    require(u16(header_size + 4) == 0x0c, "unsupported SFAT header")
    count = u16(header_size + 6)
    require(0 <= count <= MAX_ENTRIES, "excessive SARC entries")
    multiplier = u32(header_size + 8)
    table = header_size + 0x0c
    sfnt = table + count * 0x10
    require(sfnt + 8 <= size and data[sfnt:sfnt + 4] == b"SFNT",
            "missing/truncated SFNT")
    require(u16(sfnt + 4) == 8, "unsupported SFNT header")
    names_offset = sfnt + 8
    require(names_offset <= data_start <= size, "invalid data section offset")

    entries = []
    prior_hash = -1
    seen_names = set()
    for index in range(count):
        ptr = table + index * 0x10
        h = u32(ptr)
        attr = u32(ptr + 4)
        start = u32(ptr + 8)
        end = u32(ptr + 12)
        require(h >= prior_hash, "unsorted SARC filename hashes")
        prior_hash = h
        require(0 <= start <= end <= size - data_start, "invalid member data range")
        name = None
        if attr != 0:
            string_ptr = names_offset + (attr & 0x00ffffff) * 4
            require(names_offset <= string_ptr < data_start,
                    "member name pointer outside string table")
            stop = data.find(b"\x00", string_ptr, min(data_start, string_ptr + MAX_NAME + 1))
            require(stop >= 0 and stop > string_ptr, "missing/empty bounded member name")
            encoded_name = data[string_ptr:stop]
            name = encoded_name.decode("utf-8", "replace")
            require(all(c.isprintable() for c in name), "nonprintable SARC name")
            require(name.casefold() not in seen_names, "duplicate SARC member name")
            seen_names.add(name.casefold())
        absolute = data_start + start
        entries.append({
            "name": name,
            "hash": f"{h:08x}",
            "content_offset": absolute,
            "content_bytes": end - start,
            "name_offset": (names_offset + (attr & 0x00ffffff) * 4) if attr else None,
            "magic": data[absolute: min(absolute + 8, data_start + end)].hex(),
            "ui_candidate": bool(name and any(hint in name.lower() for hint in HINTS)),
        })
    digest = hashlib.sha256(data).hexdigest()
    return {
        "kind": "SARC_v0100_read_only",
        "archive_sha256": digest,
        "archive_bytes": size,
        "data_section_offset": data_start,
        "hash_multiplier": multiplier,
        "member_count": count,
        "members": entries,
        "warning": "Offsets are byte locations within decompressed SARC, NOT pixel coordinates. Never use as renderer glyph slots.",
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("file", type=Path, help="already decompressed SARC/BLARC")
    cli.add_argument("--out", type=Path, help="new JSON file only")
    args = cli.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise InvalidSarc("unsafe output location")
        report = json.dumps(inventory(args.file), indent=2) + "\n"
        if args.out:
            args.out.write_text(report, encoding="utf-8")
            print(f"SARC INVENTORY {args.out}")
        else:
            print(report, end="")
        return 0
    except (InvalidSarc, OSError, UnicodeError, struct.error) as error:
        print(f"REJECTED SARC: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
