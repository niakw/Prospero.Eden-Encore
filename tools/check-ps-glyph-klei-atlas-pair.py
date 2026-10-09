#!/usr/bin/env python3
"""Synthetic Klei PS/Switch XML metadata pair regression; no game assets.

Not executed during no-run/no-build gate.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def load(name: str, file: str):
    spec=importlib.util.spec_from_file_location(name,ROOT/"tools"/file)
    assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


atlas=load("eden_klei_atlas_fixture","ps-glyph-klei-atlas.py")
pair=load("eden_klei_pair_fixture","ps-glyph-klei-atlas-pair.py")
with tempfile.TemporaryDirectory(prefix="eden-klei-ps-nx-") as tmp:
    root=Path(tmp)
    ps=root/"ps4_controllers.xml"
    nx=root/"nx_controllers.xml"
    ps.write_text(
        '<Atlas><Texture filename="ps4_controllers.tex"/><Elements>'
        '<Element name="controls_image" u1="0.25" v1="0.5" u2="0.5" v2="0.75"/>'
        '<Element name="ps_only" u1="0" v1="0" u2="0.25" v2="0.25"/>'
        '</Elements></Atlas>',encoding="utf-8")
    nx.write_text(
        '<Atlas><Texture filename="nx_controllers.tex"/><Elements>'
        '<Element name="controls_image" u1="0.5" v1="0" u2="0.75" v2="0.25"/>'
        '<Element name="nx_only" u1="0" v1="0" u2="0.25" v2="0.25"/>'
        '</Elements></Atlas>',encoding="utf-8")
    ps_report=atlas.read(ps,256,128)
    nx_report=atlas.read(nx,256,128)
    compared=pair.compare(ps_report,nx_report)
    assert compared["shared_sprite_names"] == 1
    assert compared["only_in_ps_name_count"] == 1
    assert compared["only_in_switch_name_count"] == 1
    assert compared["shared"][0]["shared_sprite_name"] == "controls_image"
    assert compared["shared"][0]["same_normalized_uv"] is False
    assert compared["shared"][0]["ps_candidate_top_origin_xywh"] == [64,32,64,32]
    assert compared["shared"][0]["switch_candidate_top_origin_xywh"] == [128,96,64,32]
    assert compared["shared"][0]["glyph_identity_and_console_proof"] is False
    assert compared["activated_glyph_overrides"] == 0

print("HOST FIXTURE PASS: shared Klei sprite names with distinct PS/Switch UVs")
print("No verified .tex pixels, Nintendo game updates or PS5 gameplay")
