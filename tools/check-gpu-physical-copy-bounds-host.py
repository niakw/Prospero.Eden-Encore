#!/usr/bin/env python3
"""Host model for PS5 GPU physical-page bounds; no device, title, or SDK.

The immutable source checks separately require the real pinned GPU patches to
contain the same bounds decisions. This model proves the page math and
fail-closed byte semantics, not that the compiled PS5 driver is correct.
"""
from __future__ import annotations

from pathlib import Path
import random

root = Path(__file__).resolve().parents[1]
physical_patch = (root / "headless/backports/eden-ps5-gpu-physical-read-bounds.patch").read_text()
flush_patch = (root / "headless/backports/eden-ps5-gpu-block-flush-bounds.patch").read_text()
for token in (
    "first_phys >= compressed_device_addr.size()",
    "compressed_device_addr.size() - first_phys",
    "next_pages = first_phys >= compressed_device_addr.size()",
    "on_unmapped(copy_amount, current_vaddr)",
    "static_cast<size_t>(phys_addr - 1U) < compressed_device_addr.size()",
):
    assert token in physical_patch, token
assert physical_patch.count("static_cast<size_t>(phys_addr - 1U) < compressed_device_addr.size()") == 2
assert "std::memset(dest_pointer, 0, size);" in flush_patch
assert "size <= device_as_size - address" in flush_patch
span_patch = (root / "headless/backports/eden-ps5-gpu-span-physical-bounds.patch").read_text()
assert span_patch.count("page_count > compressed_device_addr.size() - first_phys") == 2

PAGE = 4096


def checked_block(mapping: list[int], physical: bytes, addr: int, size: int,
                  hints: list[int]) -> tuple[bytes, int]:
    # GPU virtual region bounds guard runs before renderer FlushRegion.
    gpu_size = len(mapping) * PAGE
    if size == 0:
        return b"", 0
    if addr >= gpu_size or size > gpu_size - addr:
        return b"\x00" * size, 0
    capacity = len(physical) // PAGE
    result = bytearray()
    checks = 0
    remaining, index, offset = size, addr // PAGE, addr % PAGE
    while remaining:
        first_backing = mapping[index]
        remaining_pages = 1 + ((remaining - 1 + offset) // PAGE)
        next_pages = min(hints[index] + 1, remaining_pages, len(mapping) - index)
        if first_backing:
            first_phys = first_backing - 1
            next_pages = 1 if first_phys >= capacity else min(next_pages, capacity - first_phys)
        for step in range(1, next_pages):
            checks += 1
            observed = mapping[index + step]
            contiguous = (observed == 0) if first_backing == 0 else (observed == first_backing + step)
            if not contiguous:
                next_pages = step
                break
        amount = min(next_pages * PAGE - offset, remaining)
        phys_page = mapping[index]
        if phys_page == 0 or phys_page - 1 >= capacity:
            result.extend(b"\x00" * amount)
        else:
            start = (phys_page - 1) * PAGE + offset
            assert start + amount <= len(physical)
            result.extend(physical[start:start + amount])
        remaining -= amount
        index += next_pages
        offset = 0
    return bytes(result), checks


def reference(mapping: list[int], physical: bytes, addr: int, size: int) -> bytes:
    if size == 0:
        return b""
    if addr >= len(mapping) * PAGE or size > len(mapping) * PAGE - addr:
        return b"\x00" * size
    capacity = len(physical) // PAGE
    result = bytearray(size)
    for start in range(0, size):
        guest = addr + start
        phys_page = mapping[guest // PAGE]
        if phys_page and phys_page - 1 < capacity:
            result[start] = physical[(phys_page - 1) * PAGE + guest % PAGE]
    return bytes(result)


def checked_span(mapping: list[int], capacity: int, addr: int, size: int) -> bool:
    # Source-backed GetSpan guard: all physical pages must be adjacent and
    # the LAST page must fit in the physical backing too.
    if size == 0 or addr >= len(mapping) * PAGE or size > len(mapping) * PAGE - addr:
        return False
    start_page = addr // PAGE
    page_count = 1 + ((size - 1 + addr % PAGE) // PAGE)
    backing = mapping[start_page]
    if backing == 0:
        return False
    first_phys = backing - 1
    if first_phys >= capacity or page_count > capacity - first_phys:
        return False
    return all(mapping[start_page + i] == backing + i for i in range(1, page_count))


def reference_span(mapping: list[int], capacity: int, addr: int, size: int) -> bool:
    if size < 1 or addr + size > len(mapping) * PAGE:
        return False
    first = addr // PAGE
    last = (addr + size - 1) // PAGE
    phys = mapping[first]
    return phys > 0 and all(
        1 <= mapping[i] <= capacity and mapping[i] == phys + i - first
        for i in range(first, last + 1)
    )


rng = random.Random(0xEDE9)
for capacity in (1, 2, 4, 8, 12):
    # Include invalid page zero (unmapped), exact last page and stale
    # indices at and beyond the end of the host DRAM backing.
    physical = bytes(rng.randrange(256) for _ in range(capacity * PAGE))
    for _ in range(65):
        mapping = [rng.randrange(capacity + 5) for _ in range(12)]
        hints = [rng.randrange(0, 36) for _ in mapping]  # deliberately stale
        for _ in range(15):
            addr = rng.randrange(0, (len(mapping) + 2) * PAGE)
            size = rng.choice((0, 1, 2, 16, PAGE-1, PAGE, PAGE+1, 2*PAGE, 4*PAGE))
            actual, checks = checked_block(mapping, physical, addr, size, hints)
            assert actual == reference(mapping, physical, addr, size)
            assert checked_span(mapping, capacity, addr, size) == reference_span(
                mapping, capacity, addr, size)
            if size and addr // PAGE == (addr + size - 1) // PAGE:
                assert checks == 0  # the O(1) hot-path guarantee

# A stale hint pointing past the actual last physical page must be split
# exactly at the capacity boundary; the rest becomes zero without deref.
for capacity in (1, 2, 4, 8, 12):
    physical = bytes([0xCA]) * (PAGE * capacity)
    mapping = [capacity, capacity + 1, capacity + 2]
    result, _ = checked_block(mapping, physical, 0, PAGE * 3, [200] * 3)
    assert result == bytes([0xCA]) * PAGE + bytes(PAGE * 2)

print("PASS host GPU DRAM-boundary model: valid page, OOB, stale span, zero read, no cross-boundary deref, const/mutable GetSpan")
print("GPU native mapping synchronization / FC27 texture correctness NOT hardware qualified")
