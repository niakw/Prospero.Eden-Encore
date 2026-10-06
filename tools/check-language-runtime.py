#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Release guard for PS5 locale -> launcher catalog selection and live language switching."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
system = (root / 'third_party/ps5_system_language.hpp').read_text()
settings = (root / 'headless/settings_store.h').read_text()
frontend = (root / 'headless/prosperoeden/frontend.cpp').read_text()
browse = (root / 'headless/prosperoeden/pe/ui/browse.cpp').read_text()
services = (root / 'headless/prosperoeden/eden_services.cpp').read_text()
launcher = (root / 'headless/prosperoeden/pe/ui/launcher.hpp').read_text()
lang_dir = root / 'headless/prosperoeden/ui/lang'

quoted = lambda body: re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', body)

def array(name: str, text: str):
    match = re.search(rf'{re.escape(name)}[^=]*=\s*\{{(.*?)\}};', text, re.S)
    assert match, f'missing {name}'
    return quoted(match.group(1))

system_tags = array('kLanguageTags', system)
assert len(system_tags) == 31, len(system_tags)
assert system_tags[2] == 'fr-FR', f'PS5 French must map to fr-FR, got {system_tags[2]!r}'

keys = array('kLanguageKeys', settings)
catalogs = array('kLanguageCatalogTags', settings)
assert len(keys) == len(catalogs) >= 18
assert keys[2] == 'fr' and catalogs[2] == 'fr-FR', (keys[2], catalogs[2])

po = sorted(lang_dir.glob('*.po'))
assert len(po) == 29, f'expected 29 launcher catalogs, got {len(po)}'
fr = lang_dir / 'fr-FR.po'
assert fr.is_file() and fr.stat().st_size > 1000, 'complete fr-FR catalog missing'

# A release must never let an old dev override force English. The only language.txt read must live
# inside the EDEN_DEV_PROFILE block.
needle = 'Eden::AppFile(\"language.txt\")'
pos = frontend.find(needle)
assert pos >= 0, 'development language override missing'
ifdef = frontend.rfind('#ifdef EDEN_DEV_PROFILE', 0, pos)
endif = frontend.find('#endif', pos)
assert ifdef >= 0 and endif > pos, 'language.txt is not development-only'
assert 'pe::catalog().clear();' in frontend, 'catalog is not cleared before each launcher language load'
assert 'launcher.restart_requested()' in frontend, 'frontend does not honor launcher language restart'
assert 'EDEN_LANGUAGE launcher-restart=1' in frontend, 'language restart is not diagnosable'
assert 'Requested launcher catalog unavailable:' in frontend, 'missing catalog is not reported'
assert 'restart_requested_ = true;' in browse, 'Settings > Language does not request live launcher reload'
assert 'bool restart_requested() const' in launcher, 'launcher restart contract missing'
assert 'static const std::vector<std::string> labels = Labels' not in services, 'translated labels survive a launcher restart'
assert 'return language_labels_;' in services and 'return resolution_labels_;' in services, 'translated labels are not per-service caches'

print('Language runtime contract PASS (PS5 French -> fr-FR, release override safe, live reload, 29 catalogs)')
