// SPDX-License-Identifier: GPL-3.0-or-later
// Isolated host mirror of the PS5-only GPU physical-span math.
// Passes ASan+UBSan; NOT a complete DeviceMemoryManager runtime or PS5 SDK test.
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <vector>

static constexpr std::size_t PAGE = 4096;

static std::vector<std::uint8_t> ReadBlockModel(
    const std::vector<std::uint32_t>& mapping,
    const std::vector<std::uint8_t>& physical,
    const std::vector<std::uint32_t>& hints,
    std::size_t address, std::size_t size) {
    std::vector<std::uint8_t> result(size, 0);
    if (size == 0 || address >= mapping.size() * PAGE ||
        size > mapping.size() * PAGE - address) return result;

    std::size_t remaining = size, page_index = address / PAGE;
    std::size_t page_offset = address % PAGE, written = 0;
    while (remaining) {
        const auto first_backing = mapping[page_index];
        const std::size_t hint = static_cast<std::size_t>(hints[page_index]) + 1;
        const std::size_t remaining_pages =
            1 + ((remaining - 1 + page_offset) / PAGE);
        std::size_t next_pages = std::min({
            hint, remaining_pages, mapping.size() - page_index});
        if (first_backing != 0) {
            const auto first_phys = static_cast<std::size_t>(first_backing - 1U);
            next_pages = first_phys >= physical.size() / PAGE
                ? 1 : std::min(next_pages, physical.size() / PAGE - first_phys);
        }
        for (std::size_t n = 1; n < next_pages; ++n) {
            const auto observed = mapping[page_index + n];
            const bool contiguous = first_backing == 0
                ? observed == 0 : observed == first_backing + n;
            if (!contiguous) {
                next_pages = n;
                break;
            }
        }
        const auto amount = std::min(next_pages * PAGE - page_offset, remaining);
        const auto phys_addr = mapping[page_index];
        if (phys_addr != 0 &&
            static_cast<std::size_t>(phys_addr - 1U) < physical.size() / PAGE) {
            const auto raw = static_cast<std::size_t>(phys_addr - 1U) * PAGE +
                             page_offset;
            assert(raw + amount <= physical.size());
            std::memcpy(result.data() + written, physical.data() + raw, amount);
        }
        written += amount;
        remaining -= amount;
        page_index += next_pages;
        page_offset = 0;
    }
    return result;
}

static std::vector<std::uint8_t> ReferenceRead(
    const std::vector<std::uint32_t>& mapping,
    const std::vector<std::uint8_t>& physical,
    std::size_t address, std::size_t size) {
    std::vector<std::uint8_t> result(size, 0);
    if (size == 0 || address >= mapping.size() * PAGE ||
        size > mapping.size() * PAGE - address) return result;
    for (std::size_t i = 0; i < size; ++i) {
        const auto guest = address + i;
        const auto phys_addr = mapping[guest / PAGE];
        if (phys_addr != 0 &&
            static_cast<std::size_t>(phys_addr - 1U) < physical.size() / PAGE)
            result[i] = physical[static_cast<std::size_t>(phys_addr - 1U) * PAGE +
                                 guest % PAGE];
    }
    return result;
}

static bool GetSpanModel(const std::vector<std::uint32_t>& mapping,
                         std::size_t capacity, std::size_t address,
                         std::size_t size) {
    if (size == 0 || address >= mapping.size() * PAGE ||
        size > mapping.size() * PAGE - address) return false;
    const auto first_page = address / PAGE;
    const auto page_count = 1 + ((size - 1 + address % PAGE) / PAGE);
    const auto backing = mapping[first_page];
    if (backing == 0) return false;
    const auto first_phys = static_cast<std::size_t>(backing - 1U);
    if (first_phys >= capacity || page_count > capacity - first_phys)
        return false;
    for (std::size_t i = 1; i < page_count; ++i)
        if (mapping[first_page + i] != backing + i) return false;
    return true;
}

static bool ReferenceSpan(const std::vector<std::uint32_t>& mapping,
                          std::size_t capacity, std::size_t address,
                          std::size_t size) {
    if (size == 0 || address >= mapping.size() * PAGE ||
        size > mapping.size() * PAGE - address) return false;
    const auto first = address / PAGE, last = (address + size - 1) / PAGE;
    const auto first_physical = mapping[first];
    if (first_physical == 0) return false;
    for (auto page = first; page <= last; ++page) {
        if (mapping[page] == 0 || mapping[page] > capacity ||
            mapping[page] != first_physical + page - first) return false;
    }
    return true;
}

int main() {
    std::mt19937 rng(0xEDA55);
    constexpr std::size_t request_sizes[] = {
        0, 1, 2, 16, PAGE - 1, PAGE, PAGE + 1, 2 * PAGE, 4 * PAGE};
    std::size_t tests = 0;
    for (std::size_t capacity : {1U, 2U, 4U, 8U, 12U}) {
        std::vector<std::uint8_t> physical(capacity * PAGE);
        for (auto& byte : physical) byte = static_cast<std::uint8_t>(rng());
        for (unsigned scenario = 0; scenario < 70; ++scenario) {
            std::vector<std::uint32_t> mapping(12), hints(12);
            for (std::size_t i = 0; i < mapping.size(); ++i) {
                mapping[i] = rng() % static_cast<unsigned>(capacity + 5);
                hints[i] = rng() % 80; // stale continuity, intentionally.
            }
            for (unsigned trial = 0; trial < 70; ++trial) {
                const auto address = rng() % (14 * PAGE);
                const auto bytes = request_sizes[rng() % 9];
                assert(ReadBlockModel(mapping, physical, hints, address, bytes) ==
                       ReferenceRead(mapping, physical, address, bytes));
                assert(GetSpanModel(mapping, capacity, address, bytes) ==
                       ReferenceSpan(mapping, capacity, address, bytes));
                ++tests;
            }
        }
    }
    assert(tests == 24500);
    std::cout << "PASS PS5 GPU host-only C++20 ASan/UBSan block and span math: "
              << tests << " deterministic cases\n";
}
