#!/usr/bin/env python3
"""Qualified single-mip ASTC Switch BNTX texture editing, preserving outside blocks.

Works on original, authorized BNTX NX bytes via official ARM astcenc CLI
and Tegra block-linear/pitch-linear addressing. Source bytes, exact texture
name, SHA-256, update evidence and explicit glyph rectangles are required.
No full-image re-encode is ever injected into BNTX: ONLY compressed 128-bit
ASTC blocks intersecting approved rectangles are replaced. All other image
blocks, mips (only one supported), metadata and container bytes are untouched.

This is an offline *component*. No BOTW original assets or mod packs are
bundled; Nintendo ASTC source compatibility requires real Switch testing.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("eden_bntx_astc_swizzle", HERE / "ps-glyph-bntx-rgba.py")
if not sp or not sp.loader:
    raise SystemExit("requires ps-glyph-bntx-rgba.py")
tile = importlib.util.module_from_spec(sp)
sp.loader.exec_module(tile)

MAX_ENCODE_PIXELS = 4_194_304
MAX_ASTC_BINARY = 64 * 1024 * 1024
MAX_BLOCKS_CHANGED = 32768
ASTC_MAGIC = bytes.fromhex("13aba15c")


class UnsafeAstc(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise UnsafeAstc(reason)


def inspect_astc(blob: bytes, texture_name: str) -> dict:
    require(isinstance(blob, bytes) and 0x40 <= len(blob) <= MAX_ASTC_BINARY,
            "BNTX too large or missing")
    resources = tile.inspect.inspect(blob)["textures"]
    found = [x for x in resources if x["name"].casefold() == texture_name.casefold()]
    require(len(found) == 1, "ambiguous/missing named ASTC texture")
    info = found[0]
    code = int(info["format_code"], 16)
    fmt, colorspace = (code >> 8) & 0xff, code & 0xff
    require(fmt in tile.inspect.ASTC_DIMENSIONS and colorspace in (1, 6),
            "not an LDR ASTC UNORM or SRGB block format")
    require(info["depth"] == info["array_length"] == info["mip_count"] == 1 and
            info["dimension"] == 1,
            "3D/array/mipmapped ASTC image is unqualified")
    width, height = info["width"], info["height"]
    require(width > 0 and height > 0 and width * height <= MAX_ENCODE_PIXELS,
            "ASTC texture exceeds bounded UI editing budget")
    block_w, block_h = tile.inspect.ASTC_DIMENSIONS[fmt]
    w_blocks, h_blocks = math.ceil(width / block_w), math.ceil(height / block_h)
    require(info["tile_mode"] in (0, 1) and
            len(info["mip_data_offsets"] or []) == 1,
            "unsupported tiled layout or absent mip data offset")
    offset = info["mip_data_offsets"][0]
    order = "<" if blob[12:14] == b"\xff\xfe" else ">" if blob[12:14] == b"\xfe\xff" else None
    require(order is not None, "invalid BNTX byte order")
    import struct
    layout = struct.unpack_from(order + "I", blob, info["brti_offset"] + 0x38)[0]
    bh = layout & 7
    require(0 <= bh <= 5 and (info["tile_mode"] == 0 or bh == 0),
            "invalid ASTC block-linear height exponent")
    byte_count = tile.surface_size(w_blocks, h_blocks, info["tile_mode"], bh, 16)
    require(byte_count <= info["encoded_image_bytes"] and
            0 <= offset <= len(blob) and info["encoded_image_bytes"] <= len(blob) - offset,
            "ASTC encoded image span unbounded")
    return {"name": info["name"], "format_code": info["format_code"],
            "colorspace": "srgb" if colorspace == 6 else "linear",
            "width": width, "height": height, "block_width": block_w,
            "block_height": block_h, "width_blocks": w_blocks,
            "height_blocks": h_blocks, "block_height_log2": bh,
            "tile_mode": info["tile_mode"], "data_offset": offset,
            "surface_bytes": byte_count, "original_sha256": hashlib.sha256(blob).hexdigest()}


def astc_header(d: dict) -> bytes:
    return (ASTC_MAGIC + bytes((d["block_width"], d["block_height"], 1)) +
            d["width"].to_bytes(3, "little") +
            d["height"].to_bytes(3, "little") +
            b"\x01\x00\x00")


def get_blocks(blob: bytes, d: dict) -> bytes:
    linear = bytearray(d["width_blocks"] * d["height_blocks"] * 16)
    used = set()
    for y in range(d["height_blocks"]):
        for x in range(d["width_blocks"]):
            addr = tile.pixel_offset(x, y, d["width_blocks"], d["height_blocks"],
                                     d["tile_mode"], d["block_height_log2"], 16)
            require(addr + 16 <= d["surface_bytes"] and addr not in used,
                    "overlapping or invalid native ASTC compressed block address")
            used.add(addr)
            off = d["data_offset"] + addr
            linear[(y * d["width_blocks"] + x) * 16:
                   (y * d["width_blocks"] + x + 1) * 16] = blob[off:off + 16]
    return bytes(linear)


def run_astcenc(codec: str, args: list[str]) -> None:
    binary = shutil.which(codec)
    require(binary is not None, "ARM astcenc executable not found (install astcenc)")
    cmd = [binary, *args]
    try:
        result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnsafeAstc("astcenc missing or timed out") from exc
    require(result.returncode == 0, "astcenc rejected image: " +
            result.stderr.decode("utf-8", "replace")[-300:])


def decoded_image(blob: bytes, name: str, astcenc: str = "astcenc") -> Image.Image:
    d = inspect_astc(blob, name)
    with tempfile.TemporaryDirectory(prefix="eden-astc-ui-") as root:
        src = Path(root) / "original.astc"
        out = Path(root) / "decoded.png"
        src.write_bytes(astc_header(d) + get_blocks(blob, d))
        run_astcenc(astcenc, ["-ds" if d["colorspace"] == "srgb" else "-dl",
                              str(src), str(out)])
        require(out.is_file() and out.stat().st_size < 64 * 1024 * 1024,
                "unexpected ASTC decoded output")
        with Image.open(out) as result:
            require(result.size == (d["width"], d["height"]),
                    "ASTC decoder dimensions differ from source BNTX")
            return result.convert("RGBA")


def verify_rects(rectangles: list, width: int, height: int) -> list[tuple[int,int,int,int]]:
    require(isinstance(rectangles, list) and 0 < len(rectangles) <= 256,
            "must explicitly select 1-256 verified glyph slots")
    valid = []
    for item in rectangles:
        require(isinstance(item, list) and len(item) == 4 and
                all(type(v) is int for v in item), "slot rectangle must be integer XYWH")
        x, y, w, h = item
        require(x >= 0 and y >= 0 and w > 0 and h > 0 and
                x + w <= width and y + h <= height,
                "sprite slot outside decoded Switch texture")
        require(not any(x < ax + aw and ax < x + w and y < ay + ah and ay < y + h
                        for ax, ay, aw, ah in valid),
                "overlapping glyph slots")
        valid.append(tuple(item))
    return valid


def patch_astc(original: bytes, texture_name: str, edited: Image.Image,
               rectangles: list, original_sha256: str,
               astcenc: str = "astcenc") -> tuple[bytes, dict]:
    require(hashlib.sha256(original).hexdigest() == original_sha256.lower(),
            "original Switch BNTX SHA mismatch")
    desc = inspect_astc(original, texture_name)
    require(edited.mode == "RGBA" and
            edited.size == (desc["width"], desc["height"]),
            "replacement needs same-size decoded RGBA")
    rects = verify_rects(rectangles, *edited.size)
    original_image = decoded_image(original, texture_name, astcenc)
    # All edited pixels must be within approved rectangles; this catches
    # accidentally imported entire third-party mod backgrounds.
    diffs = ImageChops.difference(original_image, edited).convert("RGBA")
    mask = diffs.split()
    changed = ImageChops.lighter(ImageChops.lighter(mask[0], mask[1]),
                                 ImageChops.lighter(mask[2], mask[3])).point(
        lambda val: 255 if val else 0)
    if not changed.getbbox():
        return original, {"changed_blocks": 0, "untouched_encoded_blocks_preserved": True}
    for y in range(desc["height"]):
        for x in range(desc["width"]):
            if changed.getpixel((x, y)):
                require(any(rx <= x < rx + rw and ry <= y < ry + rh
                            for rx, ry, rw, rh in rects),
                        "edited pixels outside verified glyph rectangles")
    affected = set()
    for x, y, w, h in rects:
        for yy in range(y // desc["block_height"],
                        (y + h - 1) // desc["block_height"] + 1):
            for xx in range(x // desc["block_width"],
                            (x + w - 1) // desc["block_width"] + 1):
                affected.add((xx, yy))
    require(len(affected) <= MAX_BLOCKS_CHANGED,
            "too many compressed blocks modified")
    # Preserve untouched visual content at boundaries of compressed ASTC
    # blocks: if any non-transparent game-owned content falls outside the
    # approved rectangle yet shares a compressed block, do NOT re-encode it.
    alpha = original_image.getchannel("A")
    for bx, by in affected:
        for yy in range(by * desc["block_height"],
                        min((by + 1) * desc["block_height"], desc["height"])):
            for xx in range(bx * desc["block_width"],
                            min((bx + 1) * desc["block_width"], desc["width"])):
                if not any(rx <= xx < rx + rw and ry <= yy < ry + rh
                           for rx, ry, rw, rh in rects):
                    require(alpha.getpixel((xx, yy)) == 0,
                            "ASTC block crosses unrelated nontransparent UI art")
    with tempfile.TemporaryDirectory(prefix="eden-astc-glyph-") as root:
        inp = Path(root) / "edited.png"
        encoded = Path(root) / "edited.astc"
        edited.save(inp, "PNG")
        run_astcenc(astcenc, ["-cs" if desc["colorspace"] == "srgb" else "-cl",
                              str(inp), str(encoded),
                              f"{desc['block_width']}x{desc['block_height']}",
                              "-thorough"])
        data = encoded.read_bytes()
    require(data[:16] == astc_header(desc) and
            len(data) == 16 + desc["width_blocks"] * desc["height_blocks"] * 16,
            "encoder did not preserve ASTC format, block size or pixel dimensions")
    out = bytearray(original)
    source_linear = get_blocks(original, desc)
    for bx, by in affected:
        index = by * desc["width_blocks"] + bx
        old = source_linear[16 * index:16 * index + 16]
        new = data[16 + 16 * index:16 + 16 * index + 16]
        if old == new:
            continue
        addr = tile.pixel_offset(bx, by, desc["width_blocks"],
                                 desc["height_blocks"], desc["tile_mode"],
                                 desc["block_height_log2"], 16)
        start = desc["data_offset"] + addr
        out[start:start + 16] = new
    result = bytes(out)
    require(len(result) == len(original), "ASTC BNTX file size was changed")
    # Untouched compressed bytes must remain exactly equal; no hidden
    # conversions of unrelated Switch game UI tiles are permitted.
    candidate = get_blocks(result, desc)
    untouched = 0
    for idx in range(desc["width_blocks"] * desc["height_blocks"]):
        if (idx % desc["width_blocks"], idx // desc["width_blocks"]) not in affected:
            require(candidate[16 * idx:16 * idx + 16] ==
                    source_linear[16 * idx:16 * idx + 16],
                    "untouched ASTC block changed unexpectedly")
            untouched += 1
    require(inspect_astc(result, texture_name)["width"] == desc["width"],
            "ASTC metadata changed")
    return result, {
        "original_bntx_sha256": original_sha256.lower(),
        "patched_bntx_sha256": hashlib.sha256(result).hexdigest(),
        "reencoded_astc_blocks": len(affected),
        "untouched_encoded_blocks_preserved": True,
        "untouched_astc_block_count": untouched,
        "format": desc["format_code"],
        "requires_real_game_scene_qualification": True,
    }
