#!/usr/bin/env python3
"""Prevent first-party build debris and dangling workflow script references.

Pinned source vaults and legal/media assets are deliberately left untouched.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
tracked = set(filter(None, subprocess.check_output(
    ["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")))
# Treat maintained vendor overlays as first-party-owned code. Leave immutable
# vendor/sources and vendor/objects unmodified (some source archives contain
# upstream test logs and binary fixtures by design).
owned = {path for path in tracked if not path.startswith("vendor/")}
maintained = {path for path in tracked if path.startswith("vendor/encore-active/")}
checked = owned | maintained
errors = []
junk_dir = {"__pycache__", "node_modules", ".pytest_cache", ".mypy_cache",
            ".ruff_cache", ".tox", ".nox", ".venv", ".idea", ".vscode",
            "CMakeFiles", "Testing", "coverage"}
junk_names = {".DS_Store", "Thumbs.db", "CMakeCache.txt", "cmake_install.cmake",
              "compile_commands.json", ".ninja_deps", ".ninja_log", ".coverage"}
junk_extensions = (".pyc", ".pyo", ".swp", ".swo", ".tmp", ".bak", ".orig",
                   ".rej", ".o", ".obj", ".log", ".gcda", ".gcno", ".profraw", ".profdata")
# The two former editable source-background paths carried the same Git blob.
# Keep one original for future design edits; package art uses encore-background.jpg.
if "assets/launch-background-source.png" in tracked:
    errors.append("redundant legacy background source reintroduced")
if "assets/background-source.png" not in tracked:
    errors.append("canonical editable background source missing")
for name in sorted(checked):
    path = Path(name)
    if (any(part in junk_dir for part in path.parts)
            or path.name in junk_names or path.name.startswith("._")
            or name.endswith(junk_extensions)):
        errors.append("tracked disposable artefact: " + name)
    if (path.name in {"prod.keys", "title.keys"}
            or path.suffix.lower() in {".nsp", ".xci", ".nsz", ".ncz", ".fpkg", ".pkg"}):
        errors.append("tracked console/private package material: " + name)

# Verify literal CI tool invocations. Avoid treating comments and arbitrary
# documentation links as mandatory run steps.
pattern = re.compile(r"\b(?:python3\s+(?:-B\s+)?|bash\s+)"
                     r"(tools/[A-Za-z0-9_./-]+\.(?:py|sh))")
checks = 0
workflows = sorted((ROOT / ".github/workflows").glob("*.yml"))
for workflow in workflows:
    source = workflow.read_text()
    if not re.search(r"(?m)^permissions:\s*$", source):
        errors.append("workflow without explicit permissions: " + workflow.name)
    for candidate in pattern.findall(source):
        checks += 1
        if candidate not in tracked:
            errors.append(f"{workflow.name}: missing tracked tool {candidate}")

if errors:
    raise SystemExit("\n".join(errors))
print(f"ENCORE_REPO_HYGIENE_PASS first_party={len(owned)} maintained_vendor={len(maintained)} workflows_checked={len(workflows)} tool_refs={checks} immutable_vault_untouched=1")
