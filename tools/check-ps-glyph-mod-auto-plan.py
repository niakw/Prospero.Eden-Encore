#!/usr/bin/env python3
"""Host synthetic mod-extracted Switch geometry -> reviewed glyph plans."""
from __future__ import annotations

import importlib.util
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("eden_mod_auto_plan",
                                           TOOLS / "ps-glyph-mod-auto-plan.py")
assert sp and sp.loader
auto = importlib.util.module_from_spec(sp)
sp.loader.exec_module(auto)


def refuse(func, name):
    try:
        func()
    except auto.InvalidPlan:
        return
    raise AssertionError(f"accepted unsafe game glyph plan: {name}")


report = {
    "schema": 1, "matched_archives": [{
        "romfs_path": "Layout/Controller.sblarc",
        "original_file_sha256": "a" * 64,
        "positions": {
            "textures": [
                {"member": "__Combined.bntx", "texture": "control_a_prompt",
                 "scene": "world_interaction", "original_bntx_sha256": "b" * 64,
                 "detected_original_switch_slots": [
                     {"rect_xywh": [1, 2, 20, 20]},
                 ]},
                {"member": "__Combined.bntx", "texture": "controller_help_atlas",
                 "scene": "controller_diagram", "original_bntx_sha256": "b" * 64,
                 "detected_original_switch_slots": [
                     {"rect_xywh": [30, 2, 20, 20]},
                     {"rect_xywh": [53, 2, 20, 20]},
                 ]},
            ]
        },
    }],
}
preview = auto.make(report, "01007EF00011E000", "1.6.0")
assert len(preview["plans"]) == 2
first = preview["plans"][0]
assert first["manifest"]["slots"][0]["rect"] == [1, 2, 20, 20]
assert first["manifest"]["slots"][0]["kind"] == "guest_action"
assert first["manifest"]["slots"][0]["guest_button"] == "a"
assert not first["manifest"]["slots"][0]["reviewed"]
assert not first["ready_for_assembler_after_review"]
other = preview["plans"][1]
assert len(other["manifest"]["slots"]) == 2
assert all(item["kind"] is None for item in other["manifest"]["slots"])
assert preview["approved_operation_count"] == 0

bindings = {
    "Layout/Controller.sblarc|__Combined.bntx|control_a_prompt|0":
        {"reviewed": True, "kind": "guest_action", "guest_button": "a"},
    "Layout/Controller.sblarc|__Combined.bntx|controller_help_atlas|0":
        {"reviewed": True, "kind": "controller_position", "face": "right"},
    "Layout/Controller.sblarc|__Combined.bntx|controller_help_atlas|1":
        {"reviewed": True, "kind": "controller_position", "face": "bottom"},
}
checked = auto.make(report, "01007EF00011E000", "1.6.0", bindings)
assert checked["approved_operation_count"] == 2
assert checked["plans"][0]["ready_for_assembler_after_review"]
assert checked["plans"][1]["ready_for_assembler_after_review"]
assert checked["plans"][1]["manifest"]["slots"][0]["face"] == "right"
assert checked["plans"][1]["manifest"]["slots"][1]["face"] == "bottom"
assembly = auto.reviewed_manifest(checked, 0)
assert set(assembly) == {"schema", "title_id", "update_version", "profile",
                         "original_archive_sha256", "original_member_sha256",
                         "member", "texture", "scene", "variant", "slots"}
assert assembly["slots"] == [{"kind": "guest_action", "guest_button": "a",
                              "rect": [1, 2, 20, 20]}]
assert auto.reviewed_manifest(checked, 1)["slots"] == [
    {"kind": "controller_position", "face": "right", "rect": [30, 2, 20, 20]},
    {"kind": "controller_position", "face": "bottom", "rect": [53, 2, 20, 20]},
]
refuse(lambda: auto.reviewed_manifest(preview, 0),
       "guessed A label exported as already approved glyph")
refuse(lambda: auto.reviewed_manifest(checked, 9),
       "nonexistent sprite plan selected for output")
refuse(lambda: auto.make(report, "01007EF00011E000", "1.6.0",
                         {"romfs/WRONG/unknown/1": {
                             "reviewed": True, "kind": "guest_action",
                             "guest_button": "a"}}),
       "silently ignored a review binding that matches no mod-provided sprite")

# The original mod's input labels are not blindly translated into
# rectangle semantics of a PlayStation-shaped controller diagram.
bad = dict(bindings)
bad["Layout/Controller.sblarc|__Combined.bntx|control_a_prompt|0"] = {
    "reviewed": False, "kind": "guest_action", "guest_button": "a"}
refuse(lambda: auto.make(report, "01007EF00011E000", "1.6.0", bad),
       "action semantics claimed approved without review")
bad = dict(bindings)
bad["Layout/Controller.sblarc|__Combined.bntx|controller_help_atlas|1"] = {
    "reviewed": True, "kind": "controller_position", "face": "east"}
refuse(lambda: auto.make(report, "01007EF00011E000", "1.6.0", bad),
       "unknown physical face position")
refuse(lambda: auto.make(report, "BAD", "1.6.0", bindings),
       "invalid Switch game identity")
assert auto.semantic_hint("ButtonA", 1) is None
assert auto.semantic_hint("button_a", 2) is None
assert auto.semantic_hint("abc_a_b_prompt", 1) is None
assert auto.semantic_hint("button_a", 1) == {
    "kind": "guest_action", "guest_button": "a"}

print("PASS: real-mod coordinate evidence reused without manual XYWH transcription")
print("PASS: known single-action asset labels suggested, controller spatial art reviewed separately")
