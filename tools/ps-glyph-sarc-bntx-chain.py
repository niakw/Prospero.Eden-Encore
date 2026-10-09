#!/usr/bin/env python3
"""Traverse decompressed Nintendo SARC -> embedded BNTX -> named BRTI textures.

READ-ONLY and bounded. Produces exact absolute BYTE offsets within the
decompressed SARC and relative BNTX, plus texture names, formats, dimensions,
mip byte pointers. Does not decode image pixels, decompress .zs or edit assets.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_NESTED = 32
MAX_MEMBER_BYTES = 64 * 1024 * 1024


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ValueError(f"missing read-only parser: {filename}")
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


sarc = load_module("eden_glyph_sarc", "ps-glyph-sarc-inspect.py")
bntx = load_module("eden_glyph_bntx", "ps-glyph-bntx-inspect.py")


def inspect_chain_bytes(raw: bytes) -> dict:
    outer = sarc.inventory_bytes(raw)
    # SARC inspector bounds-checks all table/member pointers; no member is
    # written or loaded into guest memory. Input may come from Yaz0 decode.
    found = []
    bntx_count = 0
    for member in outer["members"]:
        name = member["name"]
        if not name or not name.lower().endswith(".bntx"):
            continue
        offset = member["content_offset"]
        length = member["content_bytes"]
        info = {"sarc_member": name, "sarc_byte_offset": offset,
                "sarc_member_bytes": length, "textures": []}
        if length < 0x40 or length > MAX_MEMBER_BYTES or bntx_count >= MAX_NESTED:
            info["status"] = "bounded_skip"
            found.append(info)
            continue
        bntx_count += 1
        try:
            internal = bntx.inspect(raw[offset:offset + length])
            for texture in internal["textures"]:
                t = dict(texture)
                t["sarc_brti_byte_offset"] = offset + texture["brti_offset"]
                t["sarc_mip_data_byte_offsets"] = (
                    [offset + level for level in texture["mip_data_offsets"]]
                    if texture["mip_data_offsets"] is not None else None)
                info["textures"].append(t)
            info["status"] = "byte_offsets_inspected_only"
        except (bntx.InvalidBntx, OSError, ValueError) as error:
            info["status"] = "nested_bntx_unreadable"
            info["reason"] = str(error)[:200]
        found.append(info)
    return {
        "schema": 1,
        "source": "decompressed_SARC_containing_BNTX",
        "sarc_sha256": outer["archive_sha256"],
        "sarc_member_count": outer["member_count"],
        "embedded_bntx_candidates": found,
        "image_pixel_coordinates": None,
        "button_semantics": None,
        "ps5_runtime_test": None,
        "warning": "SARC/BRTI/mip offsets are bytes in a decompressed container, NOT on-screen glyph pixel positions.",
    }


def inspect_chain(source: Path) -> dict:
    # Preserve strict original on-disk file checks for the standalone CLI.
    sarc.inventory(source)
    return inspect_chain_bytes(source.read_bytes())



def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("sarc_file", type=Path, help="locally authorized, already decompressed SARC/BLARC")
    p.add_argument("--out", type=Path, help="new JSON report file")
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("unsafe output destination")
        result = json.dumps(inspect_chain(args.sarc_file), indent=2) + "\n"
        if args.out:
            args.out.write_text(result, encoding="utf-8")
            print(f"SARC BNTX CHAIN {args.out} (read-only)")
        else:
            print(result, end="")
        return 0
    except (OSError, ValueError, sarc.InvalidSarc) as error:
        print(f"REJECTED SARC BNTX chain: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
