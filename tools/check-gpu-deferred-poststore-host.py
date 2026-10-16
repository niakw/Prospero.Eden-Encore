#!/usr/bin/env python3
"""Host sanitizer: reserve -> real store -> publish; cancel failed conditionals.

This proves the standalone transaction primitive against the real queue. It
does NOT compile or activate a native guest memory callback, GPU read fence,
or JIT/fastmem path.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "headless/gpu_deferred_store_publication.h").read_text()
queue = (root / "headless/gpu_deferred_write_queue.h").read_text()
replay = (root / "headless/gpu_deferred_replay.h").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
bridge = (root / "headless/guest_write_deferred_bridge.cmake").read_text()
source = (root / "vendor/sources/eden/src/core/memory.cpp").read_text()

for part in ("queue.ReserveOrdered(core, address, size, request_gpu)",
             "std::forward<Store>(store)()",
             "queue.PublishAndWake(*ticket, request_gpu)",
             "queue.CancelAndWake(*ticket, request_gpu)",
             "std::is_nothrow_invocable_r_v"):
    assert part in header, part
assert header.index("queue.ReserveOrdered(") < header.index("std::forward<Store>(store)()")
assert header.index("std::forward<Store>(store)()") < header.index("queue.PublishAndWake(")
assert "std::optional<Ticket> ReserveOrdered(" in queue
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert "CommitPostStore(" not in bridge
assert "python3 -B tools/check-gpu-deferred-poststore-host.py" in workflow
for part in ("enum class ReadBarrierResult { Complete, Failed };",
             "std::optional<StoreOutcome> CommitConditionalAfterRead(",
             "std::is_same_v<std::invoke_result_t<SyncRead&>, ReadBarrierResult>",
             "if (std::forward<SyncRead>(synchronize_read)() != ReadBarrierResult::Complete)",
             "return CommitPostStore(queue, core, address, size,"):
    assert part in header, part
assert header.index("synchronize_read)()") < header.index("return CommitPostStore(")
assert "CommitConditionalAfterRead(" not in bridge

# Source-backed classification: a tracked ordinary/memset store happens
# AFTER HandleRasterizerWrite, whereas dc cvac/civac only invalidates.
write_block = source.split("bool WriteBlockImpl(", 1)[1].split("bool ZeroBlock(", 1)[0]
assert "std::memcpy(ptr, reinterpret_cast<u8 const*>(buffer) + offset, copy_amount);" in write_block.rsplit(
    "HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);", 1)[1]
zero = source.split("bool ZeroBlock(", 1)[1].split("bool CopyBlock(", 1)[0]
assert "std::memset(ptr, 0, copy_amount);" in zero.rsplit(
    "HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);", 1)[1]
cache_ops = source.split("Result StoreDataCache(", 1)[1].split("void MarkRegionDebug(", 1)[0]
assert cache_ops.count("HandleRasterizerWrite(GetInteger(current_vaddr), block_size);") == 2
assert "std::memcpy(" not in cache_ops and "std::memset(" not in cache_ops
scalar = source.split("inline void Write(Common::ProcessAddress vaddr,", 1)[1].split(
    "bool WriteExclusive(", 1)[0]
assert scalar.index("HandleRasterizerWrite(addr, sizeof(T));") < scalar.index(
    "std::memcpy(ptr, &data, sizeof(T));")
exclusive = source.split("bool WriteExclusive(Common::ProcessAddress vaddr,", 1)[1].split(
    "void HandleRasterizerDownload(", 1)[0]
assert exclusive.count("Common::AtomicCompareAndSwap(") == 2

cpp = r"""
#include "gpu_deferred_store_publication.h"
#include "gpu_deferred_replay.h"
#include <atomic>
#include <cassert>
#include <cstdint>
#include <stdexcept>
#include <vector>
using namespace Eden::GpuDeferredWrite;
static_assert(!kNativePostStorePublicationReady);
int main() {
    Queue ordinary;
    std::uint32_t backing_ram = 0;
    unsigned stores = 0, callbacks = 0;
    const auto result = CommitPostStore(ordinary, 0, 0x2000, 4,
        [&]() noexcept -> StoreOutcome {
            assert(backing_ram == 0);
            backing_ram = 0xAABBCCDD;
            ++stores;
            return StoreOutcome::Modified;
        }, [&]() -> bool {
            ++callbacks;
            assert(ordinary.Drain([&](unsigned core, std::uint64_t addr,
                                       std::uint64_t size) {
                assert(core == 0 && addr == 0x2000 && size == 4);
                assert(backing_ram == 0xAABBCCDD);
            }) == 1);
            return true;
        });
    assert(result == StoreOutcome::Modified && stores == 1 && callbacks == 1);
    assert(!ordinary.Pending());

    // CAS fails: no backing RAM mutation and no cache invalidation.
    // This test does NOT qualify the prerequisite GPU-to-CPU download.
    Queue failed_cas;
    std::atomic<int> atomic_ram{7};
    unsigned cas_invalidations = 0;
    const auto cas_result = CommitPostStore(failed_cas, 2, 0x3000, 4,
        [&]() noexcept -> StoreOutcome {
            int expected = 9;
            if (atomic_ram.compare_exchange_strong(expected, 11))
                return StoreOutcome::Modified;
            assert(expected == 7);
            return StoreOutcome::Unchanged;
        }, [&]() -> bool {
            assert(failed_cas.Drain([&](unsigned,std::uint64_t,std::uint64_t) {
                ++cas_invalidations;
            }) == 0);
            return true;
        });
    assert(cas_result == StoreOutcome::Unchanged && cas_invalidations == 0 &&
           atomic_ram.load() == 7 && !failed_cas.Pending());

    // A real conditional read barrier must FIRST replay older published
    // guest writes / GPU invalidations and complete the download, then the
    // CAS attempt can inspect the freshly synchronized guest RAM.
    Queue conditional;
    std::atomic<int> conditional_ram{7};
    unsigned prior_invalidations = 0, conditional_invalidations = 0;
    const auto pending_older = conditional.EnqueueTracked(1, 0x5000, 4);
    assert(pending_older);
    const auto conditional_ok = CommitConditionalAfterRead(
        conditional, 2, 0x5000, 4,
        [&]() -> ReadBarrierResult {
            assert(conditional_ram.load() == 7);
            assert(conditional.Drain([&](unsigned core, std::uint64_t addr,
                                           std::uint64_t size) {
                assert(core == 1 && addr == 0x5000 && size == 4);
                ++prior_invalidations;
            }) == 1);
            return ReadBarrierResult::Complete;
        },
        [&]() noexcept -> StoreOutcome {
            assert(prior_invalidations == 1);
            int expected = 7;
            return conditional_ram.compare_exchange_strong(expected, 15)
                       ? StoreOutcome::Modified : StoreOutcome::Unchanged;
        }, [&]() -> bool {
            assert(conditional.Drain([&](unsigned core, std::uint64_t addr,
                                           std::uint64_t size) {
                assert(core == 2 && addr == 0x5000 && size == 4);
                assert(conditional_ram.load() == 15);
                ++conditional_invalidations;
            }) == 1);
            return true;
        });
    assert(conditional_ok == StoreOutcome::Modified &&
           prior_invalidations == 1 && conditional_invalidations == 1 &&
           conditional_ram.load() == 15 && !conditional.Pending());

    // A CAS comparison failure resolves its FIFO position WITHOUT
    // invalidation, even after a successful prerequisite CPU-read fence.
    Queue conditional_failed;
    std::atomic<int> failed_ram{8};
    unsigned failures_synced = 0, failures_replayed = 0;
    const auto conditional_noop = CommitConditionalAfterRead(
        conditional_failed, 1, 0x6000, 4,
        [&]() -> ReadBarrierResult {
            ++failures_synced;
            return ReadBarrierResult::Complete;
        },
        [&]() noexcept -> StoreOutcome {
            assert(failures_synced == 1);
            int expected = 10;
            return failed_ram.compare_exchange_strong(expected, 12)
                       ? StoreOutcome::Modified : StoreOutcome::Unchanged;
        }, [&]() -> bool {
            assert(conditional_failed.Drain([&](unsigned,std::uint64_t,std::uint64_t) {
                ++failures_replayed;
            }) == 0);
            return true;
        });
    assert(conditional_noop == StoreOutcome::Unchanged &&
           failures_synced == 1 && failures_replayed == 0 &&
           failed_ram.load() == 8 && !conditional_failed.Pending());

    // An explicitly incomplete GPU->CPU download must not reserve or
    // execute a CAS, nor mistake scheduling acceptance for read completion.
    Queue unsynced;
    unsigned forbidden_attempts = 0, forbidden_wakes = 0;
    const auto read_rejected = CommitConditionalAfterRead(
        unsynced, 0, 0x7000, 4,
        [&]() -> ReadBarrierResult { return ReadBarrierResult::Failed; },
        [&]() noexcept -> StoreOutcome {
            ++forbidden_attempts;
            return StoreOutcome::Modified;
        }, [&]() -> bool { ++forbidden_wakes; return true; });
    assert(!read_rejected && forbidden_attempts == 0 &&
           forbidden_wakes == 0 && unsynced.AcceptedSequence() == 0 &&
           !unsynced.Pending());

    // Other core's earlier unpublished reservation must not be overtaken.
    Queue ordered;
    const auto older = ordered.Reserve(1, 0x4000, 4);
    assert(older);
    std::vector<unsigned> ordered_cores;
    std::uint32_t new_value = 0;
    const auto late = CommitPostStore(ordered, 3, 0x5000, 4,
        [&]() noexcept -> StoreOutcome {
            new_value = 12345;
            return StoreOutcome::Modified;
        }, [&]() -> bool {
            ordered.Drain([&](unsigned c,std::uint64_t,std::uint64_t) {
                ordered_cores.push_back(c);
                if (c == 3) assert(new_value == 12345);
            });
            return true;
        });
    assert(late == StoreOutcome::Modified && ordered_cores.empty());
    assert(ordered.PublishAndWake(*older, [&]() -> bool {
        assert(ordered.Drain([&](unsigned c,std::uint64_t,std::uint64_t) {
            ordered_cores.push_back(c);
            if (c == 3) assert(new_value == 12345);
        }) == 2);
        return true;
    }));
    assert((ordered_cores == std::vector<unsigned>{1,3}));
    assert(!ordered.Pending());

    // Full queue forces earlier invalidations to drain BEFORE the RAM store.
    Queue full;
    for (Queue::Sequence i = 0; i < Queue::MaxOutstandingWrites; ++i)
        assert(full.EnqueueTracked(unsigned(i % Queue::Cores),
                                   0x100000 + i * 4096, 4));
    unsigned first_drain = 0, after_store_drain = 0;
    std::uint32_t full_ram = 0;
    const auto full_result = CommitPostStore(full, 0, 0x9000000, 4,
        [&]() noexcept -> StoreOutcome {
            assert(first_drain == 1 && after_store_drain == 0);
            full_ram = 99;
            return StoreOutcome::Modified;
        }, [&]() -> bool {
            if (full_ram == 0) {
                ++first_drain;
                assert(full.Drain([&](unsigned,std::uint64_t,std::uint64_t) {
                    assert(full_ram == 0);
                }) == Queue::MaxOutstandingWrites);
            } else {
                ++after_store_drain;
                assert(full.Drain([&](unsigned,std::uint64_t,std::uint64_t) {
                    assert(full_ram == 99);
                }) == 1);
            }
            return true;
        });
    assert(full_result == StoreOutcome::Modified && first_drain == 1 &&
           after_store_drain == 1 && full_ram == 99 && !full.Pending());

    // Invalid reservation must not execute a store even once.
    Queue invalid;
    unsigned skipped_store = 0;
    const auto no_ticket = CommitPostStore(invalid, Queue::Cores, 1, 8,
        [&]() noexcept -> StoreOutcome {
            ++skipped_store;
            return StoreOutcome::Modified;
        }, [] {});
    assert(!no_ticket && skipped_store == 0);

    // Rejected scheduler request after RAM mutation poisons this title.
    Queue rejected;
    int rejected_ram = 0;
    bool thrown = false;
    try {
        (void)CommitPostStore(rejected, 0, 0x7000, 4,
            [&]() noexcept -> StoreOutcome {
                rejected_ram = 42;
                return StoreOutcome::Modified;
            }, []() -> bool {return false;});
    } catch (const std::runtime_error&) { thrown = true; }
    assert(thrown && rejected_ram == 42 && rejected.Failed());
    assert(!rejected.Reserve(0, 0x8000, 4));
}
"""
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-poststore-host-") as temp:
    unit = Path(temp) / "store.cpp"
    binary = Path(temp) / "store"
    unit.write_text(cpp)
    subprocess.run([clang, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                    "-pthread", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-I", str(root / "headless"),
                    str(unit), "-o", str(binary)], check=True, timeout=45)
    subprocess.run([str(binary)], check=True, timeout=45)
print("GPU_DEFERRED_POSTSTORE_HOST_PASS ordinary=1 cancel=1 fifo=1 pressure=1 scheduler_reject=1 conditional_read_fence=1 cas_success=1 cas_failed=1 read_reject=1 no_native_activation=1")
