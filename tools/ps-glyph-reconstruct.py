#!/usr/bin/env python3
"""Rebuild independently authored PS-button atlas specs from verified Switch geometry.

The two essential coordinate spaces are NOT interchangeable:
  guest action A -> PlayStation Cross for the chosen PS5 mapping;
  physical controller right-hand location -> Circle, bottom -> Cross.
An action prompt and a controller diagram require different semantics.
Public mod descriptions and other-platform UI coordinates are DISCOVERY LEADS,
not trustworthy Switch pixel rectangles or permission to copy mod resources.

Two subcommands:
  index: join Switch community and Wii U/PC/PSP references for the whole corpus.
  spec: resolve verified Switch atlas slots into ps-glyph-atlas.py render specs.
No game assets are downloaded, published, installed, or edited by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/PS_GLYPH_SOURCE_INDEX.json"
CROSS = ROOT / "docs/PS_GLYPH_CROSS_PLATFORM_INDEX.json"
SHA = re.compile(r"[0-9a-f]{64}\Z", re.I)
TITLE = re.compile(r"[0-9a-f]{16}\Z", re.I)
ICON = {"a": "cross", "b": "circle", "x": "square", "y": "triangle",
        "l": "l1", "r": "r1", "zl": "l2", "zr": "r2",
        "plus": "options", "minus": "touchpad",
        "left_stick": "l3", "right_stick": "r3"}
SWITCH = dict(ICON, a="circle", b="cross", x="triangle", y="square")
FACE = {"right": "circle", "bottom": "cross",
        "left": "square", "top": "triangle"}
VALID_SCENES = {"menu", "gameplay", "tutorial", "world_interaction", "controller_diagram",
                "hud", "pause", "dialogue", "battle", "special_action"}
MAX_EVIDENCE = 128 * 1024
MAX_IMAGE = 128 * 1024 * 1024
MAX_ATLASES = 64
MAX_SLOTS = 512


class Unverified(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Unverified(message)


def json_file(path: Path, cap: int = MAX_EVIDENCE) -> dict:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= cap,
            f"missing, linked or oversized evidence: {path}")
    raw = json.loads(path.read_text("utf-8"))
    require(isinstance(raw, dict), "JSON root must be an object")
    return raw


def game_key(name: str) -> str:
    # Only formatting aliases; don't merge different games/editions by engine.
    name = re.sub(r"\s*\(Switch\)\s*$", "", name.strip(), flags=re.I)
    return " ".join(name.casefold().split())


def index() -> dict:
    direct, external = json_file(SOURCE, MAX_IMAGE), json_file(CROSS, MAX_IMAGE)
    require(isinstance(direct.get("mods"), list) and
            isinstance(external.get("sources"), list), "source indices unavailable")
    games: dict[str, dict] = {}
    for item in direct["mods"]:
        key = game_key(item["title"])
        entry = games.setdefault(key, {"game": re.sub(r"\s*\(Switch\)$", "", item["title"]),
                                       "switch_mod_leads": [], "cross_platform_leads": [],
                                       "contexts": set()})
        entry["switch_mod_leads"].append({
            "id": item["id"], "url": item["source_url"],
            "style": item.get("style"),
            "asset_rect_verified": item.get("rect_xywh") is not None and
                                    item.get("verified_original_sha256") is not None,
            "archive_inspected": item.get("archive_inspected") is True,
        })
        entry["contexts"].update(item.get("contexts") or [])
    for item in external["sources"]:
        key = game_key(item["switch_game"])
        entry = games.setdefault(key, {"game": re.sub(r"\s*\(Switch\)$", "", item["switch_game"]),
                                       "switch_mod_leads": [], "cross_platform_leads": [],
                                       "contexts": set()})
        entry["cross_platform_leads"].append({
            "id": item["id"], "platform": item["platform"],
            "url": item["source_url"],
            "switch_geometry_verified": item.get("original_switch_texture_sha256") is not None and
                                        item.get("exact_switch_rect_xywh") is not None,
        })
    results = []
    for value in sorted(games.values(), key=lambda x: x["game"].casefold()):
        value["contexts"] = sorted(value["contexts"])
        value["builtin_game_pack_ready"] = False
        value["reason"] = ("Public sources describe control semantics, but do not establish "
                           "a matching Switch atlas/update and per-slot pixel coordinates.")
        results.append(value)
    return {"schema": 1, "game_count": len(results),
            "switch_mod_references": len(direct["mods"]),
            "cross_platform_references": len(external["sources"]),
            "verified_reconstruction_specs_from_public_indices": 0,
            "games": results}


def checked_path(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and 0 < len(relative) <= 240 and
            not relative.startswith("/") and "\\" not in relative and ":" not in relative,
            "unsafe RomFS resource path")
    parts = PurePosixPath(relative).parts
    require(all(p not in ("", ".", "..") and not p.startswith(".") for p in parts) and
            "/".join(parts) == relative, "noncanonical RomFS path")
    require(root.is_dir() and not root.is_symlink(), "RomFS must be a real directory")
    path = root
    for segment in parts:
        path = path / segment
        require(not path.is_symlink(), "symlink in RomFS resource path")
    require(path.is_file() and path.stat().st_size <= MAX_IMAGE,
            "verified Switch atlas missing or exceeds size limit")
    return path


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def glyph_for_slot(slot: dict, profile: str) -> str:
    require(isinstance(slot, dict), "slot must be an object")
    kind = slot.get("kind")
    if kind == "guest_action":
        action = slot.get("guest_button")
        require(action in ICON, "guest_action requires a known guest button")
        return (ICON if profile == "playstation" else SWITCH)[action]
    if kind == "controller_position":
        face = slot.get("face")
        require(face in FACE, "controller_position requires right/bottom/left/top")
        # A diagram conveys spatial location, NOT action semantics.
        return FACE[face]
    raise Unverified("ambiguous slot semantics; expected guest_action or controller_position")


def verified_cross_platform(report_path: Path, switch_sha: str,
                            rectangle: list[int]) -> None:
    report = json_file(report_path)
    require(report.get("schema") == 1 and
            report.get("original_texture_comparison") == "rendered_pixels_identical" and
            report.get("switch_original_image_sha256") == switch_sha,
            "other-platform atlas not pixel-equivalent to this Switch original")
    candidates = report.get("switch_candidate_rects_xywh")
    require(isinstance(candidates, list) and candidates,
            "no pixel-difference coordinates transferable to Switch")
    x, y, w, h = rectangle
    # The changed-pixel rectangle may be smaller than the isolated slot,
    # but MUST be fully included in the explicitly measured slot.
    require(any(isinstance(candidate, list) and len(candidate) == 4 and
                all(type(n) is int for n in candidate) and
                x <= candidate[0] and y <= candidate[1] and
                candidate[0] + candidate[2] <= x + w and
                candidate[1] + candidate[3] <= y + h
                for candidate in candidates),
            "proposed slot does not contain any byte-verified transferred region")


def build_spec(evidence: dict, romfs: Path, evidence_base: Path) -> dict:
    require(evidence.get("schema") == 1, "unsupported reconstruction evidence schema")
    title = evidence.get("title_id")
    version = evidence.get("update_version")
    require(isinstance(title, str) and TITLE.fullmatch(title) and int(title, 16),
            "real nonzero Switch title_id required")
    require(isinstance(version, str) and 0 < len(version) <= 64 and
            all(32 <= ord(ch) < 127 for ch in version),
            "exact running Switch update version required")
    profile = evidence.get("profile")
    require(profile in ("playstation", "switch"), "explicit static session profile required")
    variant = evidence.get("variant", "outline-white")
    require(variant in ("outline-white", "outline-black", "solid-white", "solid-black",
                       "full-white", "full-black"), "invalid output icon variant")
    atlases = evidence.get("atlases")
    require(isinstance(atlases, list) and 0 < len(atlases) <= MAX_ATLASES,
            "real Switch image/scene evidence required")
    result = []
    seen = set()
    for image in atlases:
        require(isinstance(image, dict), "invalid atlas evidence")
        relative = image.get("romfs_path")
        source = checked_path(romfs, relative)
        require(source.suffix.lower() in (".png", ".tga"),
                "proprietary texture requires a separately verified unpack/repack pathway")
        sha = image.get("original_sha256")
        require(isinstance(sha, str) and SHA.fullmatch(sha) and
                digest(source) == sha.lower(), "Switch atlas SHA-256 is not verified")
        scene = image.get("scene")
        require(scene in VALID_SCENES, "explicit and known UI scene required")
        key = relative.casefold()
        require(key not in seen, "duplicate atlas; combine scenes into one independent source spec")
        seen.add(key)
        geometry = image.get("geometry_evidence")
        require(geometry in ("switch_inspected", "cross_platform_verified"),
                "source mod filename/UI coordinates are not Switch pixel evidence")
        slots = image.get("slots")
        require(isinstance(slots, list) and 0 < len(slots) <= MAX_SLOTS,
                "verified atlas must have 1-512 slots")
        verified = []
        from PIL import Image
        with Image.open(source) as pixels:
            require(pixels.mode == "RGBA" and pixels.width * pixels.height <= 25_000_000,
                    "only decoded original RGBA Switch texture with valid dimensions")
            for slot in slots:
                require(isinstance(slot, dict), "each sprite slot must be an object")
                rect = slot.get("rect")
                require(isinstance(rect, list) and len(rect) == 4 and
                        all(type(n) is int for n in rect), "measured pixel XYWH required")
                x, y, w, h = rect
                require(x >= 0 and y >= 0 and w >= 3 and h >= 3 and
                        x + w <= pixels.width and y + h <= pixels.height,
                        "slot outside actual Switch texture")
                require(not any(x < ox + ow and ox < x + w and
                                y < oy + oh and oy < y + h
                                for ox, oy, ow, oh in (entry["rect"] for entry in verified)),
                        "two independent glyph slots overlap")
                sprite = pixels.crop((x, y, x + w, y + h))
                bounds = sprite.getchannel("A").getbbox()
                require(bounds is not None and bounds[0] > 0 and bounds[1] > 0 and
                        bounds[2] < w and bounds[3] < h,
                        "slot is empty or erases adjacent UI; isolate with alpha margin")
                if geometry == "cross_platform_verified":
                    report = image.get("cross_platform_report")
                    require(isinstance(report, str) and
                            report == Path(report).name and not report.startswith("."),
                            "cross-platform proof report basename required")
                    verified_cross_platform(evidence_base / report, sha.lower(), rect)
                verified.append({"button": glyph_for_slot(slot, profile), "rect": rect})
        result.append({"romfs_path": relative, "original_sha256": sha.lower(),
                       "slots": verified})
    return {"schema": 1, "title_id": title.upper(), "update_version": version,
            "variant": variant, "atlases": result}


def new_json(path: Path, data: dict) -> None:
    require(not path.exists() and not path.is_symlink() and
            path.parent.is_dir() and not path.parent.is_symlink(),
            "output must be a new file inside an existing real directory")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("index", help="consolidated Switch/Wii U/PC/PSP work queue")
    i.add_argument("--out", type=Path, help="new output JSON")
    s = sub.add_parser("spec", help="verified original Switch pixels -> artist-owned render spec")
    s.add_argument("--evidence", type=Path, required=True)
    s.add_argument("--romfs", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    opts = p.parse_args()
    try:
        if opts.command == "index":
            outcome = index()
            if opts.out:
                new_json(opts.out, outcome)
            else:
                print(json.dumps(outcome, indent=2, ensure_ascii=False))
        else:
            outcome = build_spec(json_file(opts.evidence), opts.romfs,
                                 opts.evidence.parent)
            new_json(opts.out, outcome)
            print(f"VERIFIED GEOMETRY SPEC {opts.out}; run ps-glyph-atlas.py render "
                  "(not installed, PS5 hardware untested)")
        return 0
    except (Unverified, ValueError, OSError) as e:
        print(f"RECONSTRUCTION BLOCKED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
