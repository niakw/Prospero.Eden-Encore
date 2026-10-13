#!/usr/bin/env python3
"""Report exact active translations, reject obsolete catalog entries.

Historical 27 non-French catalogs are partial and must NOT be filled with
fake English msgstr entries merely to silence warnings.
"""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(root / "tools/launcher/strings.py"))
marked = set(module["marked_text"]())
read_po = module["parse_po"]
catalogs = sorted((root / "headless/prosperoeden/ui/lang").glob("*.po"))
assert len(catalogs) == 29, f"catalog count changed: {len(catalogs)}"
total_missing = 0
for catalog in catalogs:
    translations = read_po(catalog)
    stale = set(translations) - marked
    missing = {key for key in marked if not translations.get(key)}
    if stale:
        raise AssertionError(f"{catalog.name}: {len(stale)} stale msgid entries, examples={sorted(stale)[:5]}")
    if catalog.stem in {"fr-FR", "fr-CA"}:
        assert not missing, f"{catalog.name} maintained language has {len(missing)} missing"
    elif len(missing) > 152:
        raise AssertionError(f"{catalog.name}: translation coverage regressed; {len(missing)} untranslated")
    total_missing += len(missing)
    print(f"LOCALE_COVERAGE {catalog.stem} active={len(marked)} "
          f"translated={len(marked)-len(missing)} missing={len(missing)} stale=0")
print(f"LOCALE_COVERAGE_SUMMARY languages={len(catalogs)} active_texts={len(marked)} "
      f"missing_translations={total_missing} (non-primary catalogs remain incomplete)")
