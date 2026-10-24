#!/usr/bin/env python3
"""Replayed Eden native build-cache source install with immutable pin safety.

A scratch cache may contain generated older code from a previous build.
Never loosen manifest source hashes or overwrite arbitrary user checkouts.
This test runs the real installer against a tiny owned source-cache fixture.
"""
from pathlib import Path
import importlib.util
import tempfile

root=Path(__file__).resolve().parents[1]
script=root/"tools/install-vendored-eden-backports.py"
module=importlib.util.spec_from_file_location("encore_vendored_cache",script)
assert module and module.loader
app=importlib.util.module_from_spec(module)
module.loader.exec_module(app)
assert "--repair-owned-cache" in script.read_text()
assert "tools/install-vendored-eden-backports.py --repair-owned-cache" in (
    root/"tools/prepare-build.sh").read_text()
rel="src/video_core/texture_cache/texture_cache.h"
added="src/core/added.cpp"
with tempfile.TemporaryDirectory(prefix="eden-owned-cache-replay-") as tmp:
    here=Path(tmp)
    src=here/"immutable"
    active=here/"reviewed"
    cache=here/"ps5-eden-headless.fixture"
    native=cache/"source"
    other=here/"unowned"/"source"
    cache.mkdir()
    (cache/"owner").write_text(str(root.resolve())+"\n")
    for place in (src,active,native,other):
        place.mkdir(parents=True,exist_ok=True)
    old=b"immutable pinned source bytes"
    approved=b"reviewed shipping patched bytes"
    obsolete=b"prior generated source from cached build"
    new=b"new source checked into the reviewed overlay"
    for folder,relpath,content in (
        (src,rel,old),(active,rel,approved),(active,added,new),
        (native,rel,obsolete),(other,rel,obsolete)):
        target=folder/relpath
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
    for location in (native,other):
        (location/"GIT-COMMIT").write_text(app.PIN+"\n")
    manifest={
        "entries":{
            rel:{"upstream":app.sha(old),"active":app.sha(approved)},
            added:{"upstream":None,"active":app.sha(new)},
        },
        "shipping_receipts":{".encore-backport-fixture.sha256":"fixture"},
    }
    app.ORIGINAL=src
    app.ACTIVE=active
    app.verify=lambda:manifest
    assert app.is_owned_cached_source(native)
    assert not app.is_owned_cached_source(other)
    # Strict default MUST refuse unknown cached modifications.
    try:
        app.install(native)
    except RuntimeError as exc:
        assert "Unknown previous source modifications" in str(exc)
    else:
        raise AssertionError("Unrecognized cache content was silently accepted")
    assert (native/rel).read_bytes()==obsolete
    try:
        app.install(other,repair_owned_cache=True)
    except RuntimeError as exc:
        assert "owner-stamped" in str(exc)
    else:
        raise AssertionError("Unowned source was changed")
    assert (other/rel).read_bytes()==obsolete
    app.install(native,repair_owned_cache=True)
    assert (native/rel).read_bytes()==approved
    assert (native/added).read_bytes()==new
    backup=cache/".eden-stale-overlay-backup"/(rel+"."+app.sha(obsolete)[:16])
    assert backup.read_bytes()==obsolete
    assert (src/rel).read_bytes()==old and (active/rel).read_bytes()==approved
    # Repeated make prepare must be idempotent, not create new backups.
    app.install(native,repair_owned_cache=True)
    assert len(list((cache/".eden-stale-overlay-backup").rglob("*.h.*")))==1
    # Reject a symlinked target inside an authorized scratch cache.
    (native/rel).unlink()
    (native/rel).symlink_to(other/rel)
    try:
        app.install(native,repair_owned_cache=True)
    except RuntimeError as exc:
        assert "Symlinked" in str(exc)
    else:
        raise AssertionError("Symlinked cached code accepted")
    assert (other/rel).read_bytes()==obsolete
    (native/rel).unlink()
    (native/rel).write_bytes(approved)
    # Refuse a foreign pin even inside an otherwise authorized cache.
    (native/"GIT-COMMIT").write_text("wrong revision\n")
    try:
        app.install(native,repair_owned_cache=True)
    except RuntimeError as exc:
        assert "wrong Eden source version" in str(exc)
    else:
        raise AssertionError("Foreign source version accepted")
    # Check the original has not been changed by the rebase.
    assert (src/rel).read_bytes()==old
    # A stale backup with different bytes may NEVER authorize replacement.
    (native/"GIT-COMMIT").write_text(app.PIN+"\n")
    bad_backup = cache/".eden-stale-overlay-backup"/(rel+"."+app.sha(obsolete)[:16])
    bad_backup.write_bytes(b"corrupted saved copy")
    (native/rel).write_bytes(obsolete)
    try:
        app.install(native,repair_owned_cache=True)
    except RuntimeError as exc:
        assert "Stale backup hash mismatch" in str(exc)
    else:
        raise AssertionError("Corrupted backup accepted as replay authorization")
    assert (native/rel).read_bytes()==obsolete
    bad_backup.write_bytes(obsolete)
print("EDEN_VENDORED_CACHE_REBASE_HOST_PASS pinned=1 owned_only=1 backup=1"
      " idempotent=1 symlink_rejected=1 wrong_pin_rejected=1")
