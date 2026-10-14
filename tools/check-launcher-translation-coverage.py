#!/usr/bin/env python3
"""Report exact active translations, reject obsolete catalog entries.

All 29 current catalogs must have full active-key coverage. Recent non-primary
locale texts include provisional machine-assisted translations: coverage and
placeholder checks do NOT replace human review or on-console typography QA.
"""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(root / "tools/launcher/strings.py"))
marked = set(module["marked_text"]())
read_po = module["parse_po"]
catalogs = sorted((root / "headless/prosperoeden/ui/lang").glob("*.po"))
assert len(catalogs) == 29, f"catalog count changed: {len(catalogs)}"
# Resolution labels are dynamic constants, not tr("...") literals. Never
# permit them to disappear in non-primary languages after gettext extraction.
import re
settings = (root / "headless/settings_store.h").read_text()
m = re.search(r'kResolutionLabels\[\] = \{([^}]*)\}', settings, re.S)
assert m, "no resolution labels"
resolution_labels = re.findall(r'"([^"]+)"', m.group(1))
assert len(resolution_labels) == 9, resolution_labels
assert "2x (high memory)" in resolution_labels and "4x (extreme memory)" in resolution_labels
core_ui = {
    "Anti-aliasing", "ANTI-ALIASING", "Button mapping", "BUTTON MAPPING",
    "Quick settings", "QUICK SETTINGS", "Storage", "STORAGE",
    "Video preset", "VIDEO PRESET", "Game resolution", "GAME RESOLUTION",
    "TV output", "TV OUTPUT", "FSR sharpness", "FSR SHARPNESS",
    "Stick deadzone", "STICK DEADZONE",
    "Vibration strength", "VIBRATION STRENGTH", "Play", "Cancel", "Confirm",
    "Reset", "Ultra", "Recommended", "Minimum", "Home", "Clear cache",
    "Done", "Custom", "Controllers", "Quit", "Preset", "Open settings",
}
assert core_ui <= marked, "essential UI source markers disappeared"
total_missing = 0
for catalog in catalogs:
    translations = read_po(catalog)
    stale = set(translations) - marked - module["DYNAMIC_LIBRARY_GENRES"]
    missing = {key for key in marked if not translations.get(key)}
    missing_resolutions = [label for label in resolution_labels if not translations.get(label)]
    assert not missing_resolutions, f"{catalog.name}: untranslated display scale options {missing_resolutions}"
    core_missing = sorted(k for k in core_ui if not translations.get(k))
    assert not core_missing, f"{catalog.name}: missing translated core UI labels {core_missing}"
    if stale:
        raise AssertionError(f"{catalog.name}: {len(stale)} stale msgid entries, examples={sorted(stale)[:5]}")
    assert not missing, f"{catalog.name}: {len(missing)} untranslated strings"
    total_missing += len(missing)
    print(f"LOCALE_COVERAGE {catalog.stem} active={len(marked)} "
          f"translated={len(marked)-len(missing)} missing={len(missing)} stale=0")
print(f"LOCALE_COVERAGE_SUMMARY languages={len(catalogs)} active_texts={len(marked)} "
      f"missing_translations={total_missing} (all active translations present; human review outstanding)")
