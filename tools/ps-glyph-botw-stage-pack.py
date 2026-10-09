#!/usr/bin/env python3
"""Stage a checksum-bound, LOCAL-ONLY BOTW PlayStation UI LayeredFS candidate.

Pairs one separately generated BOTW Yaz0/SARC replacement with its exact
original same-path RomFS resource and non-installation evidence receipt.
Refuses unexpected changes and does not install or enable the glyphs.
Output is compatible with ps-glyph-pack.py verify/install after later
per-title version and hardware UI qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class InvalidStage(ValueError):
    pass


def require(value: bool, reason: str):
    if not value:
        raise InvalidStage(reason)


def loader(name: str, path: str):
    s = importlib.util.spec_from_file_location(name, ROOT / path)
    require(s is not None and s.loader is not None, "missing companion pack tool")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


pack = loader("eden_botw_stage_pack", "ps-glyph-pack.py")
sarc = loader("eden_botw_stage_sarc", "ps-glyph-botw-archive-diff.py")
MAX_BYTES = 128 * 1024 * 1024


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stage(original_romfs: Path, patched_archive: Path, receipt: dict,
          romfs_relative_path: str, title_id: str, update_version: str,
          destination: Path) -> Path:
    relative = pack._path(romfs_relative_path)
    require(relative.suffix.lower() in (".sblarc", ".ssarc", ".sarc", ".blarc"),
            "requires a BOTW native UI SARC/Yaz0 game resource")
    original = pack._regular_file(original_romfs, relative)
    require(patched_archive.is_file() and not patched_archive.is_symlink() and
            0x20 <= patched_archive.stat().st_size <= MAX_BYTES,
            "patch missing or oversized")
    require(isinstance(receipt, dict) and
            receipt.get("original_archive_sha256") == sha(original) and
            receipt.get("updated_archive_sha256") == sha(patched_archive) and
            receipt.get("other_member_and_layout_bytes_preserved") is True and
            receipt.get("bntx_astc", {}).get("untouched_encoded_blocks_preserved") is True,
            "patch lacks correct original and untouched member/block proof")
    require(receipt.get("title_id") == title_id.upper() and
            receipt.get("user_declared_update_version") == update_version and
            receipt.get("scene_verified_on_ps5") is False,
            "wrong source game, update or incorrect runtime qualification")
    require(receipt.get("approved_slots_count", 0) >= 1 and
            receipt.get("glyph_profile") == "playstation",
            "no verified fixed PlayStation input artwork edits")
    # Validate that both archive versions are parseable and named members
    # differ. This catches a renamed PNG/blob misrepresented as SARC.
    diff = sarc.compare(original, patched_archive)
    require(diff["changed_members"] and all(
                x["status"] == "modified_member" and x["name"].lower().endswith(".bntx")
                for x in diff["changed_members"]),
            "unexpected non-BNTX UI edits or no modified member")
    require(not destination.exists() and not destination.is_symlink() and
            destination.parent.is_dir() and not destination.parent.is_symlink(),
            "destination must be new in an ordinary parent directory")
    temp = Path(tempfile.mkdtemp(prefix=".eden-botw-pack-", dir=destination.parent))
    try:
        replacement = temp / "replacement" / relative
        replacement.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(patched_archive, replacement)
        require(sha(replacement) == sha(patched_archive),
                "staged replacement checksum mismatch")
        manifest = {
            "schema": 2,
            "title_id": title_id.upper(),
            "update_version": update_version,
            "rights": ("Derived Nintendo-game-owned original UI: local use only; "
                       "artist-owned Zacksly PS5 icons CC BY 3.0"),
            "files": [{
                "romfs_path": relative.as_posix(),
                "replacement": (Path("replacement") / relative).as_posix(),
                "original_sha256": sha(original),
                "replacement_sha256": sha(replacement),
            }],
        }
        (temp / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (temp / "ARTWORK_ATTRIBUTION.txt").write_text(
            "PS5 Button Icons and Controls by Zacksly (CC BY 3.0)\n"
            "https://creativecommons.org/licenses/by/3.0/\n"
            "Game-owned Switch original/modified archive is for local use, "
            "not redistribution.\n")
        (temp / "HOST_TEST_ONLY.txt").write_text(
            "STAGED CANDIDATE ONLY: do not enable until a compatible "
            "native glyph rule and real PS5 UI/game update test exist.\n")
        pack.verify(temp, original_romfs, title_id)
        os.rename(temp, destination)
        return destination
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-romfs", required=True, type=Path)
    p.add_argument("--modified-archive", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--romfs-path", required=True)
    p.add_argument("--title-id", required=True)
    p.add_argument("--update-version", required=True)
    p.add_argument("--pack-out", required=True, type=Path)
    a = p.parse_args()
    try:
        require(a.receipt.is_file() and not a.receipt.is_symlink() and
                a.receipt.stat().st_size < 128 * 1024, "receipt missing or too large")
        value = json.loads(a.receipt.read_text())
        output = stage(a.original_romfs, a.modified_archive, value,
                       a.romfs_path, a.title_id, a.update_version, a.pack_out)
        print("LOCAL-ONLY STAGED GLYPH PACK", output,
              "(not installed, not runtime-qualified)")
        return 0
    except (InvalidStage, pack.InvalidPack, sarc.UnsafeArchive,
            sarc.botw.InvalidYaz0, sarc.botw.sarc.InvalidSarc,
            OSError, ValueError, KeyError, TypeError) as e:
        print("REJECTED BOTW PACK STAGING", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
