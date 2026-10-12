// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// PS5/FreeBSD read-only scheduler SMT group parser; requires no native headers.
// Reject partial, overlapping, unlabelled and implausible sibling maps.
#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <string_view>

namespace Eden::CpuTopology {
inline bool Hex(std::string_view str, std::uint64_t& result) noexcept {
    if (str.empty() || str.size() > 16) return false;
    result = 0;
    for (char c : str) {
        unsigned value = 16;
        if (c >= '0' && c <= '9') value = unsigned(c - '0');
        else if (c >= 'a' && c <= 'f') value = unsigned(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') value = unsigned(c - 'A' + 10);
        if (value >= 16) return false;
        result = (result << 4) | value;
    }
    return true;
}
inline bool ParseSmtGroups(std::string_view xml, std::uint64_t allowed,
                           std::array<int, 64>& ids) noexcept {
    ids.fill(-1);
    if (!allowed || xml.empty() || xml.size() > 65536) return false;
    std::uint64_t covered = 0;
    unsigned groups = 0;
    size_t pos = 0;
    while ((pos = xml.find("<group", pos)) != std::string_view::npos) {
        const size_t next = pos + 6;
        if (next >= xml.size() ||
            (xml[next] != ' ' && xml[next] != '\t' &&
             xml[next] != '\n' && xml[next] != '>')) {
            pos = next; // ignore <groups> root
            continue;
        }
        const size_t open = xml.find('>', next);
        if (open == std::string_view::npos) return false;
        const size_t child = xml.find("<children", open);
        const size_t close = xml.find("</group", open);
        if (close == std::string_view::npos) return false;
        const size_t limit = (std::min)(child, close);
        // The SMT flag must belong to this group, not an embedded child.
        if (xml.find("name=\"SMT\"", open) < limit) {
            const size_t cpu = xml.find("<cpu ", open);
            if (cpu < limit) {
                const size_t end = xml.find('>', cpu);
                if (end == std::string_view::npos || end >= limit) return false;
                const auto tag = xml.substr(cpu, end - cpu);
                const size_t start = tag.find("mask=\"");
                if (start == std::string_view::npos) return false;
                const size_t from = start + 6;
                const size_t stop = tag.find('"', from);
                if (stop == std::string_view::npos) return false;
                const auto value = tag.substr(from, stop - from);
                const auto comma = value.find(',');
                std::uint64_t mask{};
                if (!Hex(value.substr(0, comma), mask) ||
                    mask == 0 || std::popcount(mask) > 2) return false;
                const auto usable = mask & allowed;
                if (usable) {
                    if (covered & usable) return false;
                    const int core_id = int(std::countr_zero(mask));
                    for (unsigned cpu_id = 0; cpu_id < 64; ++cpu_id)
                        if (usable & (std::uint64_t{1} << cpu_id)) ids[cpu_id] = core_id;
                    covered |= usable;
                    ++groups;
                }
            }
        }
        pos = open + 1;
    }
    if (covered != allowed || groups < 5 || groups > 8) {
        ids.fill(-1);
        return false;
    }
    return true;
}
} // namespace Eden::CpuTopology
