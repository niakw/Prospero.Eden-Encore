#!/usr/bin/env python3
"""Install complete, maintained build recipes instead of source-text CMake rewrites.

Only source stage copies change; original upstream inputs remain immutable.
Both transforms are compared byte for byte with the pinned original.
"""
from pathlib import Path
import argparse
import shutil
import tempfile

root=Path(__file__).resolve().parents[1]
specs=(
    ("src/CMakeLists.txt",b"-Wno-error-all>",b"-Wno-error=all>"),
    ("src/common/scm_rev.cpp.in",b'#define BUILD_ID "@BUILD_ID@"',
     b'#ifdef BUILD_ID\n#undef BUILD_ID\n#endif\n#define BUILD_ID "@BUILD_ID@"'),
)
expected_sources=[]
for relative,before,after in specs:
    original=root/"vendor/sources/eden"/relative
    active=root/"vendor/encore-active/eden-build"/relative
    old=original.read_bytes()
    assert old.count(before)==1, f"pinned source changed: {relative}"
    expected=old.replace(before,after)
    assert active.read_bytes()==expected, f"maintained build source diverged: {relative}"
    expected_sources.append((relative,old,expected,active))
ap=argparse.ArgumentParser()
ap.add_argument("source",nargs="?")
args=ap.parse_args()
if args.source is None:
    print(f"EDEN_NATIVE_BUILD_RECIPES_PASS files={len(expected_sources)} byte-exact tracked sources")
else:
    stage=Path(args.source)
    for relative,old,expected,active in expected_sources:
        target=stage/relative
        assert target.is_file(), target
        current=target.read_bytes()
        if current==expected:
            print(f"EDEN_NATIVE_BUILD_RECIPE_ALREADY_ACTIVE {relative}")
            continue
        assert current==old, f"refusing to overwrite unknown revision: {relative}"
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as file:
            temp=Path(file.name)
        try:
            shutil.copyfile(active,temp)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        print(f"EDEN_NATIVE_BUILD_RECIPE_INSTALLED {relative}")
