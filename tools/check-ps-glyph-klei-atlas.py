#!/usr/bin/env python3
"""Synthetic Klei Atlas XML UV fixture: no Nintendo game resources used.

Added for a future host-only validation phase; not executed here under the
project's current CI/build/no-run restriction.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eden_klei_glyph_xml", ROOT / "tools/ps-glyph-klei-atlas.py")
assert spec and spec.loader
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def rejects(path: Path, raw: str) -> None:
    path.write_text(raw, "utf-8")
    try:
        parser.read(path, 256, 128)
    except ValueError:
        return
    raise AssertionError("invalid atlas accepted")


with tempfile.TemporaryDirectory(prefix="eden-klei-glyph-uv-fixture-") as folder:
    path = Path(folder) / "nx_controllers.xml"
    path.write_text(
        '<Atlas><Texture filename="nx_controllers.tex" />'
        '<Elements><Element name="button_a.tex" u1="0.25" u2="0.375" '
        'v1="0.5" v2="0.75" /><Element name="button_b.tex" '
        'u1="0.375" u2="0.5" v1="0" v2="0.25" /></Elements></Atlas>',
        encoding="utf-8")
    found = parser.read(path, 256, 128)
    assert found["referenced_texture_file"] == "nx_controllers.tex"
    assert found["sprite_element_count"] == 2
    assert found["elements"][0]["normalized_uv"] == [.25, .5, .375, .75]
    assert found["elements"][0]["candidate_bottom_origin_xywh"] == [64, 64, 32, 32]
    assert found["elements"][0]["candidate_top_origin_xywh"] == [64, 32, 32, 32]
    assert found["elements"][0]["observed_sprite_button_identity"] is None
    assert found["game_title_update_verified"] is False

    rejects(path, '<!DOCTYPE Atlas [ <!ENTITY x "dummy"> ]><Atlas/>')
    rejects(path, '<Atlas><Texture filename="../outside.tex"/>'
                  '<Elements></Elements></Atlas>')
    rejects(path, '<Atlas><Texture filename="C:evil.tex"/>'
                  '<Elements></Elements></Atlas>')
    rejects(path, '<Atlas><Texture filename="icon.png"/>'
                  '<Elements></Elements></Atlas>')
    rejects(path, '<Atlas><Texture filename="one.tex"/>'
                  '<Elements><Element name="bad" u1="0.5" u2="0.4" '
                  'v1="0" v2="1"/></Elements></Atlas>')
    rejects(path, '<Atlas><Texture filename="one.tex"/>'
                  '<Elements><Element name="A" u1="0" u2="0.5" '
                  'v1="0" v2="0.5"/>'
                  '<Element name="a" u1="0" u2="0.5" '
                  'v1="0" v2="0.5"/></Elements></Atlas>')
    rejects(path, '<Atlas><Texture filename="one.tex"/>'
                  '<Elements><Element name="bad" u1="0" u2="nan" '
                  'v1="0" v2="1"/></Elements></Atlas>')
    rejects(path, '<Atlas><Texture filename="one.tex"/>'
                  '<Elements><Element name="bad" u1="0" u2="1" '
                  'v1="0" v2="3"/></Elements></Atlas>')

print("HOST FIXTURE PASS: Klei normalized atlas UV, top/bottom-origin XYWH and reject guards")
print("No game .tex decoding, sprite semantics, original version or PS5 rendering proof")
