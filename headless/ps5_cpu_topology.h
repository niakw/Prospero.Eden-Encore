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
// FreeBSD releng/11.4 kern_cpuset.c:cpusetobj_strprint prints the LOW
// unsigned-long word first, then comma-separated higher CPU words. On PS5
// (64-bit FreeBSD) only word zero can name CPU 0..63; refuse unexpected
// set bits in upper words rather than silently misclassifying siblings.
inline bool FreeBsdMask(std::string_view text, std::uint64_t& mask) noexcept {
    const auto comma = text.find(',');
    if (!Hex(text.substr(0, comma), mask)) return false;
    if (comma == std::string_view::npos) return true;
    size_t pos = comma + 1;
    while (pos < text.size()) {
        const auto next = text.find(',', pos);
        std::uint64_t word{};
        if (!Hex(text.substr(pos, next == std::string_view::npos
                                      ? next : next - pos), word) ||
            word != 0) return false;
        if (next == std::string_view::npos) return true;
        pos = next + 1;
    }
    return false; // trailing comma
}
inline bool ParseSmtGroups(std::string_view xml, std::uint64_t allowed,
                           std::array<int, 64>& ids) noexcept {
    ids.fill(-1);
    if (!allowed || xml.empty() || xml.size() > 65536) return false;
    // Never leak a half-validated SMT assignment to the caller when a
    // malformed later group or a high cpuset word causes early rejection.
    std::array<int, 64> candidate{};
    candidate.fill(-1);
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
        // FreeBSD 11.4 sched_ule.c prints CG_FLAG_HTT ("alternate core
        // last") OR CG_FLAG_SMT ("new age htt"), and CG_FLAG_THREAD on both.
        // THREAD alone does not prove physical siblings. Never use flags
        // attached to a nested group rather than the current group.
        const bool physical_siblings =
            xml.find("name=\"SMT\"", open) < limit ||
            xml.find("name=\"HTT\"", open) < limit;
        if (physical_siblings) {
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
                std::uint64_t mask{};
                if (!FreeBsdMask(value, mask) ||
                    mask == 0 || std::popcount(mask) > 2) return false;
                const auto usable = mask & allowed;
                if (usable) {
                    if (covered & usable) return false;
                    const int core_id = int(std::countr_zero(mask));
                    for (unsigned cpu_id = 0; cpu_id < 64; ++cpu_id)
                        if (usable & (std::uint64_t{1} << cpu_id)) candidate[cpu_id] = core_id;
                    covered |= usable;
                    ++groups;
                }
            }
        }
        pos = open + 1;
    }
    if (covered != allowed || groups < 5 || groups > 8) return false;
    ids = candidate;
    return true;
}
} // namespace Eden::CpuTopology
