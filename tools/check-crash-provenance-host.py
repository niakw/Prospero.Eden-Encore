#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-only fixture for exact ELF .text-size provenance, no PS5 build."""
import hashlib
import importlib.util
from pathlib import Path
import struct

root = Path(__file__).resolve().parents[1]
source = root / "tools/ci/write-crash-provenance.py"
spec = importlib.util.spec_from_file_location("eden_crash_provenance", source)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

buf = bytearray(0x300)
buf[:6] = b"\x7fELF\x02\x01"
names = b"\0.shstrtab\0.text\0"
buf[0x100:0x100+len(names)] = names
buf[0x120:0x160] = b"\x90" * 64
struct.pack_into("<Q", buf, 0x28, 0x200)
struct.pack_into("<HHH", buf, 0x3A, 64, 3, 1)
fmt = "<IIQQQQIIQQ"
struct.pack_into(fmt, buf, 0x200 + 64, 1, 3, 0, 0, 0x100, len(names), 0, 0, 1, 0)
struct.pack_into(fmt, buf, 0x200 + 128, 11, 1, 6, 0x400000, 0x120, 64, 0, 0, 16, 0)

assert m.text_size(bytes(buf)) == 64
bad_ident = bytearray(buf)
bad_ident[5] = 2  # big-endian rejected
try:
    m.text_size(bytes(bad_ident))
except ValueError:
    pass
else:
    raise AssertionError("bad ELF identity accepted")
bad_offset = bytearray(buf)
struct.pack_into("<Q", bad_offset, 0x200 + 128 + 24, len(buf) + 4096)
try:
    m.text_size(bytes(bad_offset))
except ValueError:
    pass
else:
    raise AssertionError("out-of-file .text accepted")
bad_shstr = bytearray(buf)
struct.pack_into("<H", bad_shstr, 0x3E, 9)
try:
    m.text_size(bytes(bad_shstr))
except ValueError:
    pass
else:
    raise AssertionError("invalid string table index accepted")

# The authoritative symbolizer must still fail closed on mismatched ELF code
# size; the receipt alone never blesses a crash RIP against a different build.
symbolizer_path = root / "tools/symbolize-crash.py"
symbolizer = symbolizer_path.read_text()
assert "REFUSED symbolization:" in symbolizer and "!= size" in symbolizer
spec_symbols = importlib.util.spec_from_file_location("eden_symbolizer", symbolizer_path)
assert spec_symbols and spec_symbols.loader
sym = importlib.util.module_from_spec(spec_symbols)
spec_symbols.loader.exec_module(sym)
valid = {"schema": 1, "elf_text_size_hex": "0x40",
         "files": {"unstripped_elf": {"sha256": hashlib.sha256(buf).hexdigest()}}}
sym.verify_elf_receipt(bytes(buf), 64, valid)
for wrong in (
    {"schema": 1, "elf_text_size_hex": "0x40", "files": {"unstripped_elf": {"sha256": "0" * 64}}},
    {"schema": 1, "elf_text_size_hex": "0x41", "files": valid["files"]},
    {"schema": 0, "elf_text_size_hex": "0x40", "files": valid["files"]},
    {"schema": 1, "elf_text_size_hex": "0x40", "files": None},
    {"schema": 1, "elf_text_size_hex": "0x40", "files": {"unstripped_elf": None}},
):
    try:
        sym.verify_elf_receipt(bytes(buf), 64, wrong)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched ELF receipt passed symbolizer")
workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()
assert "tools/ci/write-crash-provenance.py" in workflow
assert "build/headless-native/crash-provenance.json" in workflow
assert "env.EDEN_TEST_ALL_ON == '1'" in workflow
print("PASS host-only PS5 crash provenance: ELF bounds, SHA256 receipt binding and build gate")
