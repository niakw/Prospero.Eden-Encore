#!/usr/bin/env python3
"""Check the maintained Xbyak v7.40.1 writable-alias header and selection.

Exact source replay runs when the pinned CPM dependency is present. Otherwise
validate the stored source identity and all eight changed regions without
requiring external network access during preflight.
"""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
maintained = root / "vendor/encore-active/eden-build/third_party/xbyak/xbyak.h"
selector = (root / "headless/jit-alias.cmake").read_text()
text = maintained.read_text()
edits = json.loads(r'''[["virtual void free(uint8_t *p) { AlignedFree(p); }","virtual uint8_t *writableAddress(uint8_t *p) { return p; }\n\tvirtual void free(uint8_t *p) { AlignedFree(p); }"],["uint8_t *top_;","uint8_t *top_;\n\tuint8_t *writeTop_;"],[", size_(0)",", writeTop_(type_ == USER_BUF ? top_ : alloc_->writableAddress(top_))\n\t\t, size_(0)"],["newTop[i] = top_[i]","alloc_->writableAddress(newTop)[i] = top_[i]"],["top_ = newTop;","top_ = newTop;\n\t\twriteTop_ = alloc_->writableAddress(top_);"],["top_[size_++] =","writeTop_[size_++] ="],["uint8_t *const data = top_ + offset;","uint8_t *const data = writeTop_ + offset;"],["const uint8_t *getCode() const { return top_; }","bool hasWritableAlias() const { return writeTop_ != top_; }\n\tuint8_t *writableAddress(const void *p) const { return writeTop_ + (static_cast<const uint8_t*>(p) - top_); }\n\tconst uint8_t *getCode() const { return top_; }"]]''')
def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
assert git_blob(maintained.read_bytes()) == "fa5e37041309cb18adb29bbf60ff79386b0250f8", "Maintained Xbyak source changed"
# The tag is herumi/xbyak v7.40.1, commit 964adcd198c716c0691c7d73f6c2be73db6682bd.
pinned = root / ".cache/cpm/xbyak/v7.40.1/xbyak/xbyak.h"
if pinned.is_file():
    original = pinned.read_text()
    assert git_blob(pinned.read_bytes()) == "5f8cbb5cdad9db9f480ec3cb9f3f7a9d050552e7", "Xbyak dependency pin changed"
    for old, new in edits:
        assert original.count(old) == 1, ("Xbyak pinned anchor changed", old)
        original = original.replace(old, new)
    assert original == text, "Maintained Xbyak header differs from the prior generator"
else:
    for old, new in edits:
        assert text.count(new) == 1, ("Maintained Xbyak edit missing or duplicated", new[:64])
    assert "XBYAK_XBYAK_H_" in text and "hasWritableAlias() const" in text
assert 'configure_file("${EDEN_MAINTAINED_XBYAK_HEADER}"' in selector
assert 'write_derived("${PORT_BUILD_DIR}/include/xbyak/xbyak.h"' not in selector
assert selector.count('string(REPLACE') == 0, "Xbyak selector must not mutate BlockOfCode"
assert "target_compile_definitions(dynarmic PUBLIC EDEN_JIT_ALIAS_LAYOUT=1)" in selector
print("VENDOR_MAINTAINED_XBYAK_ALIAS_PASS: eight edits, explicit COPYONLY selection")
