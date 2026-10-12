#!/usr/bin/env python3
"""Print the current documented Eden Encore revision for compiler injection."""
from pathlib import Path
import re
import sys

source = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parents[2] / "MEMORY.md"
revisions = [int(m.group(1)) for m in re.finditer(
    r"^###\s+\d{4}-\d{2}-\d{2}\s+R(\d{2,6})(?=\s|$)", source.read_text(encoding="utf-8"), re.M)]
if not revisions:
    raise SystemExit(f"No documented R revision in {source}")
print(f"R{max(revisions)}")
