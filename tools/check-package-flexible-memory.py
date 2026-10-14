#!/usr/bin/env python3
"""Guard the packaged native memory declaration against upstream drift.

This is a metadata contract, not a hardware memory allocation test.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
package = (root / "tools/package-headless-native.sh").read_text()
template = json.loads((root / "vendor/sources/boilerplate/sce_sys/param.json").read_text())
assert "kernel" not in template, "Requalify the template if its metadata changes"
assignment = "value.setdefault('kernel', {})['flexibleMemorySize'] = 335544320"
assert package.count(assignment) == 1
assert "value['attribute3'] = int(value['attribute3']) | 0x80040" in package
assert package.index(assignment) < package.index("(app / 'sce_sys/param.json').write_text")
value = json.loads(json.dumps(template))
exec(assignment, {"value": value})
assert value["kernel"]["flexibleMemorySize"] == 320 * 1024 * 1024
assert value["attribute3"] == template["attribute3"]
assert value["titleId"] == template["titleId"]
print("PACKAGE_FLEXIBLE_MEMORY_CONTRACT_PASS configured=320MiB source=upstream-native-metadata")
