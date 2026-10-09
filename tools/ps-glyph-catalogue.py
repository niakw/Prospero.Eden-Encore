#!/usr/bin/env python3
"""Merge verified local PlayStation in-game glyph packs into Eden's catalogue.

The emulator loads <ConfigFile>/encore-glyph-overrides.json only when its
revision is greater than the built-in revision (currently 2). Never silently
overwrite the user's catalogue or drop previously installed game versions.
This tool does not validate installed RomFS bytes; ps-glyph-pack.py does.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

TITLE = re.compile(r"[0-9a-fA-F]{16}\Z")
VERSION = re.compile(r"[a-zA-Z0-9_.+ -]{1,64}\Z")
MAX = 128 * 1024
MAX_RULES = 256


class InvalidCatalogue(ValueError):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise InvalidCatalogue(reason)


def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, val in pairs:
        require(key not in obj, f"duplicate JSON key: {key}")
        obj[key] = val
    return obj


def read_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX,
            f"invalid/oversized input: {path}")
    data = json.loads(path.read_text("utf-8"), object_pairs_hook=no_duplicates)
    require(isinstance(data, dict), f"JSON must be object: {path}")
    return data


def rule(title: object, version: object) -> tuple[str, str]:
    require(isinstance(title, str) and TITLE.fullmatch(title) is not None and
            int(title, 16) != 0, "invalid game title ID")
    require(isinstance(version, str) and VERSION.fullmatch(version) is not None,
            "invalid update version")
    return title.upper(), version


def check_replacement_files(folder: Path, entries: list) -> None:
    require(0 < len(entries) <= 64, "invalid glyph pack file list")
    seen = set()
    total = 0
    for item in entries:
        require(isinstance(item, dict) and set(item) ==
                {"romfs_path", "replacement", "original_sha256", "replacement_sha256"},
                "invalid glyph pack replacement entry")
        for key in ("original_sha256", "replacement_sha256"):
            value = item[key]
            require(isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value),
                    f"invalid {key}")
        original = item["romfs_path"]
        require(isinstance(original, str) and 0 < len(original) <= 240 and
                "\\" not in original and ":" not in original and
                not original.startswith("/"), "unsafe original RomFS path")
        original_parts = original.split("/")
        require(all(part and part not in (".", "..") and not part.startswith(".")
                    for part in original_parts), "invalid original RomFS components")
        name = item["replacement"]
        require(isinstance(name, str) and 0 < len(name) <= 240 and
                "\\" not in name and ":" not in name and not name.startswith("/"),
                "unsafe replacement resource path")
        parts = name.split("/")
        require(all(part and part not in (".", "..") and not part.startswith(".")
                    for part in parts), "invalid replacement components")
        key = name.casefold()
        require(key not in seen, "duplicate replacement asset path")
        seen.add(key)
        file = folder
        for part in parts:
            file = file / part
            require(not file.is_symlink(), "replacement symlink forbidden")
        require(file.is_file() and file.stat().st_size <= 128 * 1024 * 1024,
                f"replacement resource missing/too large: {name}")
        total += file.stat().st_size
        require(total <= 512 * 1024 * 1024, "glyph pack exceeds total size cap")
        digest = hashlib.sha256()
        with file.open("rb") as inp:
            for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                digest.update(chunk)
        require(digest.hexdigest() == item["replacement_sha256"].lower(),
                f"modified replacement graphic: {name}")


def build(packs: list[Path], existing: Path | None = None,
          minimum_revision: int = 2) -> dict:
    require(0 <= minimum_revision < 2**31-2, "invalid embedded revision floor")
    versions: set[tuple[str, str]] = set()
    revision = minimum_revision
    if existing is not None:
        old = read_json(existing)
        require(set(old) == {"schema_version", "revision", "titles"} and
                type(old["schema_version"]) is int and old["schema_version"] == 2 and
                type(old["revision"]) is int and 0 <= old["revision"] < 2**31-2 and
                isinstance(old["titles"], list) and len(old["titles"]) <= MAX_RULES,
                "incompatible existing glyph catalogue")
        revision = max(revision, old["revision"])
        for item in old["titles"]:
            require(isinstance(item, dict) and set(item) == {"title_id", "update_version"},
                    "invalid existing title rule")
            r = rule(item["title_id"], item["update_version"])
            require(r not in versions, "existing duplicate title/update version")
            versions.add(r)
    require(bool(packs), "at least one verified glyph pack required")
    for p in packs:
        directory = p
        require(directory.is_dir() and not directory.is_symlink(),
                "pack path must be an ordinary directory")
        manifest = read_json(directory / "manifest.json")
        require(set(manifest) == {"schema", "title_id", "update_version", "rights", "files"} and
                type(manifest["schema"]) is int and manifest["schema"] == 2 and
                isinstance(manifest["rights"], str) and len(manifest["rights"]) >= 4 and
                isinstance(manifest["files"], list) and bool(manifest["files"]),
                "invalid/empty glyph pack manifest")
        check_replacement_files(directory, manifest["files"])
        r = rule(manifest["title_id"], manifest["update_version"])
        require(r not in versions, f"catalogue already has game/version {r}")
        versions.add(r)
        require(len(versions) <= MAX_RULES, "maximum 256 game/version rules")
    return {
        "schema_version": 2,
        "revision": revision + 1,
        "titles": [
            {"title_id": title, "update_version": ver}
            for title, ver in sorted(versions)
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", type=Path, required=True, action="append",
                   help="verified pack directory; repeat for several titles")
    p.add_argument("--existing", type=Path, help="current config catalogue to preserve")
    p.add_argument("--out", type=Path, required=True, help="NEW file to copy to console")
    p.add_argument("--minimum-revision", type=int, default=2,
                   help="revision embedded in emulator source; default 2")
    args = p.parse_args()
    try:
        require(not args.out.exists() and not args.out.is_symlink() and
                args.out.parent.is_dir() and not args.out.parent.is_symlink(),
                "output already exists or parent invalid")
        data = build(args.pack, args.existing, args.minimum_revision)
        serial = json.dumps(data, ensure_ascii=True, indent=2) + "\n"
        require(len(serial.encode("utf-8")) <= MAX, "catalogue exceeds native limit")
        args.out.write_text(serial, "utf-8")
        print(f"CATALOGUE {args.out}: revision={data['revision']} rules={len(data['titles'])}")
        print("Copy to Eden ConfigFile/encore-glyph-overrides.json; only installed, verified packs activate")
        return 0
    except (InvalidCatalogue, OSError, ValueError) as e:
        print(f"REJECTED catalogue update: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
