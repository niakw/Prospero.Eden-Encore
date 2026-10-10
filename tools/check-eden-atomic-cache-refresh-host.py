#!/usr/bin/env python3
"""Run production pinned-source cache repair with temporary synthetic snapshots."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
script = root / "tools/refresh-eden-atomic-source-cache.py"
spec = importlib.util.spec_from_file_location("atomic_cache", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
prep = (root / "tools/prepare-build.sh").read_text()
assert 'python3 -B "$root/tools/refresh-eden-atomic-source-cache.py" "$scratch"' in prep
assert prep.index("refresh-eden-atomic-source-cache.py") < prep.index(
    'if [[ ! -f $eden/CMakeLists.txt ]]; then')
def invoke(scratch, archive, owner, expect_success=True):
    cp = subprocess.run([sys.executable, "-B", str(script), str(scratch),
                         str(archive), str(owner)], capture_output=True, text=True, timeout=30)
    assert (cp.returncode == 0) == expect_success, (cp.stderr, cp.stdout)
    return cp

with tempfile.TemporaryDirectory(prefix="eden-atomic-cache-regression-") as temp:
    temp = Path(temp)
    owner = temp / "repo"
    owner.mkdir()
    tar_input = temp / "pin" / "eden"
    (tar_input / "src/core").mkdir(parents=True)
    (tar_input / "CMakeLists.txt").write_text("project(EdenPin)\n")
    (tar_input / "src/core/device_memory_manager.h").write_text(
        "struct DeviceMemoryManager { int pristine; };\n")
    archive = temp / "pin.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tar_input, arcname="eden")
    scratch = temp / "ps5-eden-headless.fixture"
    scratch.mkdir()
    (scratch / "owner").write_text(str(owner))
    source = scratch / "source"
    def make_old():
        (source / "src/core").mkdir(parents=True)
        (source / "CMakeLists.txt").write_text("project(OldCachedEden)\n")
        (source / "GIT-COMMIT").write_text(module.PIN + "\n")
        (source / "src/core/device_memory_manager.h").write_text(
            "\n".join(module.OLD) + "\n")
        for receipt in module.RECEIPTS:
            (source / receipt).write_text("old-patch-receipt\n")
    make_old()
    store = source / ".cache/cpm"
    store.mkdir(parents=True)
    (store / "sentinel").write_text("keep CPM packages")
    for dirname in ("sdk", "native-local", "radv"):
        (scratch / dirname).mkdir()
        (scratch / dirname / "sentinel").write_text("keep native cache")
    first = invoke(scratch, archive, owner)
    assert "EDEN_ATOMIC_CACHE_REFRESH" in first.stdout
    assert "pristine" in (source / "src/core/device_memory_manager.h").read_text()
    assert (source / ".cache/cpm/sentinel").read_text() == "keep CPM packages"
    for dirname in ("sdk", "native-local", "radv"):
        assert (scratch / dirname / "sentinel").read_text() == "keep native cache"
    assert not (scratch / ".eden-stale-atomic-backup").exists()
    invoke(scratch, archive, owner)  # modern cache: safe no-op
    shutil.rmtree(source)
    make_old()
    header = source / "src/core/device_memory_manager.h"
    header.write_text(header.read_text() + module.NEW[0] + "\n")
    invoke(scratch, archive, owner, False)
    assert module.OLD[0] in header.read_text()
    header.write_text("\n".join(module.OLD[:-1]))
    invoke(scratch, archive, owner, False)
    assert module.OLD[0] in header.read_text()
    header.write_text("\n".join(module.OLD))
    (source / "GIT-COMMIT").write_text("unknown-pin")
    invoke(scratch, archive, owner, False)
    (source / "GIT-COMMIT").write_text(module.PIN)
    (scratch / "owner").write_text("/unknown-owner")
    invoke(scratch, archive, owner, False)
print("PASS production R289 cached old atomic_ref source refresh; keep CPM/SDK/RADV/"
      "native caches, refuse mixed/incomplete/wrong owner/pin")
