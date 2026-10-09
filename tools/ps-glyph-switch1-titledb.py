#!/usr/bin/env python3
"""Offline, conservative Nintendo Switch 1 base-title metadata resolver.

Read a locally supplied JSON export from community Switch TitleDB or a
SwitchBrew-derived list. Match existing Eden Switch-1 research names to
candidate base game Title IDs, without inventing IDs from approximate names.
Never download games, parse encrypted content, or autoactivate glyph artwork.

Supported input variants:
  * list of {title_id/id/titleId, name/title/description}
  * dict mapping 16-digit Title ID -> name or object with name
  * dict mapping NSUID -> object with id/titleId and name (regional TitleDB)

Only 0100...000 Switch 1 base-application-shaped IDs are considered.
Duplicate names resolving to distinct Title IDs remain ambiguous (null).
This is database matching only: title and update/ROMFS/correct edition still
require checking the user's own actual installed game before glyph admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWITCH = ROOT / "docs/PS_GLYPH_SOURCE_INDEX.json"
SEEDS = ROOT / "docs/PS_GLYPH_SWITCH1_GAME_SEEDS.json"
MAX_DB_BYTES = 96 * 1024 * 1024
MAX_RECORDS = 250000
TITLE_ID = re.compile(r"0100[0-9A-Fa-f]{9}000\Z")
NONWORD = re.compile(r"[^\w]+", re.UNICODE)


def clean_name(name: object) -> str | None:
    if not isinstance(name, str) or not name.strip() or len(name) > 320:
        return None
    return NONWORD.sub(" ", name.casefold()).strip()


def is_switch1_base(value: object) -> bool:
    return isinstance(value, str) and TITLE_ID.fullmatch(value) is not None


def entries(data: object):
    """Yield only title-name/ID candidates, never fetched game files."""
    if isinstance(data, dict):
        if isinstance(data.get("titles"), (dict, list)):
            data = data["titles"]
        else:
            data = list(data.items())
    if not isinstance(data, list) or len(data) > MAX_RECORDS:
        raise ValueError("unsupported or oversized title database")
    for record in data:
        if isinstance(record, (tuple, list)) and len(record) == 2:
            key, value = record
            if isinstance(value, dict):
                identifier = value.get("id") or value.get("titleId") or value.get("title_id") or key
                title = value.get("name") or value.get("title") or value.get("description")
            else:
                identifier = key
                title = value
        elif isinstance(record, dict):
            identifier = record.get("title_id") or record.get("titleId") or \
                         record.get("id") or record.get("tid")
            title = record.get("name") or record.get("title") or record.get("description")
        else:
            continue
        if not is_switch1_base(identifier):
            continue
        normalized = clean_name(title)
        if normalized:
            yield normalized, identifier.upper(), str(title).strip()


def read_json(file: Path, bound: int) -> tuple[object, str]:
    if not file.is_file() or file.is_symlink() or not 1 <= file.stat().st_size <= bound:
        raise ValueError("database missing, symlink or out of size bounds")
    with file.open("rb") as handle:
        raw = handle.read(bound + 1)
    if len(raw) > bound:
        raise ValueError("JSON input exceeded bound")
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def resolve(source_db: object, db_sha256: str, switch: dict,
            seeds: dict, all_base_games: bool = False) -> dict:
    known = defaultdict(set)
    display = {}
    for label, tid, exact in entries(source_db):
        known[label].add(tid)
        display.setdefault((label, tid), exact)
    title_names = {obj["title"] for obj in switch["mods"]} | {
        obj["switch_game"] for obj in seeds["games"]}
    resolved = []
    for title in sorted(title_names):
        norm = clean_name(title)
        ids = sorted(known.get(norm, ()))
        resolved.append({
            "requested_switch_game": title,
            "status": "unique_name_candidate" if len(ids) == 1 else
                      "ambiguous_multiple_title_ids" if ids else "not_found_exactly",
            "candidate_title_id": ids[0] if len(ids) == 1 else None,
            "ambiguous_ids": ids if len(ids) > 1 else [],
            "game_update_verified": False,
            "original_romfs_verified": False,
            "actual_installed_game_match_verified": False,
            "glyph_art_compatible": False,
        })
    output = {
        "schema": 1,
        "source": "external_switch1_title_metadata_read_only",
        "external_json_sha256": db_sha256,
        "research_title_count": len(resolved),
        "unique_name_candidates": sum(item["candidate_title_id"] is not None
                                      for item in resolved),
        "ambiguous_names": sum(bool(item["ambiguous_ids"]) for item in resolved),
        "researched_titles": resolved,
        "warning": "A Title ID inferred from a name in external metadata is only a candidate, never a validated user game version or glyph compatibility.",
    }
    if all_base_games:
        pairs = sorted((tid, display[(label, tid)])
                       for label, ids in known.items() for tid in ids)
        output["all_switch1_base_title_candidates"] = [
            {"title_id": tid, "title": name, "glyph_art_compatible": False,
             "update_and_installed_romfs_unverified": True}
            for tid, name in pairs]
    return output


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--title-db", type=Path, required=True, help="local JSON metadata export")
    cli.add_argument("--all-base-games", action="store_true",
                     help="include full deduplicated Switch 1 base-title candidate backlog")
    cli.add_argument("--out", type=Path, help="NEW JSON report path")
    args = cli.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("invalid/occupied output report path")
        db, sha = read_json(args.title_db, MAX_DB_BYTES)
        switch, _ = read_json(SWITCH, 512 * 1024)
        seeds, _ = read_json(SEEDS, 512 * 1024)
        report = resolve(db, sha, switch, seeds, args.all_base_games)
        rendered = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
        if args.out:
            args.out.write_text(rendered, encoding="utf-8")
            print(f"SWITCH 1 TITLEDB {args.out}: {report['unique_name_candidates']} research name candidates, none autoenabled")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f"REJECTED Switch1 TitleDB metadata: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
