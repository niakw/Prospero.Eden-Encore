#!/usr/bin/env python3
"""Read-only, fail-closed ZIP inventory for Switch game UI prompt mods.

This DOES NOT extract, install, execute or convert mod files. It records
relative paths, member size, compressed size and ZIP CRC for authorized local
ZIP archives. Pixel coordinates require actual texture decoding and a
verified exact-version original-game baseline, not filename heuristics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_MEMBERS = 16384
MAX_MEMBER_SIZE = 256 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
SUSPICIOUS = ("btn", "button", "controller", "input", "prompt", "glyph",
              "layout", "hud", "icon", "ui", "font", "common", "tutorial")


def format_family_hint(name: str) -> str:
    """Path/extension heuristic ONLY; never a decoded asset or compatibility proof."""
    lower = name.casefold()
    ext = Path(lower).suffix
    if lower.endswith((".blarc.zs", ".sarc.zs", ".sarc", ".blarc")):
        return "nintendo_sarc_or_compressed_sarc_candidate"
    if ext in (".bntx", ".bfres", ".bflyt", ".bflan", ".bftex"):
        return "nintendo_resource_candidate"
    if lower.endswith("/data/resources.assets") or ext in (".assets", ".unity3d", ".bundle"):
        return "unity_asset_candidate"
    if "/images/" in "/" + lower and ext == ".xml":
        return "klei_or_other_xml_atlas_candidate"
    if "/images/" in "/" + lower and ext == ".tex":
        return "klei_or_other_tex_texture_candidate"
    if ext == ".cpk":
        return "criware_cpk_candidate"
    if ext in (".spr", ".spd"):
        return "atlus_sprite_archive_candidate"
    if ext == ".pak":
        if "/content/paks/" in lower or lower.endswith("_p.pak"):
            return "unreal_pak_candidate"
        return "pak_format_ambiguous"
    if ext in (".uasset", ".uexp", ".ubulk", ".utoc", ".ucas"):
        return "unreal_package_candidate"
    if ext in (".png", ".tga"):
        return "decoded_image_candidate"
    if ext == ".bnp":
        return "bcml_patch_bundle_candidate"
    if ext in (".7z", ".rar"):
        return "nested_archive_unexamined"
    return "unknown_format"


def check_member(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not name or len(name) > 512 or "\x00" in name or "\\" in name or ":" in name or name.startswith("/"):
        raise ValueError("unsafe ZIP member name")
    if info.flag_bits & 1:
        raise ValueError("encrypted ZIP member")
    path = PurePosixPath(name.rstrip("/"))
    if not path.parts or any(p in ("", ".", "..") or p.startswith(".") for p in name.rstrip("/").split("/")):
        raise ValueError("unsafe ZIP path segments")
    if "/".join(path.parts) != name.rstrip("/"):
        raise ValueError("noncanonical ZIP path")
    # Unix symlinks/devices: prohibit entirely, even though we never extract.
    mode = (info.external_attr >> 16) & 0o170000
    if mode and mode not in (0o100000, 0o040000):
        raise ValueError("unsupported ZIP member type")
    if info.file_size > MAX_MEMBER_SIZE or info.file_size < 0 or info.compress_size < 0:
        raise ValueError("oversized ZIP member")
    return str(path)


def inventory(archive: Path) -> dict:
    if not archive.is_file() or archive.is_symlink() or archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError("archive missing, symlink or oversized")
    h = hashlib.sha256()
    with archive.open("rb") as inp:
        for chunk in iter(lambda: inp.read(1024 * 1024), b""):
            h.update(chunk)
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("excess member count")
        found = []
        seen = set()
        total = 0
        for info in infos:
            name = check_member(info)
            key = name.casefold()
            if key in seen:
                raise ValueError("case-colliding/duplicate ZIP members")
            seen.add(key)
            if info.is_dir():
                continue
            total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED:
                raise ValueError("excess total uncompressed member size")
            chunks = PurePosixPath(name).parts
            romfs_index = next((i for i, part in enumerate(chunks) if part.lower() == "romfs"), None)
            rel = "/".join(chunks[romfs_index + 1:]) if romfs_index is not None else None
            hint = any(term in name.lower() for term in SUSPICIOUS)
            found.append({"archive_path": name, "romfs_path": rel or None,
                          "container_format_hint": format_family_hint(name),
                          "hint_is_binary_verified": False,
                          "extension": Path(name).suffix.lower(),
                          "uncompressed_bytes": info.file_size,
                          "compressed_bytes": info.compress_size,
                          "zip_crc32": f"{info.CRC:08x}",
                          "ui_candidate": hint})
    return {"archive": archive.name, "archive_sha256": h.hexdigest(),
            "file_count": len(found), "files": found,
            "pixel_coordinates": None, "button_semantics": None,
            "warning": "ZIP metadata only. No files extracted, hashes of individual decoded files, original-versus-mod diffs or tested runtime compatibility."}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archives", nargs="+", type=Path, help="local, authorized ZIP files")
    p.add_argument("--out", type=Path, help="new JSON report path, never overwrite")
    p.add_argument("--platform", default="unverified", help="declared source platform label; not auto-detected")
    p.add_argument("--expect-sha256", help="optional published release SHA-256, single archive only")
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("invalid report destination")
        if not args.platform or len(args.platform) > 80 or any(c in args.platform for c in "\r\n\x00"):
            raise ValueError("invalid platform label")
        data = {"schema": 1, "declared_source_platform": args.platform,
                "mods": [inventory(path) for path in args.archives]}
        if args.expect_sha256 is not None:
            expected = args.expect_sha256.lower()
            if len(args.archives) != 1 or len(expected) != 64 or any(
                    digit not in "0123456789abcdef" for digit in expected):
                raise ValueError("expected SHA-256 requires one archive and 64 hexadecimal digits")
            if data["mods"][0]["archive_sha256"] != expected:
                raise ValueError("mod archive differs from published release SHA-256")
        result = json.dumps(data, ensure_ascii=True, indent=2) + "\n"
        if args.out:
            args.out.write_text(result, encoding="utf-8")
            print(f"ZIP INVENTORY {args.out}: {len(data['mods'])} archives, no extraction")
        else:
            print(result, end="")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"REJECTED mod inventory: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
