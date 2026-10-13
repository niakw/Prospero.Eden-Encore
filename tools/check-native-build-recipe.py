#!/usr/bin/env python3
"""Exercise exact full-versioned native compiler flag recipe, twice."""
from pathlib import Path
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
source=root/"vendor/sources/eden/src/CMakeLists.txt"
tracked=root/"vendor/encore-active/eden-build/src/CMakeLists.txt"
script=root/"tools/install-vendored-eden-build-flags.py"
original=source.read_bytes()
corrected=tracked.read_bytes()
assert original.count(b"-Wno-error-all>")==1
assert corrected==original.replace(b"-Wno-error-all>",b"-Wno-error=all>")
assert b"-Wno-error-all>" not in corrected
subprocess.run([sys.executable,"-B",str(script)],check=True,timeout=12)
with tempfile.TemporaryDirectory(prefix="eden-native-recipe-") as scratch:
    location=Path(scratch)
    (location/"src").mkdir()
    staged=location/"src/CMakeLists.txt"
    staged.write_bytes(original)
    for iteration in range(2):
        subprocess.run([sys.executable,"-B",str(script),str(location)],check=True,timeout=12)
        assert staged.read_bytes()==corrected, iteration
    staged.write_bytes(b"unrecognized revision")
    refused=subprocess.run([sys.executable,"-B",str(script),str(location)],
                           capture_output=True,text=True,timeout=12)
    assert refused.returncode!=0
    assert staged.read_bytes()==b"unrecognized revision"
print("PASS native build recipe: exact maintained full CMake, idempotent stage, unknown revisions rejected")
