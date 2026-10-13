#!/usr/bin/env python3
"""Install a full maintained upstream build recipe instead of a CMake rewrite.

Exact-content contract: only the invalid Clang -Wno-error-all spelling is
corrected, to its supported -Wno-error=all equivalent. Upstream is immutable.
"""
from pathlib import Path
import argparse
import shutil
import tempfile

root=Path(__file__).resolve().parents[1]
original=root/"vendor/sources/eden/src/CMakeLists.txt"
active=root/"vendor/encore-active/eden-build/src/CMakeLists.txt"
old=original.read_bytes()
assert old.count(b"-Wno-error-all>")==1, "upstream flags changed"
expected=old.replace(b"-Wno-error-all>", b"-Wno-error=all>")
assert active.read_bytes()==expected, "versioned native build recipe diverged"

ap=argparse.ArgumentParser()
ap.add_argument("source",nargs="?")
args=ap.parse_args()
if args.source is None:
    print("EDEN_NATIVE_BUILD_RECIPE_PASS maintained source matches pinned original except Clang flag")
else:
    target=Path(args.source)/"src/CMakeLists.txt"
    assert target.is_file(), target
    existing=target.read_bytes()
    if existing==expected:
        print("EDEN_NATIVE_BUILD_RECIPE_ALREADY_ACTIVE")
    else:
        assert existing==old, "refusing to replace unknown build recipe"
        # The compiled staged copy is verbatim the versioned active source.
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as file:
            temp=Path(file.name)
        try:
            shutil.copyfile(active,temp)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        print("EDEN_NATIVE_BUILD_RECIPE_INSTALLED maintained full source")
