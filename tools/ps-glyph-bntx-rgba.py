#!/usr/bin/env python3
"""Decode and surgically update a supported Switch BNTX RGBA8 UI texture.

No general-purpose BNTX injector: only standalone 2D, one-mip RGBA8
textures with explicit verified byte spans, pitch-linear or Tegra X1
block-linear memory. Other formats, arrays and mipmapped art fail CLOSED.
Surgery keeps *every byte outside the original texture's active pixels*
unchanged; BNTX header, resource paths, layout and file size are retained.

Position discovery and button semantics are separate steps. This module
does not guess atlas rects, source update IDs, or game control mappings.

Tegra GOB layout based on public hardware docs / tegra_swizzle research;
all offset calculations are bounded against the original image span.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("eden_glyph_bntx_rgba_inspect",
                                             HERE / "ps-glyph-bntx-inspect.py")
if sp is None or sp.loader is None:
    raise SystemExit("missing ps-glyph-bntx-inspect.py")
inspect = importlib.util.module_from_spec(sp)
sp.loader.exec_module(inspect)

MAX_PIXELS = 16_777_216
MAX_BYTES = 128 * 1024 * 1024


class InvalidTexture(ValueError):
    pass


def require(valid: bool, reason: str) -> None:
    if not valid:
        raise InvalidTexture(reason)


def round_up(value: int, n: int) -> int:
    return (value + n - 1) // n * n


def pixel_offset(x: int, y: int, width: int, height: int,
                 tile_mode: int, block_height_log2: int, element_bytes: int = 4) -> int:
    """Physical offset for one RGBA8 pixel or ASTC 16-byte block.

    The caller supplies dimensions measured in *elements*, not pixels
    for compressed ASTC. Tegra block-linear uses 64x8-byte GOBs.
    """
    require(all(type(n) is int for n in (x, y, width, height, tile_mode,
                                          block_height_log2, element_bytes)),
            "invalid element coordinates")
    require(0 <= x < width and 0 <= y < height and 0 < width <= 16384 and
            0 < height <= 16384 and element_bytes in (1, 2, 4, 8, 16) and
            tile_mode in (0, 1) and 0 <= block_height_log2 <= 5,
            "invalid texture tile geometry")
    offset = x * element_bytes
    if tile_mode == 1:
        # Switch BNTX NX pitch-linear textures use 32-byte row alignment.
        return y * round_up(width * element_bytes, 32) + offset
    block_height = 1 << block_height_log2
    width_gobs = round_up(width * element_bytes, 64) // 64
    return (
        (y // (8 * block_height)) * 512 * block_height * width_gobs +
        (offset // 64) * 512 * block_height +
        ((y % (8 * block_height)) // 8) * 512 +
        ((offset % 64) // 32) * 256 +
        ((y % 8) // 2) * 64 +
        ((offset % 32) // 16) * 32 +
        (y % 2) * 16 +
        offset % 16
    )


def surface_size(width: int, height: int, mode: int,
                 block_height_log2: int, element_bytes: int = 4) -> int:
    require(0 < width <= 16384 and 0 < height <= 16384, "invalid surface size")
    if mode == 1:
        return round_up(width * element_bytes, 32) * height
    require(mode == 0, "invalid tile mode")
    return round_up(width * element_bytes, 64) * (
        round_up(height, 8 * (1 << block_height_log2)))


def describe(blob: bytes, texture_name: str) -> dict:
    require(isinstance(blob, bytes) and 0x40 <= len(blob) <= MAX_BYTES,
            "invalid BNTX size")
    require(isinstance(texture_name, str) and texture_name and
            len(texture_name) <= 256, "texture name missing")
    info = inspect.inspect(blob)
    matches = [x for x in info["textures"] if
               x["name"].casefold() == texture_name.casefold()]
    require(len(matches) == 1, "missing/ambiguous BNTX texture")
    tex = matches[0]
    require(tex["format_code"] == "0x00000b01", "only RGBA8_UNORM 0x0B01 qualified")
    require(tex["depth"] == tex["array_length"] == tex["mip_count"] == 1,
            "multi-layer/mip or 3D textures require a dedicated encoder")
    require(tex["dimension"] in (1, 2),
            "unsupported texture dimension (expect a 2D image)")
    require(tex["width"] * tex["height"] <= MAX_PIXELS,
            "RGBA8 decoded pixel budget exceeded")
    require(tex["tile_mode"] in (0, 1), "unknown hardware texture tiling")
    marker = blob[12:14]
    endian = "<" if marker == b"\xff\xfe" else ">" if marker == b"\xfe\xff" else None
    require(endian is not None, "invalid BNTX byte order")
    # The textureLayout (BlockHeightLog2) field is at BRTI +0x38.
    layout = struct.unpack_from(endian + "I", blob, tex["brti_offset"] + 0x38)[0]
    bh = layout & 7
    require(0 <= bh <= 5, "invalid Tegra block-height")
    if tex["tile_mode"] == 1:
        require(bh == 0, "pitch-linear texture cannot have tiled block height")
    starts = tex["mip_data_offsets"]
    require(isinstance(starts, list) and len(starts) == 1,
            "no verified single-mip data pointer")
    offset = starts[0]
    actual_size = surface_size(tex["width"], tex["height"], tex["tile_mode"], bh)
    require(tex["encoded_image_bytes"] >= actual_size, "encoded image smaller than expected surface")
    require(0 <= offset <= len(blob) and actual_size <= len(blob) - offset,
            "image pixel payload escapes BNTX")
    require(tex["encoded_image_bytes"] <= len(blob) - offset,
            "declared encoded image payload escapes BNTX")
    return {"texture": tex["name"], "width": tex["width"], "height": tex["height"],
            "tile_mode": tex["tile_mode"], "block_height_log2": bh,
            "data_offset": offset, "surface_bytes": actual_size,
            "declared_image_bytes": tex["encoded_image_bytes"],
            "original_bntx_sha256": hashlib.sha256(blob).hexdigest(),
            "source_kind": "original Nintendo Switch BNTX",
            "pixel_format": "RGBA8_UNORM", "mip_count": 1,
            "status": "qualified_container_layout_not_glyph_semantics"}


def decode_rgba(blob: bytes, name: str) -> Image.Image:
    desc = describe(blob, name)
    width, height = desc["width"], desc["height"]
    pixels = bytearray(width * height * 4)
    start, size = desc["data_offset"], desc["surface_bytes"]
    seen = set()
    for y in range(height):
        for x in range(width):
            pos = pixel_offset(x, y, width, height,
                               desc["tile_mode"], desc["block_height_log2"])
            require(pos + 4 <= size and pos not in seen,
                    "invalid or overlapping native tile address")
            seen.add(pos)
            i = (y * width + x) * 4
            pixels[i:i + 4] = blob[start + pos:start + pos + 4]
    return Image.frombytes("RGBA", (width, height), bytes(pixels))


def encode_rgba(original: bytes, name: str, image: Image.Image,
                expected_sha256: str) -> bytes:
    require(isinstance(expected_sha256, str) and
            hashlib.sha256(original).hexdigest() == expected_sha256.lower(),
            "original BNTX fingerprint mismatch")
    desc = describe(original, name)
    require(image.mode == "RGBA" and image.size == (desc["width"], desc["height"]),
            "replacement must be same-size RGBA pixels")
    # Copy the original complete BNTX, touching *only* the active
    # 4-byte pixel elements for the chosen named texture.
    pixels = image.tobytes()
    output = bytearray(original)
    width, height = image.size
    start, size = desc["data_offset"], desc["surface_bytes"]
    seen = set()
    for y in range(height):
        for x in range(width):
            pos = pixel_offset(x, y, width, height,
                               desc["tile_mode"], desc["block_height_log2"])
            require(pos + 4 <= size and pos not in seen,
                    "invalid overlapping/out-of-bounds pixel layout")
            seen.add(pos)
            i = (y * width + x) * 4
            output[start + pos:start + pos + 4] = pixels[i:i + 4]
    encoded = bytes(output)
    require(len(encoded) == len(original), "BNTX output changed file length")
    require(decode_rgba(encoded, name).tobytes() == pixels,
            "post-write image comparison failed")
    # Confirm BNTX texture metadata and all original image offsets persist.
    updated = describe(encoded, name)
    for key in ("width", "height", "tile_mode", "block_height_log2",
                "data_offset", "surface_bytes", "declared_image_bytes"):
        require(updated[key] == desc[key], "BNTX encoded resource layout changed")
    return encoded


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("inspect", "decode", "replace"))
    p.add_argument("--bntx", type=Path, required=True)
    p.add_argument("--texture", required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--edited-png", type=Path)
    p.add_argument("--sha256", help="required fingerprint of BNTX when replacing")
    args = p.parse_args()
    try:
        require(args.bntx.is_file() and not args.bntx.is_symlink() and
                args.bntx.stat().st_size <= MAX_BYTES, "invalid source BNTX")
        source = args.bntx.read_bytes()
        if args.action == "inspect":
            print(json.dumps(describe(source, args.texture), indent=2))
        else:
            require(args.out is not None and args.out.parent.is_dir() and
                    not args.out.parent.is_symlink() and
                    not args.out.exists() and not args.out.is_symlink(),
                    "output must be a new file in a real directory")
            if args.action == "decode":
                decoded = decode_rgba(source, args.texture)
                decoded.save(args.out, "PNG")
            else:
                require(args.edited_png is not None and args.sha256 is not None and
                        args.edited_png.is_file() and not args.edited_png.is_symlink() and
                        args.edited_png.stat().st_size <= MAX_BYTES,
                        "PNG replacement and source SHA-256 mandatory")
                with Image.open(args.edited_png) as img:
                    require(img.format == "PNG" and img.mode == "RGBA",
                            "edited graphic must be RGBA PNG")
                    updated = encode_rgba(source, args.texture, img,
                                          args.sha256)
                args.out.write_bytes(updated)
            print(f"BNTX RGBA8 {args.action.upper()} {args.out} "
                  "(file layout preserved, UI/game scene unverified)")
        return 0
    except (InvalidTexture, inspect.InvalidBntx, OSError, ValueError) as exc:
        print(f"REJECTED BNTX pixel operation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
