#!/usr/bin/env python3
"""Turn mod-discovered real Switch glyph rects into version/hash-bound draft plans.

No manual XYWH transcription: consume ps-glyph-mod-zip-positions.py's
actual decoded original/mod ASTC evidence. Only asset names that explicitly
identify a SINGLE guest action can supply a *suggestion* (A/B/X/Y).
Ambiguous sprite sheets and spatial controller diagrams stay unlabeled.

An approved binding map can supply separately checked action/face semantics
without editing or redistributing the third-party mod. Generated specs
remain non-executable drafts unless every label is approved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_REPORT_BYTES = 5 * 1024 * 1024
MAX_OPERATIONS = 512
MAX_BINDINGS = 512


class InvalidPlan(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise InvalidPlan(reason)


def semantic_hint(texture_name: str, count: int) -> dict | None:
    if count != 1:
        return None
    # Extract only explicit action indicators. 'A' in an opaque texture
    # or unrelated word is not evidence of a Nintendo guest input.
    tokens = re.split(r"[^a-zA-Z0-9]+", texture_name.casefold())
    keys = [x for x in tokens if x in ("a", "b", "x", "y")]
    keywords = {"button", "btn", "prompt", "action", "control", "key", "input"}
    if len(keys) != 1 or not any(x in keywords for x in tokens):
        return None
    return {"kind": "guest_action", "guest_button": keys[0]}


def make(report: dict, title_id: str, update: str, binding: dict | None = None) -> dict:
    require(report.get("schema") == 1 and
            isinstance(report.get("matched_archives"), list),
            "mod ZIP coordinate evidence absent")
    require(isinstance(title_id, str) and re.fullmatch(r"[0-9a-fA-F]{16}", title_id)
            and int(title_id, 16) != 0 and
            isinstance(update, str) and re.fullmatch(r"[a-zA-Z0-9_.+ -]{1,64}", update),
            "exact Title ID and version are required")
    binding = binding or {}
    require(isinstance(binding, dict) and len(binding) <= MAX_BINDINGS,
            "invalid semantic bindings")
    plans, unresolved = [], []
    for item in report["matched_archives"]:
        relative = item["romfs_path"]
        underlying = item.get("positions", {})
        for image in underlying.get("textures", []):
            slots = image.get("detected_original_switch_slots")
            if not isinstance(slots, list) or not slots:
                unresolved.append({"romfs_path": relative, "member": image["member"],
                                   "texture": image["texture"],
                                   "reason": "no_isolated_source_sprite_geometry"})
                continue
            found = []
            hint = semantic_hint(image["texture"], len(slots))
            for ordinal, candidate in enumerate(slots):
                rect = candidate.get("rect_xywh")
                require(isinstance(rect, list) and len(rect) == 4 and
                        all(type(n) is int and n >= 0 for n in rect) and
                        rect[2] > 0 and rect[3] > 0,
                        "unverified original Switch pixel rectangle")
                address = f"{relative}|{image['member']}|{image['texture']}|{ordinal}"
                approved = binding.get(address)
                if approved is not None:
                    require(isinstance(approved, dict) and approved.get("reviewed") is True,
                            "semantic binding requires explicit independent review")
                    kind = approved.get("kind")
                    require(kind in ("guest_action", "controller_position"),
                            "unknown approved meaning")
                    marker = ("guest_button" if kind == "guest_action" else "face")
                    value = approved.get(marker)
                    require(value in (("a", "b", "x", "y") if kind == "guest_action" else
                                      ("top", "right", "bottom", "left")),
                            "invalid reviewed Nintendo action/controller position")
                    resolved = {"kind": kind, marker: value,
                                "rect": rect, "reviewed": True, "source": "explicit_scene_review"}
                else:
                    resolved = {"kind": hint["kind"] if hint else None,
                                "guest_button": hint["guest_button"] if hint else None,
                                "rect": rect, "reviewed": False,
                                "source": "unverified_texture_name_hint" if hint else
                                          "unresolved_mod_visual_semantics"}
                found.append(resolved)
            plans.append({
                "romfs_path": relative,
                "manifest": {
                    "schema": 1, "title_id": title_id.upper(),
                    "update_version": update, "profile": "playstation",
                    "original_archive_sha256": item["original_file_sha256"],
                    "original_member_sha256": image["original_bntx_sha256"],
                    "member": image["member"], "texture": image["texture"],
                    "scene": image["scene"], "variant": "outline-white",
                    "slots": found,
                },
                "ready_for_assembler_after_review": all(x["reviewed"] for x in found),
                "recognized_from_exact_mod_original_pixel_diff": True,
            })
            require(len(plans) <= MAX_OPERATIONS, "too many candidate sprite operations")
    return {
        "schema": 1,
        "title_id": title_id.upper(), "update_version": update,
        "plans": plans,
        "unresolved": unresolved,
        "approved_operation_count": sum(x["ready_for_assembler_after_review"] for x in plans),
        "asset_action_hints_are_not_approved": True,
        "active_game_mod_produced": False,
        "warning": ("All XYWH are derived from actual changed Switch mod pixels "
                    "and matching original. A/B/X/Y label hints from asset names "
                    "are NOT scene evidence. Keep reviewed=false until the game's "
                    "actual input/help UI semantics are independently verified."),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zip-positions", type=Path, required=True)
    p.add_argument("--title-id", required=True)
    p.add_argument("--update-version", required=True)
    p.add_argument("--bindings", type=Path,
                   help="optional exact slot keys and independently reviewed labels")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    try:
        for source in (a.zip_positions, a.bindings):
            if source is not None:
                require(source.is_file() and not source.is_symlink() and
                        source.stat().st_size <= MAX_REPORT_BYTES,
                        "missing/unsafe glyph report or semantic bindings")
        require(not a.out.exists() and not a.out.is_symlink() and
                a.out.parent.is_dir() and not a.out.parent.is_symlink(),
                "output must be new")
        original = json.loads(a.zip_positions.read_text("utf-8"))
        binds = (json.loads(a.bindings.read_text("utf-8"))
                 if a.bindings is not None else None)
        data = make(original, a.title_id, a.update_version, binds)
        a.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print("MOD-DERIVED GLYPH DRAFTS:", len(data["plans"]),
              "candidate textures;", data["approved_operation_count"],
              "independently reviewed")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as e:
        print("REJECTED MOD-DERIVED GLYPH PLAN", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
