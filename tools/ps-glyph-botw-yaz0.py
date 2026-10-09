#!/usr/bin/env python3
"""Read-only BOTW Switch UI archive inspection: Yaz0 -> SARC -> optional BNTX.

The original .sblarc/.ssarc/.sarc file is never modified or extracted.
Yaz0 is a lossless container compressor (not pixel compression). Decoding it
allows inspecting exact internal Nintendo resource names/byte offsets without
claiming reconstructed PlayStation icons or sprite XYWH coordinates.
The decoder handles literal and backreference tokens with strict output caps.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_INPUT = 128 * 1024 * 1024
MAX_DECOMPRESSED = 128 * 1024 * 1024


class InvalidYaz0(ValueError):
    pass


def expect(condition: bool, why: str) -> None:
    if not condition:
        raise InvalidYaz0(why)


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    if spec is None or spec.loader is None:
        raise InvalidYaz0("missing inspector " + file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sarc = load("eden_botw_sarc", "ps-glyph-sarc-inspect.py")
chain = load("eden_botw_bntx_chain", "ps-glyph-sarc-bntx-chain.py")


def decode(data: bytes) -> bytes:
    expect(isinstance(data, bytes) and 16 <= len(data) <= MAX_INPUT,
           "Yaz0 input too short or oversized")
    expect(data[:4] == b"Yaz0", "not Yaz0 (uncompressed SARCs are supported separately)")
    declared = int.from_bytes(data[4:8], "big")
    expect(0x20 <= declared <= MAX_DECOMPRESSED,
           "declared decompressed bytes exceed bounded SARC budget")
    # Nintendo Yaz0 stores 8 reserved zero bytes after the decoded length.
    expect(data[8:16] == bytes(8), "unexpected Yaz0 reserved header bytes")
    position = 16
    output = bytearray()
    while len(output) < declared:
        expect(position < len(data), "truncated Yaz0 control sequence")
        control = data[position]
        position += 1
        for bit in range(7, -1, -1):
            if len(output) == declared:
                break
            if control & (1 << bit):
                expect(position < len(data), "truncated Yaz0 literal")
                output.append(data[position])
                position += 1
            else:
                expect(position + 1 < len(data), "truncated Yaz0 copy descriptor")
                first, second = data[position], data[position + 1]
                position += 2
                distance = (((first & 15) << 8) | second) + 1
                length = first >> 4
                if length == 0:
                    expect(position < len(data), "truncated Yaz0 long-copy length")
                    length = data[position] + 0x12
                    position += 1
                else:
                    length += 2
                expect(distance <= len(output), "Yaz0 backreference before output start")
                expect(length <= declared - len(output),
                       "Yaz0 backreference exceeds exact declared output")
                # A backreference that overlaps itself is a periodic repetition
                # of the already decoded distance-byte suffix.
                pattern = bytes(output[-distance:])
                output.extend((pattern * ((length + distance - 1) // distance))[:length])
    # Game containers may be 4/16-byte aligned with trailing zero padding.
    expect(not any(data[position:]), "nonpadding data after completed Yaz0 stream")
    return bytes(output)


def inventory(source: Path, nested: bool = True) -> dict:
    expect(source.is_file() and not source.is_symlink(), "archive missing or symlink")
    length = source.stat().st_size
    expect(0x20 <= length <= MAX_INPUT, "source archive size outside input budget")
    raw = source.read_bytes()
    expect(len(raw) == length, "incomplete original archive read")
    if raw.startswith(b"Yaz0"):
        decompressed = decode(raw)
        compression = "Yaz0"
    else:
        expect(raw.startswith(b"SARC"), "not a Yaz0/SARC UI container")
        decompressed = raw
        compression = "uncompressed"
    info = sarc.inventory_bytes(decompressed)
    results = {
        "schema": 1,
        "source_name": source.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "compression": compression,
        "decompressed_sha256": hashlib.sha256(decompressed).hexdigest(),
        "decompressed_bytes": len(decompressed),
        "sarc": info,
        "ps5_art_qualified": False,
        "sprite_pixel_rectangles": None,
        "warning": ("Container and member offsets are file BYTES, not image pixels. "
                    "BNTX may require deswizzle/ASTC decode before sprite inspection."),
    }
    if nested:
        results["bntx_chain"] = chain.inspect_chain_bytes(decompressed)
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--out", type=Path, help="NEW JSON inventory only")
    p.add_argument("--skip-bntx", action="store_true")
    a = p.parse_args()
    try:
        if a.out and (a.out.exists() or a.out.is_symlink() or
                      not a.out.parent.is_dir() or a.out.parent.is_symlink()):
            raise InvalidYaz0("report output already exists or parent is unsafe")
        data = json.dumps(inventory(a.archive, not a.skip_bntx),
                          ensure_ascii=False, indent=2) + "\n"
        if a.out:
            a.out.write_text(data, encoding="utf-8")
            print(f"BOTW YAZ0/SARC UI INVENTORY {a.out} (read-only)")
        else:
            print(data, end="")
        return 0
    except (InvalidYaz0, OSError, ValueError,
            sarc.InvalidSarc, chain.bntx.InvalidBntx) as e:
        print(f"REJECTED BOTW ARCHIVE: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
