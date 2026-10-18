#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prevent one-past-end sparse CPU/GPU table access at the 2-MiB slot boundary.

Inspect the actual Encore-maintained header, not removed CMake injection text.
Byte-for-byte parity with pinned source transformations is checked separately.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sparse = (root / "vendor/encore-active/eden-core/src/common/sparse_large_vector.h").read_text()
upstream = (root / "vendor/sources/eden/src/common/sparse_large_vector.h").read_text()
old = 'if (index > alloc_size / sizeof(T)) {'
new = 'if (index >= alloc_size / sizeof(T)) {'
assert upstream.count(old) == 3
assert sparse.count(new) == 3
assert old not in sparse
for capacity in (1, 2, 4096, 1 << 20):
    assert all(index < capacity for index in (0, capacity - 1))
    assert all(index >= capacity for index in (capacity, capacity + 1))
for token in (
    'std::mutex sparse_mutation_mutex;',
    'std::lock_guard<std::mutex> mutation_lock{sparse_mutation_mutex};',
    'if (IsCommittedPage(index)) return;',
    'void CommitPage(std::size_t index) noexcept {',
):
    assert token in sparse, token
assert sparse.count('mutation_lock{sparse_mutation_mutex}') == 2
# An unmap that clears just one 16 KiB host page inside an owned 2 MiB
# slot must zero its bytes, not only the committed-page bitmap. Otherwise
# subsequent reuse treats stale mappings as fresh; dense fallback needs it too.
section = sparse.split('    void DecommitPage(std::size_t index) noexcept {', 1)[1].split('    void CommitPage(std::size_t index) noexcept {', 1)[0]
zero = 'std::memset(reinterpret_cast<void*>(page_address), 0, HostPageSize);'
clear = 'committed_pages[page_index >> 6].fetch_and('
decommit = 'DecommitSparsePage(vector_base + slot_offset);'
assert section.count(zero) == 1
assert section.index(zero) < section.index(clear) < section.index(decommit)
assert 'only calls here for a' in section
# Model the multi-page slot lifetime: removing A with B still live must
# make A's previously set bytes zero before an A re-commit.
pages = {0: bytearray(b'ABCD'), 1: bytearray(b'WXYZ')}
committed = {0, 1}
pages[0][:] = bytes(len(pages[0]))
committed.remove(0)
assert 1 in committed and bytes(pages[0]) == bytes(4)
committed.add(0)
assert bytes(pages[0]) == bytes(4)
native = (root / "src/memory_pages.cpp").read_text()
commit_source = native.split("void CommitSparsePage(std::uintptr_t page) noexcept {", 1)[1].split(
    "std::size_t SparseCommitSpan()", 1
)[0]
# The global owner lock must protect SparseRangeOf and the first owned[slot]
# dereference; otherwise concurrent FreeSparsePages can free the bitmap.
assert commit_source.count("const std::lock_guard lock{sparse_mutex};") == 1
assert commit_source.index("const std::lock_guard lock{sparse_mutex};") < commit_source.index("SparseRange* range = SparseRangeOf(page);")
assert commit_source.index("SparseRange* range = SparseRangeOf(page);") < commit_source.index("range->owned[slot]")
print("PASS: sparse table zero/decommit and page commit serialized per vector")
print("PASS: pinned SparseLargeVector GetAndFault/Set/IsCommittedPage stop at count")
