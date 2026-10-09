#!/usr/bin/env python3
"""Synthetic UnityPy API fixture. Do not run under the current no-run gate.

Mocks Unity objects and metadata only; no Nintendo/Unity game assets.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eden_unity_metadata", ROOT / "tools/ps-glyph-unity-inventory.py")
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.sprite_rect({"x": 12, "y": 3, "width": 24, "height": 24}) == [12., 3., 24., 24.]
assert m.sprite_rect({"x": 1, "y": 1, "width": -2, "height": 4}) is None
assert m.sprite_rect({"x": float("nan"), "y": 0, "width": 1, "height": 1}) is None
assert m.safe_string("Cross\x1b[31m") == "Cross[31m"

class TextureObject:
    type = types.SimpleNamespace(name="Texture2D")
    path_id = 17
    def peek_name(self):
        return "controller_buttons_ps5"
    def parse_as_object(self):
        return types.SimpleNamespace(m_Name="controller_buttons_ps5",
                                     m_Width=128, m_Height=256)

class SpriteObject:
    type = types.SimpleNamespace(name="Sprite")
    path_id = 18
    def peek_name(self):
        return "controller_cross_ps5"
    def parse_as_object(self):
        return types.SimpleNamespace(
            m_Name="controller_cross_ps5",
            m_Rect=types.SimpleNamespace(x=0, y=0, width=32, height=32),
            m_RD=types.SimpleNamespace(
                textureRect=types.SimpleNamespace(x=64, y=96, width=32, height=32)))

class MiscObject:
    type = types.SimpleNamespace(name="Texture2D")
    path_id = 19
    def peek_name(self):
        return "unrelated_map_layer"
    def parse_as_object(self):
        raise AssertionError("unrelated asset should not be fully parsed")

fake_unitypy = types.ModuleType("UnityPy")
fake_unitypy.load = lambda _: types.SimpleNamespace(
    objects=[TextureObject(), SpriteObject(), MiscObject()])
prior = sys.modules.get("UnityPy")
sys.modules["UnityPy"] = fake_unitypy
try:
    with tempfile.TemporaryDirectory(prefix="eden-unity-ui-metadata-") as tmp:
        path = Path(tmp) / "resources.assets"
        path.write_bytes(b"synthetic-unity-asset-index")
        result = m.inspect(path, "Switch")
        assert result["object_count_seen"] == 3
        assert result["reported_texture_or_sprite_objects"] == 3
        assert result["objects"][0]["texture_dimensions"] == [128, 256]
        assert result["objects"][1]["serialized_sprite_rect"] == [0., 0., 32., 32.]
        assert result["objects"][1]["serialized_texture_rect"] == [64., 96., 32., 32.]
        assert result["objects"][1]["sprite_button_identity_verified"] is False
        assert result["objects"][2]["texture_dimensions"] is None
finally:
    if prior is None:
        sys.modules.pop("UnityPy", None)
    else:
        sys.modules["UnityPy"] = prior

print("HOST FIXTURE PASS: read-only Unity Texture2D metadata and Sprite texture rectangles")
print("Original Switch Unity assets, coordinate orientation and PS5 gameplay NOT verified")
