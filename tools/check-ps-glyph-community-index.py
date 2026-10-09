#!/usr/bin/env python3
"""Source-only schema/evidence gate for community glyph mod research index.

NEVER infer real compatibility from published mod pages. The source index
is research data, not runtime rules; actionable geometry must be backed
by verified source+replacement SHA and exact title/update evidence.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/PS_GLYPH_SOURCE_INDEX.json"
HEX16 = re.compile(r"[0-9a-fA-F]{16}\Z")
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


def valid_path(value: str) -> bool:
    if not value or len(value) > 240 or value.startswith("/") or "\\" in value or ":" in value or "\x00" in value:
        return False
    return all(bool(part) and part not in (".", "..") and not part.startswith(".")
               for part in value.split("/"))


def validate(data: object) -> dict:
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("mods"), list):
        raise ValueError("invalid research source registry")
    mods = data["mods"]
    if not 1 <= len(mods) <= 512:
        raise ValueError("unexpected source count")
    seen_ids: set[str] = set()
    sites: set[str] = set()
    names = set()
    verified = 0
    for index, item in enumerate(mods):
        if not isinstance(item, dict):
            raise ValueError(f"source #{index}: not an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"community-[0-9]{3}", identifier) or identifier in seen_ids:
            raise ValueError(f"source #{index}: invalid/duplicate ID")
        seen_ids.add(identifier)
        title = item.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError(f"source {identifier}: invalid title")
        names.add(title)
        u = item.get("source_url")
        if not isinstance(u, str):
            raise ValueError(f"source {identifier}: URL missing")
        parsed = urlparse(u)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError(f"source {identifier}: unsafe source URL")
        sites.add(parsed.netloc.lower())
        tid = item.get("title_id")
        if tid is not None and (not isinstance(tid, str) or not HEX16.fullmatch(tid) or int(tid, 16) == 0):
            raise ValueError(f"source {identifier}: malformed title ID")
        for key in ("verified_original_sha256", "verified_replacement_sha256"):
            value = item.get(key)
            if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
                raise ValueError(f"source {identifier}: malformed {key}")
        rect = item.get("rect_xywh")
        if rect is not None:
            if (not isinstance(rect, list) or len(rect) != 4 or
                    any(type(n) is not int or n < 0 for n in rect) or
                    rect[2] == 0 or rect[3] == 0):
                raise ValueError(f"source {identifier}: invalid rect")
            if not (item.get("archive_inspected") and tid and item.get("game_update_reported") and
                    item.get("verified_original_sha256") and item.get("verified_replacement_sha256")):
                raise ValueError(f"source {identifier}: geometry lacking precise binary evidence")
            verified += 1
        if item.get("ps5_qualified") is True:
            # Separate field must record actual native game/start/update pass.
            if rect is None or not item.get("ps5_test_proof"):
                raise ValueError(f"source {identifier}: unproven PS5 claim")
        for lead in item.get("resource_leads", []):
            if not isinstance(lead, dict):
                raise ValueError(f"source {identifier}: bad resource lead")
            path = lead.get("romfs_archive")
            if path is not None and (not isinstance(path, str) or not valid_path(path)):
                raise ValueError(f"source {identifier}: unsafe ROMFS resource lead")
            if lead.get("binary_verified") is True and not item.get("archive_inspected"):
                raise ValueError(f"source {identifier}: uninspected binary claimed verified")
    coverage = data.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("mod_pages") != len(mods) or \
            coverage.get("unique_games") != len(names) or \
            coverage.get("verified_game_atlases") != verified:
        raise ValueError("research source coverage counts are inconsistent")
    return {"sources": len(mods), "games": len(names), "verified_atlases": verified,
            "sites": sorted(sites)}


def main() -> int:
    try:
        if not INDEX.is_file() or INDEX.is_symlink() or INDEX.stat().st_size > 256 * 1024:
            raise ValueError("missing/oversized source index")
        index = json.loads(INDEX.read_text("utf-8"))
        print("PS_GLYPH_SOURCE_INDEX_VALID " + json.dumps(validate(index), sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        print(f"PS_GLYPH_SOURCE_INDEX_INVALID: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
