#!/usr/bin/env python3
"""Read-only BNTX/NX Switch container texture inventory for PS glyph discovery.

Parses header, explicit BRTI pointer table and a small bounded header for each
texture. Never unswizzles/decompresses mip data, never modifies Nintendo art and
never assumes an internal texture is actually a button atlas.
Based on publicly documented BNTX file structures (3DSkit, BNTX-Injector).
All offsets validated against actual file size; unexpected layouts fail closed.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TEXTURES = 256
MAX_NAME_BYTES = 256
BRTI_BYTES = 0xA0
FORMATS = {
    0x02: "L8", 0x07: "RGB565", 0x09: "RG8", 0x0A: "L16",
    0x0B: "RGBA8", 0x0F: "R11G11B10", 0x14: "L32",
    0x1A: "BC1", 0x1B: "BC2", 0x1C: "BC3",
    0x1D: "BC4", 0x1E: "BC5", 0x1F: "BC6H", 0x20: "BC7",
}
ASTC_DIMENSIONS = {
    0x2D: (4, 4), 0x2E: (5, 4), 0x2F: (5, 5),
    0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5),
    0x33: (8, 6), 0x34: (8, 8), 0x35: (10, 5),
    0x36: (10, 6), 0x37: (10, 8), 0x38: (10, 10),
    0x39: (12, 10), 0x3A: (12, 12),
}
HINTS = ("button", "btn", "input", "controller", "gamepad",
         "prompt", "icon", "hud", "menu", "ui", "key")


class InvalidBntx(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise InvalidBntx(reason)


def inspect(file: Path) -> dict:
    require(file.is_file() and not file.is_symlink(), "not an ordinary BNTX file")
    size = file.stat().st_size
    require(0x40 <= size <= MAX_FILE_BYTES, "BNTX size outside allowed bounds")
    with file.open("rb") as stream:
        def read_at(offset: int, length: int) -> bytes:
            require(0 <= offset <= size and 0 <= length <= size - offset,
                    "invalid BNTX offset/size")
            stream.seek(offset)
            data = stream.read(length)
            require(len(data) == length, "truncated BNTX data")
            return data

        header = read_at(0, 0x40)
        require(header[:8] == b"BNTX\0\0\0\0", "invalid BNTX magic")
        marker = header[0x0C:0x0E]
        require(marker in (b"\xff\xfe", b"\xfe\xff"),
                "unsupported BNTX byte order")
        endian = "<" if marker == b"\xff\xfe" else ">"
        reported_size = struct.unpack_from(endian + "I", header, 0x1C)[0]
        require(reported_size == size, "BNTX declared size mismatch")
        target = header[0x20:0x24]
        require(target == b"NX  ", "not a Switch NX texture container")
        count = struct.unpack_from(endian + "I", header, 0x24)[0]
        require(0 < count <= MAX_TEXTURES, "invalid BNTX texture count")
        table_ptr = struct.unpack_from(endian + "Q", header, 0x28)[0]
        table = read_at(table_ptr, count * 8)
        textures = []
        for index in range(count):
            pointer = struct.unpack_from(endian + "Q", table, index * 8)[0]
            brti = read_at(pointer, BRTI_BYTES)
            require(brti[:4] == b"BRTI",
                    f"texture {index}: invalid BRTI magic")
            tile_mode, mipmaps = struct.unpack_from(endian + "HH", brti, 0x12)[0], (
                struct.unpack_from(endian + "H", brti, 0x16)[0])
            fmt = struct.unpack_from(endian + "I", brti, 0x1C)[0]
            width, height, depth, array_len = struct.unpack_from(endian + "IIII", brti, 0x24)
            image_bytes = struct.unpack_from(endian + "I", brti, 0x50)[0]
            dimension = brti[0x5C]
            name_ptr = struct.unpack_from(endian + "Q", brti, 0x60)[0]
            require(0 < width <= 16384 and 0 < height <= 16384 and
                    0 < depth <= 2048 and 0 < array_len <= 2048 and
                    1 <= mipmaps <= 16 and 0 < image_bytes <= MAX_FILE_BYTES,
                    f"texture {index}: invalid dimensions/mips")
            require(name_ptr > 0, f"texture {index}: name pointer absent")
            string_size = struct.unpack(endian + "H", read_at(name_ptr, 2))[0]
            require(0 < string_size <= MAX_NAME_BYTES,
                    f"texture {index}: name outside bounds")
            name_bytes = read_at(name_ptr + 2, string_size)
            name = name_bytes.decode("utf-8", errors="replace")
            # Avoid control sequences in logs/JSON output.
            name = "".join(c for c in name if c.isprintable())[:MAX_NAME_BYTES]
            format_group = (fmt >> 8) & 0xFF
            format_name = (f"ASTC{ASTC_DIMENSIONS[format_group][0]}x"
                           f"{ASTC_DIMENSIONS[format_group][1]}"
                           if format_group in ASTC_DIMENSIONS
                           else FORMATS.get(format_group, "UNKNOWN"))
            textures.append({
                "name": name, "width": width, "height": height,
                "format": format_name, "format_code": f"0x{fmt:08x}",
                "tile_mode": tile_mode, "mip_count": mipmaps,
                "depth": depth, "array_length": array_len,
                "dimension": dimension, "encoded_image_bytes": image_bytes,
                "candidate_name": any(hint in name.lower() for hint in HINTS),
                "read_only": True,
            })
    return {
        "kind": "BNTX_NX_read_only_metadata",
        "texture_count": len(textures),
        "textures": textures,
        "warning": "Inspection only: no deswizzle, ASTC/BC decode, repack or in-game replacement",
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("file", type=Path, help="locally extracted game BNTX file")
    args = cli.parse_args()
    try:
        print(json.dumps(inspect(args.file), indent=2))
        return 0
    except (InvalidBntx, OSError, struct.error) as error:
        print(f"REJECTED BNTX: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
