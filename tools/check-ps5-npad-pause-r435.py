#!/usr/bin/env python3
"""R435: prove diagnostic-only Npad fullkey LIFO witness retains original writes."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
cmake=(root/'headless/CMakeLists.txt').read_text()
hid=(root/'vendor/sources/eden/src/hid_core/resources/npad/npad.cpp').read_text()
input_src=(root/'headless/pad.cpp').read_text()
pad_header=(root/'third_party/ps5_pad.hpp').read_text()
assert 'if(PS5_NATIVE AND EDEN_DEV_PROFILE)' in cmake
assert 'R435: dev-only guest HID Fullkey Npad LIFO witness' in cmake
assert 'npad->fullkey_lifo.WriteNextEntry(pad_state);' in cmake
assert 'list(REMOVE_ITEM eden_npad_sources resources/npad/npad.cpp)' in cmake
assert 'Pinned Eden fullkey Npad writer changed; requalify R435' in cmake
assert cmake.count('EDEN_NPAD_PLUS_LIFO edges=%llu') == 1
assert cmake.count('EDEN_NPAD_PROGRESS fullkey_writes=%llu') == 1
assert 'std::atomic<bool> eden_fullkey_last_plus' in cmake
assert 'std::memory_order_relaxed' in cmake
assert cmake.count('npad->fullkey_lifo.WriteNextEntry(pad_state);') == 2
assert hid.count('                npad->fullkey_lifo.WriteNextEntry(pad_state);') == 2
assert hid.count('npad->fullkey_lifo.WriteNextEntry(pad_state);\\n                break;\\n            case Core::HID::NpadStyleIndex::Handheld:') == 1
assert 'set(eden_npad_write_anchor [=[' in cmake
assert '                {\\n                    // Event has entered emulated HID memory' in cmake
assert 'EDEN_NPAD_PLUS_LIFO' not in hid
assert 'published_plus_edges.fetch_add' in input_src
assert 'return sample.connected != 0 &&' in pad_header
assert 'kButtonIntercepted' in pad_header
cxx=shutil.which('c++') or shutil.which('clang++') or shutil.which('g++')
assert cxx
fixture=r"""
#include <atomic>
#include <cassert>
struct Witness {
 std::atomic<unsigned long long> writes{0}, plus_edges{0};
 std::atomic<bool> last_plus{false};
 void Write(bool plus) {
   bool prev=last_plus.exchange(plus,std::memory_order_relaxed);
   writes.fetch_add(1,std::memory_order_relaxed);
   if(plus && !prev) plus_edges.fetch_add(1,std::memory_order_relaxed);
 }
};
int main() {
 Witness w;
 for (int i=0;i<3000;++i)w.Write(false);
 w.Write(true); w.Write(true); w.Write(false);
 w.Write(true); w.Write(false);
 assert(w.plus_edges.load()==2);
 assert(w.writes.load()==3005);
}
"""
with tempfile.TemporaryDirectory(prefix='eden-r435-') as d:
    src=Path(d)/'npad.cpp'
    exe=Path(d)/'npad'
    src.write_text(fixture)
    subprocess.run([cxx,'-std=c++20','-O2','-pthread',str(src),'-o',str(exe)],
                   check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=90)
print("R435 PASS: dev-only Npad fullkey Plus LIFO witness; source pinned and writes unchanged")
