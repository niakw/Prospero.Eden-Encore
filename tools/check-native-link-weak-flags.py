#!/usr/bin/env python3
"""Guard native two-pass weak-symbol linker resolution without ignored -z flags."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
link = (root/"tools/link-headless-native.sh").read_text()
assert "-z nodynamic-undefined-weak" not in "\n".join(
    line for line in link.splitlines() if not line.lstrip().startswith("#")
)
for part in (
    'link_native "$weak_scan" "$weak_map"',
    'weak_flags+=("--defsym=${name}=0")',
    'link_native "$output" "$output.map" "${weak_flags[@]}"',
    'if "$nm_tool" -D --undefined-only "$output"',
    'Native link still contains unresolved weak imports:',
):
    assert part in link, f"missing weak-import contract: {part}"
subprocess.run(["bash","-n",str(root/"tools/link-headless-native.sh")],
               check=True,timeout=10)
print("PASS native weak symbol scan/resolution preserved; unsupported linker option removed")
