// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Pure validation of pinned PS5 Sony current-CPU + AMD CPUID 0x8000001E.
// This does NOT perform affinity syscalls or synthesize SMT pairs from CPU IDs.
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>

namespace Eden::CpuTopology {
struct AmdCpuEvidence {
    unsigned requested{};
    int sony_before{-1}, sony_after{-1};
    std::uint32_t ext_apic{}, ext_ebx{}, ext_ecx{};
    bool amd_leaf_supported{};
};
struct AmdCpuEvidenceResult {
    bool valid{};
    std::array<int,64> physical{};
    unsigned physical_count{};
    unsigned fully_accessible_pairs{};
    unsigned single_accessible_threads{};
};
inline AmdCpuEvidenceResult ValidateAmdSmtEvidence(
    std::uint64_t permitted, const AmdCpuEvidence* samples,
    std::size_t count) noexcept {
    AmdCpuEvidenceResult result{};
    result.physical.fill(-1);
    if (!samples || permitted == 0 ||
        count != static_cast<std::size_t>(std::popcount(permitted)) ||
        count < 5 || count > 16) return result;
    std::array<std::uint32_t,16> apics{},group_keys{};
    std::array<unsigned,16> group_sizes{};
    std::uint64_t witnessed=0;
    unsigned apic_count=0,group_count=0;
    for (std::size_t i=0;i<count;++i) {
        const auto& x=samples[i];
        if (x.requested >= 64 ||
            (permitted & (std::uint64_t{1}<<x.requested))==0 ||
            (witnessed & (std::uint64_t{1}<<x.requested)) ||
            x.sony_before != static_cast<int>(x.requested) ||
            x.sony_after != static_cast<int>(x.requested) ||
            !x.amd_leaf_supported ||
            ((x.ext_ebx>>8)&255u)+1u != 2u) return result;
        witnessed |= std::uint64_t{1}<<x.requested;
        // Reject virtualized CPUID that repeats APIC IDs across logical CPUs.
        for (unsigned j=0;j<apic_count;++j)
            if (apics[j]==x.ext_apic) return result;
        apics[apic_count++]=x.ext_apic;
        const std::uint32_t key=((x.ext_ecx&255u)<<8)|(x.ext_ebx&255u);
        unsigned group=0;
        while (group<group_count && group_keys[group]!=key)++group;
        if (group==group_count) {
            if (group_count==8)return result;
            group_keys[group_count++]=key;
        }
        if (++group_sizes[group] > 2)return result;
        result.physical[x.requested]=static_cast<int>(group);
    }
    if (witnessed!=permitted || group_count<5 || group_count>8)return result;
    result.physical_count=group_count;
    for (unsigned i=0;i<group_count;++i) {
        result.fully_accessible_pairs+=group_sizes[i]==2;
        result.single_accessible_threads+=group_sizes[i]==1;
    }
    result.valid=true;
    return result;
}
} // namespace Eden::CpuTopology
