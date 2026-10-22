#!/usr/bin/env python3
"""Byte-offset diagnostic for nonidentical release images (does not waive failure)."""
import argparse
import pathlib

CHUNK_BYTES = 1024 * 1024
MAX_DIFFERENCES = 8

def scan_bytes(first: pathlib.Path, second: pathlib.Path) -> tuple[int | None, list[tuple[int, int | None, int | None]]]:
    """Find first differences with bounded memory, including unequal lengths."""
    differences = []
    offset = 0
    with first.open("rb") as left, second.open("rb") as right:
        while True:
            a = left.read(CHUNK_BYTES)
            b = right.read(CHUNK_BYTES)
            if not a and not b:
                break
            if a != b:
                for index in range(max(len(a), len(b))):
                    av = a[index] if index < len(a) else None
                    bv = b[index] if index < len(b) else None
                    if av != bv:
                        differences.append((offset + index, av, bv))
                        if len(differences) >= MAX_DIFFERENCES:
                            break
                if len(differences) >= MAX_DIFFERENCES:
                    break
            offset += max(len(a), len(b))
    if not differences:
        return None, differences
    return differences[0][0], differences

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=pathlib.Path)
    parser.add_argument("second", type=pathlib.Path)
    args = parser.parse_args()
    first, second = args.first, args.second
    if not first.is_file() or not second.is_file():
        parser.error("two existing image files are required")
    offset, differences = scan_bytes(first, second)
    print(f"FFPFSC_IMAGE_REPRO_DIFF first_size={first.stat().st_size} "
          f"second_size={second.stat().st_size} first_different_offset={offset}")
    if offset is not None:
        for at, before, after in differences:
            print(f"FFPFSC_IMAGE_REPRO_BYTE offset=0x{at:x} "
                  f"a={'EOF' if before is None else f'{before:02x}'} "
                  f"b={'EOF' if after is None else f'{after:02x}'}")
    return 0 if offset is None else 1

if __name__ == "__main__":
    raise SystemExit(main())
