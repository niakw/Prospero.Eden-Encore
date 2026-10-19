#!/usr/bin/env python3
"""Static ownership checks for specialized application runtime interfaces.

This test neither edits launcher code nor claims native console validation.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADLESS = ROOT / "headless"
owners = [
  {
    "id": "U58",
    "name": "controller_applet.h",
    "symbols": [
      "ControllerStyle(",
      "class PadControllerApplet final"
    ],
    "consumer": "headless/main.cpp"
  },
  {
    "id": "U59",
    "name": "dev_vulkan.h",
    "symbols": [
      "inline bool static_vertex_input = true;",
      "inline void ResetForTitle()"
    ],
    "consumer": "headless/main.cpp"
  },
  {
    "id": "U60",
    "name": "error_applet.h",
    "symbols": [
      "class LoggedErrorApplet final",
      "void ShowError(Result error,"
    ],
    "consumer": "headless/main.cpp"
  },
  {
    "id": "U61",
    "name": "glyph_overrides_runtime.h",
    "symbols": [
      "inline bool ParseCatalogue(",
      "kMaxGraphicPackBytes"
    ],
    "consumer": "headless/main.cpp"
  },
  {
    "id": "U62",
    "name": "mods.h",
    "symbols": [
      "inline std::vector<Mod> List(",
      "inline std::string Summary("
    ],
    "consumer": "headless/main.cpp"
  },
  {
    "id": "U63",
    "name": "ryujinx_saves.h",
    "symbols": [
      "inline std::vector<Save> FindSaves(",
      "inline std::vector<Save> FindFolderSaves("
    ],
    "consumer": "headless/metadata_bridge.cpp"
  },
  {
    "id": "U64",
    "name": "sdk_audit.h",
    "symbols": [
      "inline void AuditSdkThread(",
      "inline void AuditSdk()"
    ],
    "consumer": "headless/main.cpp"
  },
  {
    "id": "U65",
    "name": "watch.h",
    "symbols": [
      "inline bool Parse(",
      "inline bool Hit("
    ],
    "consumer": "headless/main.cpp"
  }
]

assert len(owners) == 8
for owner in owners:
    header = HEADLESS / owner["name"]
    body = header.read_text(encoding="utf-8")
    for symbol in owner["symbols"]:
        assert symbol in body, (owner["id"], "missing function", symbol)
    include = '#include "' + owner["name"] + '"'
    assert include in (ROOT / owner["consumer"]).read_text(encoding="utf-8"), (
        "source consumer changed", owner["name"], owner["consumer"])
assert "keep_connected{}" in (HEADLESS/"controller_applet.h").read_text()
assert "ResetForTitle() noexcept" in (HEADLESS/"dev_vulkan.h").read_text()
assert "FinishedCallback finished" in (HEADLESS/"error_applet.h").read_text()
assert "kMaxCatalogBytes" in (HEADLESS/"glyph_overrides_runtime.h").read_text()
assert "TitleFolder(" in (HEADLESS/"mods.h").read_text()
assert "header = 12, entry = 0x8C;" in (HEADLESS/"ryujinx_saves.h").read_text()
assert "std::thread worker(" in (HEADLESS/"sdk_audit.h").read_text()
assert "snapshot_taken{false}" in (HEADLESS/"watch.h").read_text()
print("ENCORE_HEADLESS_SPECIALIZED_OWNERS_PASS headers=8 direct_consumers=8 native_runtime_unqualified=1")
