#!/usr/bin/env python3
from pathlib import Path
import shutil
import subprocess
root = Path(__file__).resolve().parents[1]
preset = (root / "headless/prosperoeden/pe/ui/video_presets.hpp").read_text()
settings = (root / "headless/prosperoeden/pe/ui/settings.cpp").read_text()
library = (root / "headless/prosperoeden/pe/ui/library.cpp").read_text()
store = (root / "headless/settings_store.h").read_text()
generated = (root / "headless/encore_overrides_generated.h").read_text()

compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "No host C++ compiler available for generated-profile syntax gate"
syntax = subprocess.run(
    [compiler, "-std=c++20", "-fsyntax-only", "-x", "c++", "-"],
    input=generated, text=True, capture_output=True, check=False,
)
assert syntax.returncode == 0, "encore_overrides_generated.h syntax error:\n" + syntax.stderr

assert "kAuthoredProfileCount = 4" in generated
assert "kCustomProfile = 4" in generated
for profile in (
    "{1, 0, 3, 0, 50, 0, 0, true}",      # Minimum
    "{1, 1, 4, 0, 50, 1, 0, true}",      # Recommended
    "{1, 2, 5, 2, 50, 1, 0, true}",      # High
    "{1, 2, 6, 0, 50, 0, 0, true}",      # Ultra
):
    assert profile in generated, profile
assert "0x0100C49025D3E000ULL" in generated
assert "ProfileForTitle" in generated
assert "kCustomVideoProfile = Eden::EncoreOverrides::kCustomProfile" in preset
assert "VideoPresetForTitle" in preset
assert "ApplyVideoPreset(prefs_, preset);" in settings
assert "ApplyVideoPreset(next, preset, game.title_id);" in library
for reset in ("next.renderer = -1;", "next.output = -1;", "next.resolution = -1;", "next.filter = -1;",
              "next.fsr_sharpness = -1;", "next.anti_aliasing = -1;", "next.refresh = -1;"):
    assert reset in library, reset
assert "CycleVideoPreset(prefs_.performance_profile, step)" in settings
assert settings.count("RefreshVideoProfile(prefs_)") >= 7
assert library.count("RefreshVideoProfile(next, prefs_, game.title_id)") >= 7
assert '"minimum", "recommended", "high", "ultra", "custom"' in store
assert '"Minimum", "Recommended", "High", "Ultra", "Custom"' in store
assert "Smooth" not in settings
assert "Smooth" not in library
print("Video presets: 4 authored tiers + Custom, title-aware encore-overrides snapshot PASS")
