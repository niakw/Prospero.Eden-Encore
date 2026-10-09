#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail before expensive PS5 setup if any in-tree Python source is unparseable.

Python's ast.parse compiles no C++, imports no project modules, executes no
scripts and writes no pyc files. This protects template/generator scripts too:
a C++ // comment outside a triple-quoted replacement broke Vulkan generation.
"""
from __future__ import annotations

import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sources = sorted(
    set((root / "tools").rglob("*.py")) | set((root / "headless").rglob("*.py"))
)
count = 0
for path in sources:
    # No dependencies, cache or hidden directories; only authored repo source.
    if any(part.startswith(".") for part in path.relative_to(root).parts):
        continue
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(root)))
    except (SyntaxError, UnicodeError) as error:
        raise SystemExit(f"Python syntax invalid in {path.relative_to(root)}: {error}") from error
    count += 1
assert count > 0, "source Python inventory is empty"
print(f"PYTHON_SOURCE_SYNTAX_PASS files={count}")
