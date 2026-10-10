// SPDX-License-Identifier: GPL-3.0-or-later
// Host-side registry model of the pinned PS5 GPU ASID lifetime protocol.
// NOT the entire Eden DeviceMemoryManager or a native PS5 build.
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <vector>

namespace {
constexpr std::size_t kDeviceSize = std::size_t{1} << 39;
constexpr std::size_t kMaxIDs = std::size_t{1} << (64 - 39);

struct Process {
    std::atomic<std::uint64_t> touches{0};
    std::uint64_t cookie = UINT64_C(0xBEDA77ED);
};

class Registry {
public:
    std::size_t RegisterProcess(Process* p) {
        std::unique_lock lock(guard);
        if (p == nullptr || entries.size() >= kMaxIDs)
            return std::size_t(-1);
        entries.emplace_back(p);
        return entries.size() - 1;
    }
    void UnregisterProcess(std::size_t id) {
        std::unique_lock lock(guard);
        if (id >= entries.size() || entries[id] == nullptr) return;
        entries[id] = nullptr;  // tombstone; NEVER recycle
    }
    bool Map(std::size_t id, std::size_t address, std::size_t size) {
        if (size == 0 || address >= kDeviceSize || size > kDeviceSize - address)
            return false;
        std::shared_lock lock(guard);
        if (id >= entries.size() || entries[id] == nullptr) return false;
        auto* process = entries[id];
        assert(process->cookie == UINT64_C(0xBEDA77ED));
        process->touches.fetch_add(1, std::memory_order_relaxed);
        return true;
    }
    bool Cache(std::size_t id, std::size_t address, std::size_t size) {
        if (size == 0 || address >= kDeviceSize || size > kDeviceSize - address)
            return false;
        std::shared_lock lock(guard);
        if (id >= entries.size() || entries[id] == nullptr) return false;
        auto* process = entries[id];
        assert(process->cookie == UINT64_C(0xBEDA77ED));
        process->touches.fetch_add(1, std::memory_order_relaxed);
        return true;
    }
    std::size_t Slots() {
        std::shared_lock lock(guard);
        return entries.size();
    }
private:
    std::shared_mutex guard;
    std::deque<Process*> entries;
};
}

int main() {
    Registry reg;
    Process first{};
    const auto old = reg.RegisterProcess(&first);
    assert(old == 0);
    assert(reg.Map(old, 0, 4096));
    reg.UnregisterProcess(old);
    reg.UnregisterProcess(old); // idempotent
    assert(!reg.Map(old, 0, 4096));
    Process second{};
    const auto next = reg.RegisterProcess(&second);
    assert(next != old);  // retired ID cannot alias a newly registered process
    assert(!reg.Map(old, 0, 4096));
    assert(!reg.Map(std::size_t(-1), 0, 4096));
    assert(!reg.Cache(std::size_t(-1), 0, 4096));
    assert(!reg.Cache(next, kDeviceSize, 4096));
    assert(!reg.Map(next, kDeviceSize - 1, 2)); // overflow of allowed range
    assert(!reg.Map(next, 0, 0));
    assert(reg.Map(next, kDeviceSize - 1, 1));
    reg.UnregisterProcess(next);

    std::atomic<std::size_t> published{std::size_t(-1)};
    constexpr int kCycles = 3500;
    std::thread producer([&] {
        for (int n = 0; n < kCycles; ++n) {
            auto process = std::make_unique<Process>();
            auto id = reg.RegisterProcess(process.get());
            assert(id != std::size_t(-1));
            published.store(id, std::memory_order_release);
            (void)reg.Map(id, 0, 4096);
            reg.UnregisterProcess(id);  // waits for every active shared reader
            process.reset();            // no reader can access after unregister
        }
        published.store(std::size_t(-1), std::memory_order_release);
    });
    std::vector<std::thread> readers;
    for (int worker = 0; worker < 5; ++worker) {
        readers.emplace_back([&] {
            for (int i = 0; i < kCycles * 3; ++i) {
                auto id = published.load(std::memory_order_acquire);
                (void)reg.Map(id, 0, 128);
                (void)reg.Cache(id, 4096, 4096);
                (void)reg.Map(id, kDeviceSize - 1, 32);
            }
        });
    }
    producer.join();
    for (auto& t : readers) t.join();
    assert(reg.Slots() == std::size_t(kCycles) + 2);
    assert(!reg.Map(2, 0, 4096));
    std::cout << "PASS PS5 GPU ASID registry model: no reuse/UAF; 6 threads, "
              << kCycles << " registrations, strict address range checks\n";
}
