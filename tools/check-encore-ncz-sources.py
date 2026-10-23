#!/usr/bin/env python3
"""Verify NSZ/XCZ source owners and standard Library extensions."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
pinned=root/"vendor/sources/eden/src/core"
active=root/"vendor/encore-active/eden-core/src/core"
pairs=[
 ("file_sys/submission_package.cpp","0ea323492b914f05d45548cf90b912e00e610431","Ncz::Open"),
 ("file_sys/card_image.cpp","593c561689f1790b8c8ab673f3dd44d3d790f553","Ncz::Open"),
 ("loader/loader.cpp","90e23ccc11fb03672b22d169210dec6554e67f71","extension == \"xcz\""),
 ("loader/nsp.cpp","cfc908b4ef6e1b02636d88815aa5469052575784","\".ncz\""),
 ("file_sys/registered_cache.cpp","ce851e4d38ba752c626f51e29bae4d2303dbd39","extension == \"nsz\""),
]
for rel,sha,marker in pairs:
    raw=(pinned/rel).read_bytes()
    digest=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    assert digest==sha,("Pinned Eden changed",rel)
    text=(active/rel).read_text()
    assert marker in text and text!=raw.decode(),rel
    if marker=="Ncz::Open": assert '#include "ncz_vfs.h"' in text
    print("NCZ_SOURCE_OWNER_PASS",rel)
cmake=(root/"headless/CMakeLists.txt").read_text()
segment=cmake.split("# NSZ/XCZ: select reviewed full C++ source owners",1)[1].split("# The guest title is the owner",1)[0]
assert "write_derived" not in segment
assert segment.count("list(REMOVE_ITEM core_sources")==1
assert "ncz.cpp" in segment
for rel,_,_ in pairs: assert '"'+rel+'"' in segment
for path in ["headless/main.cpp","headless/settings_store.h","headless/metadata_bridge.cpp","headless/prosperoeden/eden_services.cpp"]:
    data=(root/path).read_text()
    assert (".nsz" in data or "IsGameFile" in data) and (".xcz" in data or "IsGameFile" in data),path
main=(root/"headless/main.cpp").read_text()
assert "Eden::Ncz::SetUnpackFolder(" in main
assert "Eden::Ncz::SetUnpackAllowed(true);" in main
assert main.count("Eden::Ncz::SetUnpackAllowed(false);")>=2
cpp=r"""
#include <cassert>
#include "game_files.h"
int main() {
    for(auto name:{"game.nsp","game.xci","game.nsz","game.xcz","GAME.NSP","GAME.XCI","GAME.NSZ","GAME.XCZ"})
        assert(Eden::IsGameFile(name));
    for(auto name:{"","game.nro","game.nso","game.nca","game.nax","game.kip","game.zstd","game.zbic","game.nsp.bak"})
        assert(!Eden::IsGameFile(name));
}
"""
compiler=shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory() as d:
    path=Path(d)/"game.cpp"
    path.write_text(cpp)
    exe=Path(d)/"check"
    result=subprocess.run([compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                           "-I"+str(root/"headless"),str(path),"-o",str(exe)],
                          capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stderr
    subprocess.run([str(exe)],check=True,timeout=12)
print("NCZ_FORMATS_AND_SELECTION_PASS")
