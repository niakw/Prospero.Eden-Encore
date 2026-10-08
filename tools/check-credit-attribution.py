#!/usr/bin/env python3
"""Keep named upstream contributors visible in both README and package legal notices."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
readme = (root / "README.md").read_text()
notices = (root / "THIRD_PARTY_NOTICES.md").read_text()
credit_section = readme.split("## Credits\n", 1)[1].split("## Community\n", 1)[0]
author_section = notices.split("## Identified upstream authors, maintainers and project teams\n", 1)[1].split("## Emulator and compression\n", 1)[0]
pattern = re.compile(r"^- \[([^\]\n]+)\]\((https://github\.com/[^\s)]+)\) — \*\*Authors / maintainers: (.*?)\*\* —", re.M)
entries = pattern.findall(credit_section)
assert len(entries) >= 28, f"lost upstream author attributions: {len(entries)}"
assert len({url for _name, url, _who in entries}) == len(entries), "duplicate repository credit"
for name, url, authors in entries:
    assert authors.strip(), (name, url)
    assert f"- [{name}]({url}) — {authors}." in author_section, f"legal author credit missing: {url}"
legal_count = author_section.count("](https://github.com/")
assert legal_count == len(entries), (legal_count, len(entries))
assert "Sean T. Barrett" in author_section and "Mitsunari Shigeo" in author_section
print(f"Named project authors and maintainer attributions: {len(entries)} README / legal entries PASS")
