#!/usr/bin/env python3
"""Turn real Switch original-vs-mod image differences into UNSIGNED glyph drafts.

Inputs: a report from ps-glyph-mod-diff.py or ps-glyph-mod-folder-diff.py,
and the matching, legitimately extracted original Switch RomFS. Only
PNG/TGA RGBA images with isolated original alpha sprites are supported.

The original RomFS is never modified. Diff components are NOT sprite slots:
they may be separate arms of one Cross or a change to non-glyph UI.
Match them against independently inspected *original* alpha-isolated
sprite rectangles, and leave all resulting button names UNASSIGNED.
A human must confirm semantic action, scene, version, file provenance
and art rights before ps-glyph-reconstruct.py spec accepts any entry.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

HERE = Path(__file__).resolve().parent
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_RESOURCES = 1024
MAX_CHANGED = 1024
MAX_CANDIDATES = 512


def helper(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ValueError(f"missing required offline helper {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reconstruct = helper("eden_diff_evidence_reconstruct", "ps-glyph-reconstruct.py")
scanner = helper("eden_diff_evidence_scan", "ps-glyph-scan.py")


def contains(outer: list[int], inner: list[int]) -> bool:
    x, y, w, h = outer
    a, b, c, d = inner
    return x <= a and y <= b and a + c <= x + w and b + d <= y + h


def xywh(value: object, size: tuple[int, int]) -> list[int]:
    if not isinstance(value, list) or len(value) != 4 or any(type(n) is not int for n in value):
        raise ValueError("diff rectangle must be four integers")
    x, y, w, h = value
    if x < 0 or y < 0 or w < 1 or h < 1 or x + w > size[0] or y + h > size[1]:
        raise ValueError("diff rectangle outside original Switch image")
    return value


def draft(diff_report: dict, romfs: Path, title: str, update: str,
          profile: str, scene: str, report_sha256: str = "") -> dict:
    reconstruct.require(diff_report.get("schema") == 1 and
                        isinstance(diff_report.get("resources"), list) and
                        len(diff_report["resources"]) <= MAX_RESOURCES,
                        "unsupported or excessive mod-difference report")
    reconstruct.require(isinstance(title, str) and reconstruct.TITLE.fullmatch(title) and
                        int(title, 16) != 0, "real Switch Title ID required")
    reconstruct.require(isinstance(update, str) and 0 < len(update) <= 64 and
                        all(32 <= ord(c) < 127 for c in update),
                        "explicit actual running update version required")
    reconstruct.require(profile in ("playstation", "switch"), "explicit input profile required")
    reconstruct.require(scene in reconstruct.VALID_SCENES, "explicit UI scene required")
    # All original ROMFS file accesses follow the same symlink/size checks as
    # the final verified reconstruction pipeline.
    atlases = []
    unresolved = []
    paths = set()
    for resource in diff_report["resources"]:
        reconstruct.require(isinstance(resource, dict), "resource must be an object")
        name = resource.get("romfs_path")
        if not isinstance(name, str):
            continue
        if resource.get("status") != "pixels_differ":
            unresolved.append({"romfs_path": name, "reason": "unsupported_or_unchanged"})
            continue
        if len(atlases) >= reconstruct.MAX_ATLASES:
            unresolved.append({"romfs_path": name, "reason": "atlas_count_limit"})
            continue
        key = name.casefold()
        reconstruct.require(key not in paths, "duplicate/case-colliding source atlas")
        paths.add(key)
        source = reconstruct.checked_path(romfs, name)
        if source.suffix.lower() not in (".png", ".tga"):
            unresolved.append({"romfs_path": name, "reason": "proprietary_source_requires_decoder"})
            continue
        original_sha = resource.get("original_sha256")
        reconstruct.require(isinstance(original_sha, str) and
                            reconstruct.SHA.fullmatch(original_sha) and
                            reconstruct.digest(source) == original_sha.lower(),
                            "original Switch game/update SHA-256 does not match diff")
        with Image.open(source) as image:
            reconstruct.require(image.format in ("PNG", "TGA") and image.mode == "RGBA" and
                                0 < image.width * image.height <= scanner.MAX_SCAN_PIXELS,
                                "original must be decoded RGBA image within scan budget")
            dims = image.size
            rectangles = resource.get("changed_rects_xywh")
            reconstruct.require(isinstance(rectangles, list) and
                                0 < len(rectangles) <= MAX_CHANGED and
                                tuple(resource.get("dimensions", ())) == dims,
                                "diff lacks compatible changed image dimensions")
            candidates = scanner.alpha_candidates(image)
        reconstruct.require(len(candidates) <= MAX_CANDIDATES, "excess alpha candidates")
        matched: dict[tuple[int, int, int, int], int] = {}
        unmatched = 0
        for raw in rectangles:
            changed = xywh(raw, dims)
            targets = [tuple(slot) for slot in candidates if contains(slot, changed)]
            # Do not merge a UI background change or ambiguous overlapping
            # candidates into a supposedly verified button sprite.
            if len(targets) != 1:
                unmatched += 1
                continue
            matched[targets[0]] = matched.get(targets[0], 0) + 1
        slots = [
            {"kind": None, "guest_button": None, "face": None,
             "rect": list(rect), "scene_semantics_approved": False,
             "matched_diff_components": n}
            for rect, n in sorted(matched.items(), key=lambda pair: (pair[0][1], pair[0][0]))
        ]
        if slots:
            atlases.append({
                "romfs_path": name,
                "original_sha256": original_sha.lower(),
                "scene": scene,
                "geometry_evidence": "switch_inspected",
                "slots": slots,
            })
        if unmatched or not slots:
            unresolved.append({"romfs_path": name,
                               "reason": "unisolated_or_ambiguous_diff_components",
                               "unmatched_components": unmatched,
                               "total_changed_components": len(rectangles)})
    return {
        "schema": 1, "title_id": title.upper(), "update_version": update,
        "profile": profile, "variant": "outline-white",
        "atlases": atlases,
        "unresolved_resources": unresolved,
        "draft_provenance": {
            "diff_report_sha256": report_sha256,
            "semantics_approved": False,
            "running_update_verified": False,
            "original_assets_not_redistributed": True,
        },
        "warning": ("UNAPPROVED glyph positions. Assign each slot's kind and "
                    "guest_button or face only after independent scene review. "
                    "Remove review-only keys before final spec approval. "
                    "BNTX/BFRES/BLARC require separately qualified decoding/repacking."),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--diff-report", type=Path, required=True)
    p.add_argument("--original-romfs", type=Path, required=True)
    p.add_argument("--title-id", required=True)
    p.add_argument("--update-version", required=True)
    p.add_argument("--profile", choices=("playstation", "switch"), default="playstation")
    p.add_argument("--scene", choices=sorted(reconstruct.VALID_SCENES), required=True)
    p.add_argument("--out", type=Path, required=True, help="new JSON report; cannot overwrite")
    a = p.parse_args()
    try:
        d = reconstruct.json_file(a.diff_report, MAX_REPORT_BYTES)
        report_sha256 = hashlib.sha256(a.diff_report.read_bytes()).hexdigest()
        result = draft(d, a.original_romfs, a.title_id, a.update_version,
                       a.profile, a.scene, report_sha256)
        reconstruct.new_json(a.out, result)
        print(f"UNAPPROVED GLYPH DRAFT {a.out}: "
              f"{sum(len(item['slots']) for item in result['atlases'])} independent candidates, "
              f"{len(result['unresolved_resources'])} unresolved resources")
        return 0
    except (OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError) as error:
        print(f"RECONSTRUCTION DRAFT REJECTED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
