#!/usr/bin/env python3
"""Guard against a partial pinned native bootstrap being mistaken for a complete one."""
from pathlib import Path
import json
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from deps import missing_setup_outputs

items = json.loads((ROOT / "tools/deps.json").read_text())["items"]
boilerplate = next(item for item in items if item["name"] == "boilerplate")
expected = {
    ".deps/native/ps5-payload-sdk/bin/prospero-clang",
    ".deps/native/zlib/root/usr/lib/libz.a",
    ".deps/native/zlib/root/usr/include/zlib.h",
    ".deps/native/zlib/root/.source-version",
}
declared = {boilerplate["setup_creates"], *boilerplate["setup_requires"]}
assert declared == expected
assert boilerplate["setup_version_stamps"] == {
    ".deps/native/zlib/root/.source-version": "1.3.2"
}
assert boilerplate["setup"] == ["bash", "tools/setup-native-dependencies.sh"]
for rel in expected:
    value = Path(rel)
    assert not value.is_absolute() and ".." not in value.parts, rel

with tempfile.TemporaryDirectory(prefix="encore-native-bootstrap-") as temp:
    root = Path(temp)
    for rel in expected:
        file = root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("1.3.2" if file.name == ".source-version" else "fixture")
    assert missing_setup_outputs(boilerplate, root) == []
    for removed in sorted(expected):
        file = root / removed
        content = file.read_bytes()
        file.unlink()
        assert missing_setup_outputs(boilerplate, root) == [removed], removed
        file.write_bytes(content)
    stamp = root / ".deps/native/zlib/root/.source-version"
    stamp.write_text("0.0.0")
    assert missing_setup_outputs(boilerplate, root) == [".deps/native/zlib/root/.source-version"]
    stamp.write_text("1.3.2")
    assert missing_setup_outputs(boilerplate, root) == []

build = (ROOT / "tools/build-native-tool.sh").read_text()
assert '"$zlib/usr/lib/libz.a"' in build
assert '"$zlib/usr/include/zlib.h"' in build
source = (ROOT / "tools/deps.py").read_text()
assert "if 'setup' in item and missing_setup_outputs(item, path):" in source
assert "missing = missing_setup_outputs(item, path)" in source
assert "for missing in missing_setup_outputs(item, location(item)):" in source
print("ENCORE_NATIVE_BOOTSTRAP_CONTRACT_PASS sdk=1 zlib_archive=1 zlib_header=1 zlib_stamp=1")
