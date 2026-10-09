#!/usr/bin/env python3
"""Host-only tests for independent PS5 glyph reconstruction; synthetic pixels.

No Nintendo texture, licensed icon ZIP, game mod, live PS5 or game dump used.
"""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eden_ps_glyph_reconstruct",
                                              ROOT / "tools/ps-glyph-reconstruct.py")
assert spec and spec.loader
recon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recon)

index = recon.index()
assert index["switch_mod_references"] >= 26
assert index["cross_platform_references"] >= 22
assert index["game_count"] >= 18
assert index["verified_reconstruction_specs_from_public_indices"] == 0
botw = next(game for game in index["games"] if game["game"] == "Zelda: Breath of the Wild")
assert any("659253" in m["url"] for m in botw["switch_mod_leads"])
assert any(s["platform"] == "Wii U" for s in botw["cross_platform_leads"])
assert not botw["builtin_game_pack_ready"]

def blocked(call, reason: str) -> None:
    try:
        call()
    except recon.Unverified:
        return
    raise AssertionError(f"reconstruction accepted unverified {reason}")

def png(img: Image.Image) -> bytes:
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()

with tempfile.TemporaryDirectory(prefix="eden-reconstruct-test-") as base:
    root = Path(base)
    romfs = root / "romfs"
    atlas = romfs / "UI" / "buttons.png"
    atlas.parent.mkdir(parents=True)
    image = Image.new("RGBA", (128, 96))
    draw = ImageDraw.Draw(image)
    positions = [(8, 8, 40, 40), (56, 8, 40, 40),
                 (8, 50, 40, 40), (56, 50, 40, 40)]
    for x, y, w, h in positions:
        draw.rectangle((x + 4, y + 4, x + w - 5, y + h - 5),
                       outline=(240, 240, 240, 255), width=3)
    atlas.write_bytes(png(image))
    sha = hashlib.sha256(atlas.read_bytes()).hexdigest()

    evidence = {
        "schema": 1, "title_id": "01007EF00011E000", "update_version": "1.6.0",
        "profile": "playstation", "variant": "outline-white",
        "atlases": [{
            "romfs_path": "UI/buttons.png", "original_sha256": sha,
            "scene": "controller_diagram", "geometry_evidence": "switch_inspected",
            "slots": [
                {"kind": "guest_action", "guest_button": "a", "rect": [8, 8, 40, 40]},
                {"kind": "guest_action", "guest_button": "b", "rect": [56, 8, 40, 40]},
                {"kind": "controller_position", "face": "right", "rect": [8, 50, 40, 40]},
                {"kind": "controller_position", "face": "bottom", "rect": [56, 50, 40, 40]},
            ],
        }],
    }
    built = recon.build_spec(evidence, romfs, root)
    assert built["atlases"][0]["slots"] == [
        {"button": "cross", "rect": [8, 8, 40, 40]},
        {"button": "circle", "rect": [56, 8, 40, 40]},
        {"button": "circle", "rect": [8, 50, 40, 40]},
        {"button": "cross", "rect": [56, 50, 40, 40]},
    ]
    evidence["profile"] = "switch"
    physical = recon.build_spec(evidence, romfs, root)
    assert physical["atlases"][0]["slots"][0]["button"] == "circle"
    assert physical["atlases"][0]["slots"][1]["button"] == "cross"
    assert physical["atlases"][0]["slots"][2:] == built["atlases"][0]["slots"][2:]
    evidence["profile"] = "playstation"

    # A PC/Wii U atlas location or mod author text is not a Switch pixel coordinate.
    evidence["atlases"][0]["geometry_evidence"] = "community_mod_position"
    blocked(lambda: recon.build_spec(evidence, romfs, root), "mod text")
    evidence["atlases"][0]["geometry_evidence"] = "cross_platform_verified"
    blocked(lambda: recon.build_spec(evidence, romfs, root), "missing pixel equivalence")
    report = {
        "schema": 1, "original_texture_comparison": "rendered_pixels_identical",
        "switch_original_image_sha256": sha,
        "switch_candidate_rects_xywh": [
            [11, 11, 32, 32], [59, 11, 32, 32],
            [11, 53, 32, 32], [59, 53, 32, 32],
        ],
    }
    path = root / "comparison.json"
    path.write_text(json.dumps(report))
    evidence["atlases"][0]["cross_platform_report"] = path.name
    assert recon.build_spec(evidence, romfs, root) == built
    report["switch_original_image_sha256"] = "0" * 64
    path.write_text(json.dumps(report))
    blocked(lambda: recon.build_spec(evidence, romfs, root), "wrong Switch hash")
    report["switch_original_image_sha256"] = sha
    report["switch_candidate_rects_xywh"] = [[100, 90, 2, 2]]
    path.write_text(json.dumps(report))
    blocked(lambda: recon.build_spec(evidence, romfs, root), "other-game coordinates")
    evidence["atlases"][0]["geometry_evidence"] = "switch_inspected"
    evidence["atlases"][0].pop("cross_platform_report")

    bad = json.loads(json.dumps(evidence))
    bad["atlases"][0]["slots"][0]["kind"] = "unqualified"
    blocked(lambda: recon.build_spec(bad, romfs, root), "unknown slot")
    bad["atlases"][0]["slots"][0] = {"kind": "guest_action", "guest_button": "a",
                                      "rect": [12, 12, 28, 28]}
    blocked(lambda: recon.build_spec(bad, romfs, root), "unbounded sprite")
    bad = json.loads(json.dumps(evidence))
    bad["atlases"][0]["slots"][1]["rect"] = [8, 8, 40, 40]
    blocked(lambda: recon.build_spec(bad, romfs, root), "overlapping sprites")
    bad = json.loads(json.dumps(evidence))
    bad["atlases"][0]["romfs_path"] = "../UI/buttons.png"
    blocked(lambda: recon.build_spec(bad, romfs, root), "path traversal")
    bad = json.loads(json.dumps(evidence))
    bad["atlases"][0]["original_sha256"] = "0" * 64
    blocked(lambda: recon.build_spec(bad, romfs, root), "source mismatch")
    bad = json.loads(json.dumps(evidence))
    bad["atlases"][0]["scene"] = "nintendo-badges"
    blocked(lambda: recon.build_spec(bad, romfs, root), "unknown context")
    bad = json.loads(json.dumps(evidence))
    bad["atlases"][0]["romfs_path"] = "UI/buttons.bntx"
    blocked(lambda: recon.build_spec(bad, romfs, root), "undecoded proprietary texture")

    target = root / "generated.json"
    recon.new_json(target, built)
    assert json.loads(target.read_text()) == built
    blocked(lambda: recon.new_json(target, built), "overwritten output")

print("PASS GLYPH RECONSTRUCTION: corpus merged, A=Cross, right=Circle, "
      "real Switch SHA/geometry and cross-platform proof gating")
print("Synthetic input only. No game asset converted; no PS5 scene qualified.")
