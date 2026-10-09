// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Native PS5 JIT construction: a failed *dense code allocation* should not
// turn available, but fragmented direct memory into a hard game-start crash.
// This header is used by BOTH A64 and A32 per-core wrappers.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <new>
#include <utility>
#include <xbyak/xbyak.h>

namespace Eden::JitStartup {
constexpr std::uint32_t kAlignment = 2u * 1024u * 1024u;

constexpr std::uint32_t NextCapacity(std::uint32_t previous,
                                     std::uint32_t baseline) noexcept {
    if (previous <= baseline) return previous;
    // Halving a failed 1 GiB arena immediately throws away 512 MiB of
    // possible JIT capacity even when only a small amount is unavailable.
    // Step down by 25% (2 MiB aligned), preserving more guest code cache,
    // while still converging geometrically to the known-good baseline.
    // Subtraction avoids overflow near UINT32_MAX.
    std::uint32_t candidate =
        ((previous - previous / 4) / kAlignment) * kAlignment;
    if (candidate < baseline) candidate = baseline;
    // Any accepted retry must be strictly smaller; callers never spin.
    if (candidate >= previous) candidate = baseline;
    return candidate;
}

// Restrict recovery to actual allocator failures. Invalid instructions,
// protection failures and unrelated exceptions still propagate immediately.
// std::optional<Dynarmic::Jit>::emplace has strong empty-on-throw semantics:
// failed JIT constructors do not publish executable pointers into guest state.
template<class Construct>
void ConstructWithCapacityFallback(std::uint32_t& capacity, std::uint32_t baseline,
                                   unsigned bits, std::size_t core, Construct&& construct) {
    for (;;) {
        try {
            std::forward<Construct>(construct)();
            return;
        } catch (const Xbyak::Error& error) {
            if (static_cast<int>(error) != Xbyak::ERR_CANT_ALLOC || capacity <= baseline)
                throw;
        } catch (const std::bad_alloc&) {
            if (capacity <= baseline) throw;
        }
        const std::uint32_t next = NextCapacity(capacity, baseline);
        if (next == capacity) throw std::bad_alloc{};
        std::fprintf(stderr, "EDEN_JIT_STARTUP_RETRY bits=%u core=%zu from=%u to=%u\n",
                     bits, core, capacity, next);
        capacity = next;
    }
}

static_assert(NextCapacity(128u * 1024u * 1024u, 64u * 1024u * 1024u) ==
              96u * 1024u * 1024u);
static_assert(NextCapacity(320u * 1024u * 1024u, 192u * 1024u * 1024u) ==
              240u * 1024u * 1024u);
static_assert(NextCapacity(258u * 1024u * 1024u, 256u * 1024u * 1024u) ==
              256u * 1024u * 1024u);
static_assert(NextCapacity(16u * 1024u * 1024u, 16u * 1024u * 1024u) ==
              16u * 1024u * 1024u);
} // namespace Eden::JitStartup
