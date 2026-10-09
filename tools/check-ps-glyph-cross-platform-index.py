#!/usr/bin/env python3
"""Verify that cross-platform prompt research never silently becomes Switch support.

A PC/Wii U/PSP UI mod can help locate asset names, glyph geometry and scene
logic, but cannot establish byte-for-byte equivalence of a Nintendo Switch
game ROMFS or safe automatic replacement. This source-only gate enforces it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parents[1]
SWITCH_INDEX = BASE / "docs/PS_GLYPH_SOURCE_INDEX.json"
CROSS_INDEX = BASE / "docs/PS_GLYPH_CROSS_PLATFORM_INDEX.json"
SEEDS_INDEX = BASE / "docs/PS_GLYPH_SWITCH1_GAME_SEEDS.json"
SHA = re.compile(r"[0-9a-fA-F]{64}\Z")
ID = re.compile(r"cross-[0-9]{3}\Z")
VALID_RELATIONSHIPS = {
    "same_title_different_platform",
    "same_title_earlier_port",
    "related_sequel_edition_not_same_title",
}
VALID_CONFIDENCE = {
    "mod_documentation", "cross_port_explicit_in_switch_mod",
    "mod_changelog", "tool_documentation", "mod_installation_instructions",
    "mod_author_report", "mod_listing",
}


def reject_unless(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def read(path: Path) -> dict:
    reject_unless(path.is_file() and not path.is_symlink() and
                  1 <= path.stat().st_size <= 512 * 1024,
                  f"unsafe/missing source index: {path.name}")
    result = json.loads(path.read_text("utf-8"))
    reject_unless(isinstance(result, dict), "index root is not an object")
    return result


def validate(cross: dict, switch: dict, seeds: dict | None = None) -> dict:
    reject_unless(cross.get("schema") == 1 and switch.get("schema") == 1,
                  "unsupported source index schema")
    original = switch.get("mods")
    sources = cross.get("sources")
    reject_unless(isinstance(original, list) and isinstance(sources, list) and
                  1 <= len(sources) <= 512, "invalid source lists")
    switch_titles = {entry.get("title") for entry in original
                     if isinstance(entry, dict)}
    seeded_titles: set[str] = set()
    if seeds is not None:
        reject_unless(seeds.get("schema") == 1 and isinstance(seeds.get("games"), list),
                      "invalid Switch 1 title seed schema")
        for entry in seeds["games"]:
            reject_unless(isinstance(entry, dict) and isinstance(entry.get("switch_game"), str),
                          "invalid Switch title seed")
            title = entry["switch_game"]
            reject_unless(bool(title) and title not in switch_titles and
                          title not in seeded_titles,
                          "duplicate or empty Switch 1 title seed")
            listing = entry.get("official_switch_listing")
            reject_unless(isinstance(listing, str), "missing official Switch listing")
            listed = urlsplit(listing)
            reject_unless(listed.scheme == "https" and listed.hostname == "www.nintendo.com" and
                          not listed.username and not listed.password,
                          "Switch 1 title seed requires Nintendo's own listing")
            seeded_titles.add(title)
    switch_titles.update(seeded_titles)
    unique_ids: set[str] = set()
    games: set[str] = set()
    platforms: set[str] = set()
    verified = 0
    for item in sources:
        reject_unless(isinstance(item, dict), "invalid cross-platform entry")
        key = item.get("id")
        reject_unless(isinstance(key, str) and ID.fullmatch(key) and
                      key not in unique_ids, "duplicate or invalid research ID")
        unique_ids.add(key)
        title = item.get("switch_game")
        reject_unless(isinstance(title, str) and title in switch_titles,
                      f"{key}: target game missing from Switch 1 source index")
        games.add(title)
        platform = item.get("platform")
        reject_unless(isinstance(platform, str) and 1 <= len(platform) <= 90,
                      f"{key}: invalid source platform")
        platforms.add(platform)
        relationship = item.get("relationship")
        reject_unless(relationship in VALID_RELATIONSHIPS,
                      f"{key}: unsupported platform relationship")
        reject_unless(item.get("confidence") in VALID_CONFIDENCE,
                      f"{key}: unknown evidence level")
        for name in ("engine_family", "transfer_scope"):
            value = item.get(name)
            reject_unless(isinstance(value, str) and 10 <= len(value) <= 600,
                          f"{key}: missing engine/transfer bounds")
        if relationship == "related_sequel_edition_not_same_title":
            reject_unless("NOT proof" in item["transfer_scope"] or
                          "not" in item["transfer_scope"].lower(),
                          f"{key}: related title must explicitly reject offset equivalence")
        uri = item.get("source_url")
        reject_unless(isinstance(uri, str), f"{key}: missing URL")
        parsed = urlsplit(uri)
        reject_unless(parsed.scheme == "https" and bool(parsed.hostname) and
                      not parsed.username and not parsed.password,
                      f"{key}: non-HTTPS or credential-bearing source")
        for field in ("asset_container_family", "features"):
            values = item.get(field)
            reject_unless(isinstance(values, list) and all(
                isinstance(x, str) and 1 <= len(x) <= 200 for x in values),
                f"{key}: invalid {field}")
        sha = item.get("original_switch_texture_sha256")
        reject_unless(sha is None or (isinstance(sha, str) and SHA.fullmatch(sha)),
                      f"{key}: invalid Switch SHA-256")
        rect = item.get("exact_switch_rect_xywh")
        if rect is not None:
            reject_unless(isinstance(rect, list) and len(rect) == 4 and
                          all(type(n) is int and 0 <= n <= 32768 for n in rect) and
                          rect[2] > 0 and rect[3] > 0, f"{key}: invalid exact rectangle")
            reject_unless(item.get("mod_archive_inspected") is True and sha and
                          item.get("original_switch_texture_path") and
                          item.get("original_switch_game_update") and
                          item.get("switch_vs_source_equivalence_proof"),
                          f"{key}: claimed Switch rectangle without real binary equivalence")
            verified += 1
        for layout in item.get("layout_mapping_evidence", []):
            reject_unless(isinstance(layout, dict) and
                          all(isinstance(layout.get(field), str) for field in
                              ("layout", "source_statement", "interpretation")),
                          f"{key}: invalid semantic mapping note")
        # No implicit compatibility based only on a PC/Wii U/PSP mod page.
        if item.get("switch_runtime_qualified") is True:
            reject_unless(rect is not None and item.get("switch_runtime_test_proof"),
                          f"{key}: runtime claim without a verified Switch resource")
    counts = cross.get("statistics")
    reject_unless(isinstance(counts, dict) and
                  counts.get("sources") == len(sources) and
                  counts.get("switch_games_referenced") == len(games) and
                  counts.get("source_platforms") == sorted(platforms) and
                  counts.get("verified_cross_platform_pixel_rects") == verified,
                  "cross-platform coverage statistics inconsistent")
    return {"cross_platform_sources":len(sources),
            "switch_games_referenced":len(games),
            "verified_switch_rectangles":verified,
            "platforms":sorted(platforms),
            "switch1_seed_games":len(seeded_titles)}


def main() -> int:
    try:
        report = validate(read(CROSS_INDEX), read(SWITCH_INDEX), read(SEEDS_INDEX))
        print("CROSS_PLATFORM_RESEARCH_INDEX_VALID " + json.dumps(report, sort_keys=True))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"CROSS_PLATFORM_RESEARCH_INDEX_INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
