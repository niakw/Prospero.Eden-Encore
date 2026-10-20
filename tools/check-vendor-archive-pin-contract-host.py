#!/usr/bin/env python3
"""Verify that a self-consistent but unpinned archive is rejected.

Extracts the current real assert_blob() implementation. Full source CI
independently checks the complete vendored archive set and airgap restore.
"""
from pathlib import Path
import tempfile
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"tools/check-vendored-deps.py").read_text()
DEPS=json.loads((ROOT/"tools/deps.json").read_text())["items"]
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
CMD="python3 -B tools/check-vendor-archive-pin-contract-host.py"
assert CMD in FAST and CMD in FULL
assert "python3 -B tools/check-vendored-deps.py" in FULL
assert "assert_blob(name,item.get('sha256'),item.get('sha512'))" in SOURCE

archives=[item for item in DEPS if item["kind"]=="archive"]
assert len(archives)==6
assert len([a for a in archives if "sha256" in a])==5
assert len([a for a in archives if "sha512" in a])==1
for item in archives:
    manifest=json.loads((ROOT/"vendor/objects"/item["name"]/"chunks.json").read_text())
    assert manifest["name"]==item["name"]
    if "sha256" in item:
        assert manifest["sha256"]==item["sha256"],item["name"]

start=SOURCE.index("def assert_blob(")
end=SOURCE.index("\nfor item in ITEMS:",start)
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix="encore-archive-pin-") as tmp:
    vault=Path(tmp)
    env={"V":vault,"hashlib":hashlib,"json":json,"digest":digest}
    exec(SOURCE[start:end],env)
    check=env["assert_blob"]
    folder=vault/"objects"/"fixture"
    folder.mkdir(parents=True)
    def configure(payload):
        (folder/"chunk").write_bytes(payload)
        (folder/"chunks.json").write_text(json.dumps({
            "name":"fixture","size":len(payload),
            "sha256":hashlib.sha256(payload).hexdigest(),
            "chunks":[{"file":"chunk","size":len(payload),
                       "sha256":hashlib.sha256(payload).hexdigest()}]}))
    original=b"sha-locked archive"
    expected256=hashlib.sha256(original).hexdigest()
    expected512=hashlib.sha512(original).hexdigest()
    configure(original)
    check("fixture",expected256,expected512)
    for sha256,sha512 in [("0"*64,expected512),(expected256,"0"*128)]:
        try:
            check("fixture",sha256,sha512)
        except AssertionError:
            pass
        else:
            raise AssertionError("incorrect independent pin accepted")
    configure(b"self-consistent but unpinned archive")
    try:
        check("fixture",expected256,expected512)
    except AssertionError:
        pass
    else:
        raise AssertionError("forged vault-local manifest accepted")
    configure(original)
    (folder/"chunk").write_bytes(b"corrupt")
    try:
        check("fixture",expected256,expected512)
    except AssertionError:
        pass
    else:
        raise AssertionError("corrupted chunk accepted")
print("ENCORE_VENDOR_ARCHIVE_PIN_PASS archives=6 SHA256=5 SHA512=1 forged_vault=rejected")
