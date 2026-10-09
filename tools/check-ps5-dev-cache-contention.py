#!/usr/bin/env python3
"""Bounded GPU cache-lock contention mitigation, test/dev-only.

The 13-minute FC27 R236 trace shows 460k guest cache-lock waits while
three guest cores are compute-bound. Check the exact bounded retry path
and verify no release/shipping behavior changes. No FPS claim or PS5 run.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "headless/main.cpp").read_text()
locks = (root / "headless/performance.h").read_text()
policy = (root / "headless/encore_performance_policy.h").read_text()

assert "inline std::atomic<unsigned> cache_lock_spins{0};" in locks
assert "if (mutex.try_lock()) return;" in locks
assert "for (unsigned tries = cache_lock_spins.load(std::memory_order_relaxed); tries != 0; --tries)" in locks
assert "if (mutex.try_lock()) return;" in locks
assert "mutex.lock();" in locks
assert "cache_lock_contended.fetch_add(1" in locks
assert "cache_lock_blocked.fetch_add(1" in locks
setup = main.split("Settings::values.skip_cpu_inner_invalidation.SetValue(false);", 1)[1]
assert "#if defined(PS5_NATIVE) && defined(EDEN_DEV_PROFILE)" in setup
dev = setup.split("#if defined(PS5_NATIVE) && defined(EDEN_DEV_PROFILE)", 1)[1].split("#endif", 1)[0]
assert "constexpr unsigned kTestCacheLockSpins = 8;" in dev
assert "Eden::Performance::cache_lock_spins.store(kTestCacheLockSpins, std::memory_order_relaxed);" in dev
assert "std::min(requested, 32ul)" in main
assert "Shipping stays 0" in dev
assert "kTestCacheLockSpins" not in policy

# Model exact retry count: eight bounded tries never become an unbounded
# lock-free loop. Exhausted attempts ALWAYS enter the original mutex lock.
def acquire(available_on_try: int | None, limit: int) -> tuple[int, bool]:
    tries = 0
    if available_on_try == 0:
        return 1, False
    while tries < limit:
        tries += 1
        if available_on_try == tries:
            return 1 + tries, False
    return 1 + tries, True

assert acquire(0, 8) == (1, False)
assert acquire(1, 8) == (2, False)
assert acquire(8, 8) == (9, False)
assert acquire(None, 8) == (9, True)
assert acquire(None, 0) == (1, True)
print("PASS: 8 limited GPU cache-lock retries in PS5 test build only; blocking mutex preserved")
print("PS5 performance improvement and soft-hang safety must still be measured on hardware")
