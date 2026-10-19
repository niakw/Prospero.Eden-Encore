bool MemoryManager::EnqueueDeferredCPUWrite(u64 address, u64 size) {
    // The native producer still enqueues BEFORE writing guest backing RAM.
    // No runtime setting may activate this until the post-store bridge exists.
    if (!::Eden::GpuDeferredWrite::kNativePostStorePublicationReady ||
        !::Eden::Performance::cpu_write_defer.load(std::memory_order_relaxed) ||
        ::Eden::GpuDeferredWrite::guest_write_intent !=
            ::Eden::GpuDeferredWrite::GuestWriteIntent::StoreFollows ||
        ::Eden::GpuDeferredWrite::replaying_guest_write) return false;
    const unsigned core = ::Eden::GpuDeferredWrite::guest_write_origin_core;
    if (core >= ::Eden::GpuDeferredWrite::Queue::Cores) return false;
    return deferred_cpu_write_queue.Enqueue(core, address, size);
}
void MemoryManager::FlushCaching() {
    // A failed replay may have partially modified cache state. Never allow
    // a later GPU command to proceed through this developer-only bridge.
    if (deferred_cpu_write_queue.Failed()) std::terminate();
    if (deferred_cpu_write_queue.Pending()) {
        ::Eden::GpuDeferredWrite::ScopedReplay replay_guard;
        auto dirty = system.GetGPUDirtyMemoryManager();
        ::Eden::GpuDeferredWrite::ReplayQueued(deferred_cpu_write_queue,
            [&](std::uint64_t address, std::uint64_t size) {
                return rasterizer->OnCPUWrite(address, size);
            },
            [&](unsigned core, std::uint64_t address, std::uint64_t size) {
                dirty[core].Collect(address, size);
            });
    }
