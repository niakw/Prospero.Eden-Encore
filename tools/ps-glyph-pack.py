#!/usr/bin/env python3
"""Validate and stage legally supplied PlayStation IN-GAME glyph resources.

This is a *game-resource* (RomFS) pack installer, NOT a controller remapper.
It uses the existing Eden mods/<title>/<mod>/romfs LayeredFS override path.
Only whole, authenticated source-file replacements are accepted. It cannot
magically turn all Nintendo prompts into PlayStation icons without a game's
specific legal replacement atlas and original resource fingerprint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath

MOD_NAME = "Eden Encore PS Glyphs"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_FILES = 64
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
HEX16 = re.compile(r"[0-9a-fA-F]{16}\Z")
UPDATE_VERSION = re.compile(r"[a-zA-Z0-9_.+ -]{1,64}\Z")
HEX_SHA = re.compile(r"[0-9a-fA-F]{64}\Z")


class InvalidPack(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidPack(message)


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _path(text: object) -> Path:
    require(isinstance(text, str) and bool(text) and len(text) <= 240,
            "resource path is missing or too long")
    require("\\" not in text and "\x00" not in text and ":" not in text and not text.startswith("/"),
            "absolute, Windows or special path refused")
    parts = PurePosixPath(text).parts
    require(bool(parts) and all(part not in ("", ".", "..") for part in parts),
            "path traversal refused")
    require("/".join(parts) == text, "resource path must be normalized")
    require(all(not part.startswith(".") for part in parts), "hidden path refused")
    return Path(*parts)


def _regular_file(root: Path, relative: Path) -> Path:
    require(root.is_dir() and not root.is_symlink(), "source root must be an ordinary folder")
    current = root
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), "symlinks in pack/source paths are forbidden")
    require(current.is_file(), f"missing source/replacement file: {relative.as_posix()}")
    require(current.stat().st_size <= MAX_FILE_BYTES, "glyph file exceeds 128 MiB")
    return current


def _digest(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as inp:
        for block in iter(lambda: inp.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _hex(value: object, pattern: re.Pattern, name: str) -> str:
    require(isinstance(value, str) and pattern.fullmatch(value) is not None, f"invalid {name}")
    return value.upper()


def verify(pack_root: Path, original_root: Path, title_id: str) -> dict:
    """Validate EVERY replacement against the matching original RomFS file.

    This installer checks original graphic bytes; the running emulator separately
    gates use by the declared title/update version. No NSO Build ID is needed.
    """
    title_id = _hex(title_id, HEX16, "title ID")
    manifest_file = _regular_file(pack_root, Path("manifest.json"))
    require(manifest_file.stat().st_size <= MAX_MANIFEST_BYTES, "manifest is too large")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"),
                              object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise InvalidPack("invalid manifest JSON") from error
    require(isinstance(manifest, dict) and set(manifest) ==
            {"schema", "title_id", "update_version", "rights", "files"},
            "manifest fields must match the exact v2 schema")
    require(type(manifest["schema"]) is int and manifest["schema"] == 2,
            "unknown glyph-pack schema")
    require(_hex(manifest["title_id"], HEX16, "manifest title ID") == title_id,
            "pack title ID does not match the selected game")
    require(isinstance(manifest["update_version"], str) and
            UPDATE_VERSION.fullmatch(manifest["update_version"]) is not None,
            "invalid pack update version")
    require(isinstance(manifest["rights"], str) and 4 <= len(manifest["rights"]) <= 240,
            "pack author must declare their rights to distribute replacement graphics")
    entries = manifest["files"]
    require(isinstance(entries, list) and 0 < len(entries) <= MAX_FILES,
            "pack must declare 1-64 replacement game resources")
    seen_game = set()
    seen_source = set()
    total_bytes = 0
    normalized = []
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) ==
                {"romfs_path", "replacement", "original_sha256", "replacement_sha256"},
                "invalid resource manifest entry")
        game_file = _path(entry["romfs_path"])
        replacement = _path(entry["replacement"])
        key = game_file.as_posix().casefold()
        source_key = replacement.as_posix().casefold()
        # A file cannot be a directory for another file, even if each
        # manifest entry has a legitimate digest. Keep installer and native
        # LayeredFS runtime in agreement across Linux/case-folding APFS.
        def conflicts(candidate: str, names: set[str]) -> bool:
            return any(candidate == old or candidate.startswith(old + "/") or
                       old.startswith(candidate + "/") for old in names)
        require(not conflicts(key, seen_game) and
                not conflicts(source_key, seen_source),
                "duplicate/case-colliding or parent-overlapping RomFS/replacement path")
        seen_game.add(key)
        seen_source.add(source_key)
        expected_original = _hex(entry["original_sha256"], HEX_SHA, "original SHA-256").lower()
        expected_replacement = _hex(entry["replacement_sha256"], HEX_SHA, "replacement SHA-256").lower()
        require(expected_original != expected_replacement,
                "replacement graphic bytes must differ from original")
        original = _regular_file(original_root, game_file)
        patch = _regular_file(pack_root, replacement)
        total_bytes += patch.stat().st_size
        require(total_bytes <= MAX_TOTAL_BYTES, "glyph pack exceeds 512 MiB")
        require(_digest(original) == expected_original,
                f"original RomFS file hash mismatch: {game_file.as_posix()}")
        require(_digest(patch) == expected_replacement,
                f"replacement graphic hash mismatch: {replacement.as_posix()}")
        normalized.append({"romfs_path": game_file.as_posix(),
                           "replacement": replacement.as_posix(),
                           "original_sha256": expected_original,
                           "replacement_sha256": expected_replacement})
    return {"schema": 2, "title_id": title_id,
            "update_version": manifest["update_version"],
            "rights": manifest["rights"], "files": normalized}


def install(pack_root: Path, original_root: Path, mods_root: Path,
            title_id: str) -> Path:
    manifest = verify(pack_root, original_root, title_id)
    require(not mods_root.is_symlink(), "mods folder must not be a symlink")
    require(mods_root.exists() and mods_root.is_dir(), "mods folder must already exist")
    # Eden's TitleFolder() intentionally finds title directories without
    # regard to hexadecimal case. Reuse the existing directory instead of
    # creating a second uppercase title folder that Eden might never read.
    matches = [p for p in mods_root.iterdir()
               if p.name.casefold() == manifest["title_id"].casefold()]
    require(len(matches) <= 1, "ambiguous case-colliding title mod folders")
    game_root = matches[0] if matches else mods_root / manifest["title_id"]
    require(not game_root.is_symlink(), "title mod folder must not be a symlink")
    require(not game_root.exists() or game_root.is_dir(),
            "title mod path is not a folder")
    game_root.mkdir(exist_ok=True)
    require(not any(p.name.casefold() == MOD_NAME.casefold()
                    for p in game_root.iterdir()),
            "glyph mod already exists; do not replace any existing pack")
    target = game_root / MOD_NAME
    require(not target.exists() and not target.is_symlink(),
            "glyph mod already exists; do not replace an existing pack automatically")
    stage = Path(tempfile.mkdtemp(prefix=".eden-ps-glyphs-", dir=game_root))
    try:
        for entry in manifest["files"]:
            source = _regular_file(pack_root, _path(entry["replacement"]))
            destination = stage / "romfs" / _path(entry["romfs_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            require(_digest(destination) == entry["replacement_sha256"],
                    "staged replacement failed SHA-256 verification")
        # Stored outside romfs/: evidence is not injected into game resources.
        (stage / "eden-glyph-pack.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")
        # A generated PS icon atlas contains CC BY 3.0 adapted art. Keep
        # attribution alongside the installed mod, OUTSIDE guest RomFS.
        # No implicit glob/copy of other untrusted files in the source pack.
        credit = pack_root / "ARTWORK_ATTRIBUTION.txt"
        if credit.exists() or credit.is_symlink():
            require(credit.is_file() and not credit.is_symlink() and
                    credit.stat().st_size <= 16 * 1024,
                    "unsafe or oversized artwork attribution")
            content = credit.read_text(encoding="utf-8")
            require("Zacksly" in content and "CC BY 3.0" in content,
                    "PlayStation source credit missing")
            (stage / "ARTWORK_ATTRIBUTION.txt").write_text(content, encoding="utf-8")
        require(not target.exists() and not target.is_symlink(),
                "another process installed a glyph pack")
        stage.rename(target)  # same filesystem; no partial mod directory on failure
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "install"))
    parser.add_argument("--pack", type=Path, required=True,
                        help="pack directory containing manifest.json and replacement artwork")
    parser.add_argument("--original-romfs", type=Path, required=True,
                        help="matching, legally obtained extracted original RomFS tree")
    parser.add_argument("--title-id", required=True, help="exact running game's 16-digit title ID")
    parser.add_argument("--mods-root", type=Path, help="existing game files/mods directory (install only)")
    args = parser.parse_args()
    try:
        if args.action == "install":
            require(args.mods_root is not None, "--mods-root required for install")
            result = install(args.pack, args.original_romfs, args.mods_root,
                             args.title_id)
            print(f"INSTALLED {result} (existing LayeredFS mod; runtime-gated by title/update version)")
        else:
            manifest = verify(args.pack, args.original_romfs, args.title_id)
            print(f"VERIFIED {manifest['title_id']} update={manifest['update_version']} files={len(manifest['files'])}")
        return 0
    except (InvalidPack, OSError) as error:
        print(f"REJECTED glyph pack: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
