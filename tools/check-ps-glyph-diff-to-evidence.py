#!/usr/bin/env python3
"""Synthetic integration: real pixel diff -> safe candidate sprite -> semantic spec.

All graphics are generated synthetically in a temporary host fixture.
No real mod/download, copyrighted asset, console or installed ROMFS changed.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent


def load(name: str, filename: str):
    sp = importlib.util.spec_from_file_location(name, TOOLS / filename)
    assert sp and sp.loader
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod


candidate = load("eden_diff_evidence_fixture", "ps-glyph-diff-to-evidence.py")
reconstruct = candidate.reconstruct
pixel_diff = load("eden_pixel_diff_fixture", "ps-glyph-mod-diff.py")


def refuses(f, category: str) -> None:
    try:
        f()
    except (ValueError, OSError):
        return
    raise AssertionError(f"accepted unsafe or unqualified {category}")


with tempfile.TemporaryDirectory(prefix="eden-verified-mod-positions-") as folder:
    root = Path(folder)
    romfs = root / "romfs"
    atlas = romfs / "UI" / "test.png"
    atlas.parent.mkdir(parents=True)

    original = Image.new("RGBA", (128, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(original)
    draw.rectangle((10, 10, 40, 40), fill=(255, 255, 255, 255))
    draw.rectangle((75, 10, 105, 40), fill=(200, 200, 200, 255))
    original.save(atlas, "PNG")

    changed = original.copy()
    edited = ImageDraw.Draw(changed)
    edited.rectangle((15, 15, 35, 35), fill=(24, 100, 230, 255))
    edited.rectangle((80, 15, 100, 35), fill=(240, 18, 25, 255))
    replacement = root / "mod.png"
    changed.save(replacement, "PNG")

    sha = hashlib.sha256(atlas.read_bytes()).hexdigest()
    replacement_sha = hashlib.sha256(replacement.read_bytes()).hexdigest()
    report = pixel_diff.image_diff(atlas.read_bytes(), replacement.read_bytes())
    assert report["status"] == "pixels_differ"
    assert report["changed_pixels"] > 0
    record = dict(report, romfs_path="UI/test.png", original_sha256=sha,
                  replacement_sha256=replacement_sha)
    difference = {"schema": 1, "resources": [record]}
    draft = candidate.draft(difference, romfs, "01007EF00011E000", "1.6.0",
                            "playstation", "world_interaction", "a" * 64)
    assert len(draft["atlases"]) == 1, draft
    slots = draft["atlases"][0]["slots"]
    assert len(slots) == 2, slots
    assert all(x["kind"] is None and x["scene_semantics_approved"] is False for x in slots)
    assert slots[0]["rect"] != slots[1]["rect"]
    assert all(x["matched_diff_components"] > 0 for x in slots)
    assert draft["unresolved_resources"] == []
    assert draft["draft_provenance"]["semantics_approved"] is False
    refuses(lambda: reconstruct.build_spec(draft, romfs, root), "unreviewed glyph meaning")

    reviewed = json.loads(json.dumps(draft))
    for index, slot in enumerate(reviewed["atlases"][0]["slots"]):
        slot.pop("matched_diff_components")
        slot.pop("scene_semantics_approved")
        slot.pop("face")
        slot["kind"] = "guest_action"
        slot["guest_button"] = "a" if index == 0 else "b"
    # This is a host-only synthetic approval. A REAL texture must not be
    # approved based on public mod text, unlabeled differences, or guessed IDs.
    result = reconstruct.build_spec(reviewed, romfs, root)
    assert [x["button"] for x in result["atlases"][0]["slots"]] == ["cross", "circle"]
    reviewed["profile"] = "switch"
    result = reconstruct.build_spec(reviewed, romfs, root)
    assert [x["button"] for x in result["atlases"][0]["slots"]] == ["circle", "cross"]

    bad = json.loads(json.dumps(difference))
    bad["resources"][0]["original_sha256"] = "0" * 64
    refuses(lambda: candidate.draft(bad, romfs, "01007EF00011E000", "1.6.0",
                                    "playstation", "gameplay"), "mismatched original hash")
    bad = json.loads(json.dumps(difference))
    bad["resources"][0]["changed_rects_xywh"] = [[10, 10, 99999, 99999]]
    refuses(lambda: candidate.draft(bad, romfs, "01007EF00011E000", "1.6.0",
                                    "playstation", "gameplay"), "out-of-bounds changed rectangle")

    bad = json.loads(json.dumps(difference))
    bad["resources"][0]["romfs_path"] = "UI/../test.png"
    refuses(lambda: candidate.draft(bad, romfs, "01007EF00011E000", "1.6.0",
                                    "playstation", "gameplay"), "path escape")
    bad = json.loads(json.dumps(difference))
    bad["resources"].append(bad["resources"][0])
    refuses(lambda: candidate.draft(bad, romfs, "01007EF00011E000", "1.6.0",
                                    "playstation", "gameplay"), "case/duplicate path")

    # Pixel changes to a full-opacity background are NOT isolated icons:
    # no magic rect or autoapproved button should be produced.
    background = Image.new("RGBA", (128, 64), (40, 40, 40, 255))
    background.save(atlas)
    new_sha = hashlib.sha256(atlas.read_bytes()).hexdigest()
    changed_background = background.copy()
    changed_background.putpixel((5, 5), (255, 0, 0, 255))
    changed_background.save(replacement)
    bad = pixel_diff.image_diff(atlas.read_bytes(), replacement.read_bytes())
    bad = {"schema": 1, "resources": [dict(bad, romfs_path="UI/test.png",
                                          original_sha256=new_sha)]}
    rejected = candidate.draft(bad, romfs, "01007EF00011E000", "1.6.0",
                               "playstation", "gameplay")
    assert not rejected["atlases"] and rejected["unresolved_resources"]
    assert rejected["unresolved_resources"][0]["reason"] == (
        "unisolated_or_ambiguous_diff_components")

    # Never overwrite a generated report even if it was produced here.
    output = root / "draft.json"
    reconstruct.new_json(output, rejected)
    refuses(lambda: reconstruct.new_json(output, rejected), "existing output")

print("PASS: real synthetic pixel-change components grouped into alpha-isolated Switch glyph drafts")
print("PASS: action mapping verified and unapproved/wrong-hash/unsafe/opaque sprites rejected")
print("No original BOTW texture or PlayStation glyph mod was downloaded or shipped.")
