// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Monotonic witness: a buffer has ever occupied a guest-physical page.
// Every representable registration is published; a large but valid buffer
// must not permanently turn off the never-owned fast path for the whole game.
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
namespace Eden::BufferPages {
inline constexpr unsigned kPageBits=12;
inline constexpr std::uint64_t kSpace=std::uint64_t{1}<<34;
inline constexpr std::size_t kWords=static_cast<std::size_t>(kSpace>>kPageBits)/64;
inline std::array<std::atomic<std::uint64_t>,kWords> registered{};
inline std::atomic<bool> coverage_unknown{false};
constexpr std::uint64_t Bits(unsigned first,unsigned last) noexcept {
  return (~std::uint64_t{0}>>(63-last)) & (~std::uint64_t{0}<<first);
}
inline void Mark(std::uint64_t address,std::uint64_t size) noexcept {
  if(!size)return;
  // The bitmap already covers the entire 16 GiB guest-physical domain.
  // Old code treated any >128 MiB allocation as unknown forever, forcing
  // later unrelated CPU writes through both cache-lock fallbacks. A large
  // valid buffer costs a bounded bitmap walk but keeps untouched pages fast.
  if(address>=kSpace || size>kSpace-address){
    coverage_unknown.store(true,std::memory_order_release);
    return;
  }
  const auto first=address>>kPageBits,last=(address+size-1)>>kPageBits;
  for(auto word=first/64;word<=last/64;++word){
    const auto mask=Bits(word==first/64?first%64:0,
                         word==last/64?last%64:63);
    // Most image/buffer reuses touch pages that were already published.
    // A read-only witness avoids another contended atomic RMW in that case.
    // A partial/previously unseen word still uses fetch_or so concurrent
    // registrations of disjoint pages cannot lose either registration.
    if ((registered[word].load(std::memory_order_acquire) & mask) != mask)
      registered[word].fetch_or(mask,std::memory_order_release);
  }
}
inline bool NeverRegistered(std::uint64_t address,std::uint64_t size) noexcept {
  if(coverage_unknown.load(std::memory_order_acquire))return false;
  if(!size || size>64*1024 || address>=kSpace || size>kSpace-address)return false;
  const auto first=address>>kPageBits,last=(address+size-1)>>kPageBits;
  // The 64 KiB cap spans at most two bitmap words, including unaligned ends.
  const auto first_word=first/64,last_word=last/64;
  const auto first_mask=Bits(first%64,first_word==last_word?last%64:63);
  if(registered[first_word].load(std::memory_order_acquire)&first_mask)return false;
  if(first_word!=last_word &&
     (registered[last_word].load(std::memory_order_acquire)&Bits(0,last%64)))return false;
  return !coverage_unknown.load(std::memory_order_acquire);
}
} // namespace Eden::BufferPages
