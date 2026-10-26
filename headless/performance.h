// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <optional>
#include "common/cpu_features.h"

namespace Eden::Performance {
void RegisterWorker(const char* name);
// One-shot read-only PS5 scheduler and cpuset evidence for Vulkan workers.
void ProbeSchedulerOnce(const char* role) noexcept;
// Development: keep other named threads off guest cores 0-2 and their SMT siblings.
void SetSecondaryPlacement(bool enabled);
// Which logical slots are already dedicated to guest CPU/GPU workers.
// Zero means topology is unproven; shader scheduling must reserve
// conservatively instead of assuming that an affinity mask is secondary.
std::uint64_t PinnedWorkerMask() noexcept;
// Actual kernel-verified logical-secondary affinity inherited by shader
// compiler threads. This is NOT proof of distinct physical/SMT cores.
std::uint64_t VerifiedSecondaryPlacementMask() noexcept;
// Explicit PS5 diagnostic A/B: spread workers across distinct OS logical CPUs,
// without claiming separate physical cores when firmware CPUID is unreliable.
void EnableExperimentalLogicalPlacement();
void PlatformChecks();
// One kernel query at guest start, not in the per-frame performance path.
bool QueryLargestDirectMemoryBlock(std::size_t* largest) noexcept;
// A PS5 app hosts many titles in one process. After all renderer workers
// have joined, invalidate kernel free-block observations from the old title.
// This does NOT free direct memory or change its kernel-exposed extent.
void ResetDirectMemoryProbeForTitle() noexcept;
// Startup/shutdown-only snapshot: no direct-memory region scan in the frame loop.
void ReportDirectMemoryState(const char* phase);
// The 8192-call native kernel region walk is expensive and diagnostic-only.
// Opt in with memory-region-scan.txt; always keep cheap owner/largest-free data.
void SetDirectMemoryRegionScanEnabled(bool enabled) noexcept;
// Lightweight per-stage actual Dynarmic RX/RW ownership; no kernel VA
// enumeration or GPU frame-loop work.
void ReportJitCodeState(const char* phase);
// Serialized main-thread capture or five-second GPU diagnostic snapshot.
// Costly PC processing must never hold the guest CPU worker publication mutex.
void Snapshot();
// GPU worker only: firmware rejects cross-thread CPU-time sampling.
void SampleGpuFrame(unsigned frame);
#ifdef EDEN_DEV_PROFILE
void BeginPcSampling();
void PollGpuPc();
// Development: A64 block compilation split into translate, optimize, emit and the emitter's
// block-range registration (part of emit), per guest core, in nanoseconds.
inline std::array<std::array<std::atomic<unsigned long long>, 4>, 4> jit_phase_ns{};
// Development: A64 blocks per guest core that no core had compiled before, that this core had
// compiled before (after an invalidation), and that another core compiled first, by how long
// before: under 1 ms, 10 ms, 100 ms, 1 s, 10 s, and later. Counted only with dev-settings
// jit_dups=on (a process-wide lock and map insert per compiled block).
inline std::array<std::array<std::atomic<unsigned long long>, 8>, 4> jit_duplicates{};
inline std::atomic<bool> jit_duplicate_tracking{false};
// Only nonempty, applied standard-A64 invalidations in detailed DEV:
// 0=whole code cache, 1=coalesced partial-range batch.
inline std::array<std::array<std::atomic<unsigned long long>, 2>, 4> jit_cache_events{};
// Called before the next title starts, after the previous guest workers joined.
void ResetJitDuplicateTrackingForTitle() noexcept;
// Guest core whose host PCs the development sampler collects (dev-settings pc_core=N, default 0).
inline std::atomic<unsigned> pc_sample_core{0};
// Development: sample that core at ~500 Hz from its registration (dev-settings pc_fast=on).
inline std::atomic<bool> pc_fast{false};
// Development: honour capture-once.txt from a session's first 30 s segment instead of its fifth
// (dev-settings capture=early; the runner's lifecycle returns need a capture within ~80 s).
inline std::atomic<bool> capture_early{false};
// Development: keep Eden's default library applets, which start some from the firmware
// (dev-settings applets=firmware). The port otherwise uses the built-in ones (main.cpp).
inline std::atomic<bool> firmware_applets{false};
#endif
// One writer per guest core. JIT state is read only by its owning worker after Run.
enum class CpuPhase : unsigned { Kernel, Guest, Idle };
struct alignas(64) CpuState { std::atomic<CpuPhase> phase{}; };
inline std::array<CpuState, 4> cpu_state{};
// Caller checks the epoch before resolving the guest thread ID, avoiding a
// kernel lookup on every diagnostic JIT transition. Worker-owned only.
bool CpuSampleDue(unsigned core) noexcept;
void SampleCpu(unsigned core, unsigned long long thread, unsigned long long pc, unsigned svc, unsigned fpcr);
struct alignas(64) Totals {
    std::atomic<unsigned long long> calls{}, nanoseconds{}, requested_bytes{};
};
// Unmapped guest memory is an error, but an invalid guest pointer can produce
// tens of thousands of reports within a single second. Those synchronous
// format/write operations steal time from the three PS5 guest CPU workers.
// Keep the first 64 reports and one power-of-two progress report thereafter.
// This changes ONLY diagnostics, never memory access permission/result.
inline std::atomic<std::uint64_t> unmapped_access_count{0};
inline bool ShouldLogUnmappedAccess() noexcept {
    const std::uint64_t n = unmapped_access_count.fetch_add(1, std::memory_order_relaxed) + 1;
    return n <= 64 || (n & (n - 1)) == 0;
}
inline void ResetUnmappedAccessCount() noexcept {
    unmapped_access_count.store(0, std::memory_order_relaxed);
}
inline std::array<Totals, 4> compilation;
inline std::array<std::atomic<unsigned long long>, 4> evacuations{};
inline Totals storage;
inline Totals jit_protection;
inline Totals rasterizer_draw;
inline Totals gpu_queue_wait, gpu_dispatch;
// Classify long-running GPU worker commands only with Detailed Logging ON.
// GPU submit is already recorded in gpu_dispatch; the other commands must
// not be misattributed to shader compilation or guest JIT.
inline Totals gpu_command_tick, gpu_command_flush, gpu_command_invalidate;
// R405: GPU-owner DmaPusher fence-wait intervals INSIDE Scheduler::Push.
// Detailed logging only; not physical GPU utilization or a guest timing fix.
inline Totals gpu_dma_sync_wait, gpu_puller_semaphore_wait;
// GPU-owned live wait slots, independently readable from the compositor.
// Zero means no outstanding profiled wait. Do not use these as watchdogs or
// alter the guest command's lifetime/order based on diagnostic counters.
inline std::atomic<long long> gpu_dma_sync_active_since_ns{0};
inline std::atomic<long long> gpu_puller_semaphore_active_since_ns{0};
// Counts actual 4-KiB command-chunk pre-dispatches (R382), not ordinary
// DispatchWork calls. Written only on a successful preflight when profiling.
inline std::atomic<unsigned long long> scheduler_preflight_dispatches{0};
// Producer-side waits outside the dispatch timer: forced fence drains on the GPU
// thread, free presentation-frame waits, and guest pushes into a full GPU queue.
inline Totals gpu_fence_drain, gpu_present_wait, gpu_queue_full;
// R424: isolate presenter FIFO starvation from recycled-frame GPU fence stalls.
// Sampled only when Detailed Logging is ON, never during normal gameplay.
inline Totals gpu_present_free_wait, gpu_present_fence_wait;
// Guest threads entering the GPU caches: CPU writes to tracked pages and flush-area lookups.
inline Totals guest_cpu_write, guest_cpu_read;
// Upstream #187 write-ahead candidate: only mark subsequent registered buffer
// pages after a successful OnCPUWrite under the buffer-cache mutex. This is
// not deferred-write replay. Default OFF pending native title qualification.
inline std::atomic<unsigned> cpu_write_ahead{0};
// Bridge is source-only; no normal build or dev option enables this automatically.
inline std::atomic<bool> cpu_write_defer{false};
// Those entries take the buffer and texture cache locks, which the GPU thread holds for one draw at
// a time. Shipping builds block exactly as upstream: the earlier bounded spin reduced wake latency
// but remains a development-only experiment until it is requalified against PS5 soft hangs.
// dev-settings cache_spin=N can still opt into bounded try_lock retries for profiling.
inline std::atomic<unsigned> cache_lock_spins{0};
inline std::atomic<bool> detailed_gpu_profile{false};
inline std::atomic<unsigned long long> cache_lock_contended{0}, cache_lock_blocked{0};
// Accumulated time actually blocked on the guest cache mutex, not just
// number of failed try_lock attempts. Updated ONLY during detailed profiling.
inline std::atomic<unsigned long long> cache_lock_wait_ns{0};
// The old aggregate hides whether CPU writes block on the graphics buffer
// cache or the texture cache. Only count when detailed diagnostics are active.
struct GuestCacheDomainTotals {
    std::atomic<unsigned long long> contended{}, blocked{}, wait_ns{};
    // Exact completed waits above 1/10 ms, plus largest wait since snapshot.
    // Never touched in quiet gameplay; high-threshold diagnostics only.
    std::atomic<unsigned long long> waited_ge1ms{}, waited_ge10ms{}, max_wait_ns{};
};
inline std::array<GuestCacheDomainTotals, 2> guest_cache_domain_totals{}; // buffer, texture
template <typename Mutex>
inline void GuestCacheLock(Mutex& mutex, bool texture_domain = false) {
    // Source of thousands of contended-cache atomic writes in FC27. When
    // diagnostics are OFF use the exact upstream blocking mutex path; do not
    // try_lock first or hammer two shared accounting cache lines per miss.
    // This changes instrumentation, NOT GPU/guest lock ownership or order.
    if (!detailed_gpu_profile.load(std::memory_order_relaxed)) {
        mutex.lock();
        return;
    }
    if (mutex.try_lock()) return;
    auto& domain = guest_cache_domain_totals[texture_domain ? 1u : 0u];
    cache_lock_contended.fetch_add(1, std::memory_order_relaxed);
    domain.contended.fetch_add(1, std::memory_order_relaxed);
    for (unsigned tries = cache_lock_spins.load(std::memory_order_relaxed); tries != 0; --tries) {
        for (int pause = 0; pause < 4; ++pause) __builtin_ia32_pause();
        if (mutex.try_lock()) return;
    }
    cache_lock_blocked.fetch_add(1, std::memory_order_relaxed);
    domain.blocked.fetch_add(1, std::memory_order_relaxed);
    const auto blocked_start = Common::g_wall_clock.GetTimeNS();
    mutex.lock();
    const auto waited = (Common::g_wall_clock.GetTimeNS() - blocked_start).count();
    if (waited > 0) {
        cache_lock_wait_ns.fetch_add(static_cast<unsigned long long>(waited),
                                     std::memory_order_relaxed);
        domain.wait_ns.fetch_add(static_cast<unsigned long long>(waited),
                                 std::memory_order_relaxed);
        if (waited >= 1'000'000) {
            domain.waited_ge1ms.fetch_add(1, std::memory_order_relaxed);
            if (waited >= 10'000'000)
                domain.waited_ge10ms.fetch_add(1, std::memory_order_relaxed);
            const auto elapsed = static_cast<unsigned long long>(waited);
            auto old_max = domain.max_wait_ns.load(std::memory_order_relaxed);
            while (old_max < elapsed &&
                   !domain.max_wait_ns.compare_exchange_weak(
                       old_max, elapsed, std::memory_order_relaxed)) {}
        }
    }
}
// R310: sampled GPU-owner cache phases.  A successful FPS average does not
// explain a late frame; measure how much of each 16th draw is waiting for the
// cache pair, configuring images/buffers/descriptors, or recording commands.
// Detailed Logging ONLY. The quiet path does not touch clocks or counters.
// All phase measurements are nested inside the ORIGINAL cache locks; this
// code changes neither memory ownership nor draw/fence ordering.
enum class CachePhase : unsigned {
    PairWait, PairHeld, PipelineConfigure, TextureDescriptorSync,
    TextureFillImageViews, GraphicsBufferUpdate, DescriptorQueueAcquire,
    DynamicStates, QueryAndDraw,
    TextureCpuRefresh, TextureAliasScan, TextureAliasCopy,
    StageTextureHandles, BindTextureBuffers, BindStageDescriptors,
    StageHostBuffers, StageImageDescriptors,
    RefreshRenderTargets, CheckFeedbackLoop, CommitGraphicsDraw, DescriptorRingFinish, DescriptorRingPreflight,
    GuestWriteBufferWait, GuestWriteBufferWork, GuestWriteTextureWait,
    GuestWriteTextureWork, GuestWriteShaderInvalidate,
    GraphicsPipelineCreate, ShaderPoolReset, ShaderCfg, ShaderIr,
    ShaderSpirv, ShaderModule, GraphicsPipelineWait, ComputePipelineWait,
    TextureUploadStaging, TextureUploadContents,
    TextureUploadBarrier, Count
};
struct CachePhaseTotal {
    std::atomic<unsigned long long> samples{}, total_ns{}, max_ns{};
};
inline std::array<CachePhaseTotal, static_cast<unsigned>(CachePhase::Count)> cache_phase_totals{};
inline thread_local bool cache_draw_sample_active = false;
inline bool ShouldSampleCacheDraw() noexcept {
    if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return false;
    static thread_local unsigned sequence = 0;
    // Sampling avoids injecting high-frequency clock calls into the render path.
    return (++sequence & 15u) == 0u;
}
inline bool ShouldSampleGuestWrite() noexcept {
    if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return false;
    static thread_local unsigned sequence = 0;
    // One in 64 guest CPU-write callbacks, independent of the GPU-owner
    // per-16 draw sequence. An entire callback shares the same sample flag.
    return (++sequence & 63u) == 0u;
}
class CachePhaseTimer {
public:
    explicit CachePhaseTimer(CachePhase phase, bool enabled = cache_draw_sample_active)
        : stats(enabled ? &cache_phase_totals[static_cast<unsigned>(phase)] : nullptr) {
        if (stats) started = Common::g_wall_clock.GetTimeNS();
    }
    CachePhaseTimer(const CachePhaseTimer&) = delete;
    CachePhaseTimer& operator=(const CachePhaseTimer&) = delete;
    void Stop() noexcept {
        if (!stats) return;
        const auto elapsed = (Common::g_wall_clock.GetTimeNS() - started).count();
        if (elapsed > 0) {
            const auto ns = static_cast<unsigned long long>(elapsed);
            stats->total_ns.fetch_add(ns, std::memory_order_relaxed);
            auto previous = stats->max_ns.load(std::memory_order_relaxed);
            while (previous < ns &&
                   !stats->max_ns.compare_exchange_weak(
                       previous, ns, std::memory_order_relaxed)) {}
        }
        stats->samples.fetch_add(1, std::memory_order_relaxed);
        stats = nullptr;
    }
    ~CachePhaseTimer() { Stop(); }
private:
    CachePhaseTotal* stats{};
    std::chrono::nanoseconds started{};
};
// R361: Count draws rejected before recording, including hidden HUD/pitch
// candidates. Only increment on an actual rejected draw with diagnostics on.
// In particular no atomic writes are added to the normal successful draw path.
enum class GraphicsDrawDrop : unsigned {
    NoPipeline, ConfigureRejected, BuiltPipelineFailed, DescriptorBufferFull,
    WorkerPipelineFailed, Count
};
inline std::array<std::atomic<unsigned long long>,
                  static_cast<unsigned>(GraphicsDrawDrop::Count)> graphics_draw_drop_totals{};
inline void RecordGraphicsDrawDrop(GraphicsDrawDrop reason) noexcept {
    if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return;
    graphics_draw_drop_totals[static_cast<unsigned>(reason)].fetch_add(
        1, std::memory_order_relaxed);
}
inline void ResetCachePhases() noexcept {
    for (auto& drop : graphics_draw_drop_totals)
        drop.store(0, std::memory_order_relaxed);
    for (auto& s : cache_phase_totals) {
        s.samples.store(0, std::memory_order_relaxed);
        s.total_ns.store(0, std::memory_order_relaxed);
        s.max_ns.store(0, std::memory_order_relaxed);
    }
}

// Guest waits: nvhost_ctrl syncpoint event registration -> signal, and
// BufferQueueProducer::DequeueBuffer waiting for a free buffer slot.
inline Totals guest_sync_wait, guest_dequeue_wait;
// F05: a hung producer never returns from DequeueBuffer, so completed-call
// timers stay flat. Count *currently* blocked host dequeuers separately.
// Multi-producer safe; only an actual wait updates this count, and only
// with detailed profiling enabled. No guest scheduling or queue semantics
// change. One diagnostic count is not a per-thread/guest PC proof.
inline std::atomic<unsigned> guest_dequeue_blocked{};
class GuestDequeueBlockedScope {
public:
    GuestDequeueBlockedScope() noexcept
        : enabled(detailed_gpu_profile.load(std::memory_order_relaxed)) {
        if (enabled) guest_dequeue_blocked.fetch_add(1, std::memory_order_acq_rel);
    }
    GuestDequeueBlockedScope(const GuestDequeueBlockedScope&) = delete;
    GuestDequeueBlockedScope& operator=(const GuestDequeueBlockedScope&) = delete;
    ~GuestDequeueBlockedScope() {
        if (enabled) guest_dequeue_blocked.fetch_sub(1, std::memory_order_acq_rel);
    }
private:
    bool enabled{};
};
// fsp-srv IFile/IStorage reads (guest asset streaming): time in the backend and bytes.
inline Totals guest_fs_file, guest_fs_storage;
inline std::atomic<unsigned long long> guest_fs_file_bytes{}, guest_fs_storage_bytes{};
// Guest svcSendSyncRequest latency (queueing + HLE handling), and HLE handling time per
// service command (RecordHle, reported as EDEN_DEV_HLE).
inline Totals guest_ipc_wait;
// R393: bounded attribution of synchronous guest IPC waits. Only invoked
// when detailed GPU profiling is active; no allocation, string lookup,
// blocking lock or per-request log on the hot path.
// FC27 R394 observed >63k unattributed calls in 9m32s once 128 TIDs filled.
// 1024 slots cost only ~32 KiB; fixed bounded probing avoids O(1024)
// per-call scans after high thread churn. Diagnostics only.
inline constexpr unsigned guest_ipc_thread_slots = 1024;
inline constexpr unsigned guest_ipc_max_probes = 64;
struct GuestIpcThread {
    std::atomic<unsigned long long> tid{}, calls{}, ns{}, max_ns{};
    // A completed-call profiler alone cannot see an IPC which never returns.
    // Guest-thread ownership is unique; zero means no observed in-flight call.
    std::atomic<long long> active_since_ns{};
};
inline std::array<GuestIpcThread, guest_ipc_thread_slots> guest_ipc_threads{};
inline std::array<std::atomic<unsigned long long>, 4> guest_ipc_hist{};
inline std::atomic<unsigned long long> guest_ipc_overflow_calls{};
inline GuestIpcThread* FindGuestIpcThread(unsigned long long tid) noexcept {
    if (tid == 0) return nullptr;
    unsigned slot = static_cast<unsigned>(tid % guest_ipc_thread_slots);
    for (unsigned n = 0; n < guest_ipc_max_probes; ++n) {
        auto& row = guest_ipc_threads[slot];
        auto found = row.tid.load(std::memory_order_relaxed);
        if (found == 0) {
            unsigned long long expected = 0;
            found = row.tid.compare_exchange_strong(expected, tid, std::memory_order_relaxed)
                        ? tid : expected;
        }
        if (found == tid) return &row;
        slot = (slot + 1u) % guest_ipc_thread_slots;
    }
    return nullptr;
}
// Diagnostic-only caller (gated by detailed_gpu_profile). Never allocates,
// holds an emulator lock, or changes synchronous service IPC semantics.
inline GuestIpcThread* BeginGuestIpc(unsigned long long tid, long long started_ns) noexcept {
    auto* row = FindGuestIpcThread(tid);
    if (row && started_ns > 0) {
        long long empty = 0;
        row->active_since_ns.compare_exchange_strong(
            empty, started_ns, std::memory_order_release, std::memory_order_relaxed);
    }
    return row;
}
inline void CountGuestIpc(GuestIpcThread* row, long long elapsed_ns) noexcept {
    const auto ns = static_cast<unsigned long long>(elapsed_ns > 0 ? elapsed_ns : 0);
    guest_ipc_wait.nanoseconds.fetch_add(ns, std::memory_order_relaxed);
    guest_ipc_wait.calls.fetch_add(1, std::memory_order_relaxed);
    guest_ipc_hist[ns < 50'000 ? 0u : ns < 500'000 ? 1u : ns < 5'000'000 ? 2u : 3u]
        .fetch_add(1, std::memory_order_relaxed);
    if (row) {
        row->calls.fetch_add(1, std::memory_order_relaxed);
        row->ns.fetch_add(ns, std::memory_order_relaxed);
        auto previous = row->max_ns.load(std::memory_order_relaxed);
        while (previous < ns && !row->max_ns.compare_exchange_weak(
                   previous, ns, std::memory_order_relaxed)) {}
    } else {
        guest_ipc_overflow_calls.fetch_add(1, std::memory_order_relaxed);
    }
}
// Preserve the existing standalone completed-IPC contract used by host tests.
inline void RecordGuestIpc(unsigned long long tid, long long elapsed_ns) noexcept {
    CountGuestIpc(FindGuestIpcThread(tid), elapsed_ns);
}
inline void FinishGuestIpc(GuestIpcThread* row, unsigned long long tid,
                           long long started_ns, long long elapsed_ns) noexcept {
    CountGuestIpc(row ? row : FindGuestIpcThread(tid), elapsed_ns);
    if (row && started_ns > 0) {
        // Only clear this invocation's pending timestamp. A nested/older IPC
        // cannot be mistaken for this completion.
        long long expected = started_ns;
        row->active_since_ns.compare_exchange_strong(
            expected, 0, std::memory_order_release, std::memory_order_relaxed);
    }
}
void RecordHle(const char* service, unsigned command, long long ns);
// kspin=N: bounded host mutex acquisition used for guest scheduler locks.
inline std::atomic<unsigned> kernel_spin_iterations{4000};
template <typename Mutex>
inline void SpinAcquire(Mutex& mutex) {
    const unsigned spins = kernel_spin_iterations.load(std::memory_order_relaxed);
    for (unsigned i = 0; i < spins; ++i) {
        if (mutex.try_lock()) return;
        __builtin_ia32_pause();
    }
    mutex.lock();
}

inline long long NowNs() { return Common::g_wall_clock.GetTimeNS().count(); }
// Texture cache garbage collection (tools/prepare-vulkan-port.py, vulkan_gc_downloads.inc).
// Past its "expected" memory use Eden's collector also evicts images the GPU wrote, and each of
// those is first copied back to guest memory behind a wait for the GPU. On the console a large
// open-world game sat just past that mark (4.8 GiB against 4.5 with the FSR filter's images):
// entering gameplay took ten seconds at 3-9 FPS (15 collector runs took 4.6 s of one 5 s window)
// and frames of 70-115 ms kept coming. Those images are now kept, as they are below the mark,
// until memory is really short: use reaches the "critical" mark, or the largest free block of
// direct memory (what the next allocation needs) is under kShortMemory.
// dev-settings gc_dirty=upstream restores Eden's rule.
inline std::atomic<bool> gc_keep_dirty{true};
// R439: old visits budget can be restored with dev-settings gc_scan=upstream.
inline std::atomic<bool> gc_count_visits{false};
inline std::atomic<bool> graphics_memory_short{false};
inline constexpr std::size_t kShortMemory = std::size_t{384} << 20;
// Development: the texture cache reports its memory use and marks every 300 frames.
inline std::atomic<bool> texture_budget_log{false};
// Native DEV: expensive GPU-thread/HLE/CPU-snapshot reporting is opt-in.
// The lightweight frame-pacing counters still run in quiet gameplay.
// Reset per title, rather than inheriting a prior game's diagnostic session.

// "Is memory short?", installed by the PS5 build (performance.cpp, GraphicsMemoryShort). This
// header is compiled into libraries with and without PS5_NATIVE, so the function below must read
// the same in all of them: the platform part is behind this pointer, not behind an #ifdef.
inline std::atomic<bool (*)()> graphics_memory_probe{nullptr};
// Graphics memory still free: the largest block of the direct memory pool, which is what the
// driver's next allocation can be given. Installed by the PS5 build (performance.cpp).
//
// The texture and buffer caches decide what to evict from "memory in use" against a budget. On
// the console that figure is the budget less this free block (tools/prepare-vulkan-port.py,
// Device::GetDeviceMemoryUsage), not the driver's own count, for two reasons. The CPU and the
// GPU share one pool, so what limits graphics is what is left of it, whoever took the rest; and
// the driver reports its allocations twice over (as VRAM and as visible VRAM), which made the
// caches evict at half the use they were set to. dev-settings graphics_usage=driver restores
// the driver's count.
inline std::atomic<unsigned long long (*)()> graphics_memory_free{nullptr};
inline std::atomic<bool> graphics_usage_from_pool{true};
// GPU thread only (the collector).
inline bool KeepDirtyTextures() {
    if (!gc_keep_dirty.load(std::memory_order_relaxed)) return false;
    const auto probe = graphics_memory_probe.load(std::memory_order_relaxed);
    return !probe || !probe();
}
// 1.5ms compose delay after signaling guest VSync (compose_delay_us=0 restores upstream).
inline std::atomic<int> compose_delay_us{1500};
// Development boot trace (dev-settings boot_trace=START:END, milliseconds after the settings
// are read): guest GPU submissions and GPU-thread dispatches inside it are logged one by one.
inline std::atomic<long long> boot_trace_begin{0}, boot_trace_end{0};
// dev-settings fs_callers=on: log the guest caller of each IFileSystem request (its backtrace
// walk delays that request by ~0.1 s, so it is off unless asked for).
inline std::atomic<bool> trace_fs_callers{false};
// Maxwell render-enable evaluations (Maxwell3D::ProcessQueryCondition): [0] host conditional
// rendering, [1]/[2] always/never overrides, [3 + mode * 2 + result] per render_enable mode
// (False, True, Conditional, IfEqual, IfNotEqual) and the CPU-evaluated result. With
// VK_EXT_conditional_rendering, the host path's decisions (tools/prepare-vulkan-port.py): [13] CPU
// evaluation, [14] drawn unconditionally, [15] predicate read from one value, [16] compute
// compare, [17]/[18] hcr=cpu constant predicate draw/skip, [19] hcr=exact pending-query fallback.
inline std::array<std::atomic<unsigned long long>, 20> render_conditions{};
// Guest core idle waits (PhysicalCore::Idle): calls, nanoseconds until the
// interrupt, and calls that went to sleep because nothing arrived while spinning.
struct IdleCounters {
    std::atomic<unsigned long long> calls{0}, nanoseconds{0}, sleeps{0};
};
inline std::array<IdleCounters, 4> guest_idle{};
// PAUSE iterations a guest core spins on its interrupt flag before sleeping (~20 ns each on the
// console). Guest job systems hand work between cores ~150 times a frame; sleeping on each
// handoff put the host's thread wake-up latency on the critical path. 100 us (the default) took
// a racing game's heavy phase from ~55 to ~59.6 FPS; dev-settings
// idle_spin_us=N overrides it (0 sleeps at once).
inline std::atomic<unsigned> idle_spin_iterations{25000};
// R355: 16 draws between Vulkan worker hand-offs instead of 8. FC27 measured
// ~1,000-2,000 dispatches per five-second window with an otherwise idle GPU
// owner; halving dispatch submissions keeps the same hard 512-draw flush bound.
// The guest-visible command order and all texture/buffer synchronization remain
// unchanged. 8 is still available with dev-settings dispatch_draws=8.
// This is a candidate optimization, not a measured PS5 FPS improvement.
inline std::atomic<unsigned> dispatch_mask{15};
inline void CountIdle(std::size_t core, long long nanoseconds, bool slept) {
    // A quiet release must not bounce the guest-core counter cache lines on
    // every HLE idle/wake cycle. These statistics are diagnostic only.
    if (!detailed_gpu_profile.load(std::memory_order_relaxed) ||
        core >= guest_idle.size()) return;
    guest_idle[core].calls.fetch_add(1, std::memory_order_relaxed);
    guest_idle[core].nanoseconds.fetch_add(static_cast<unsigned long long>(nanoseconds), std::memory_order_relaxed);
    if (slept) guest_idle[core].sleeps.fetch_add(1, std::memory_order_relaxed);
}
// Development: reads 32-bit guest words for code dumps (installed by the frontend per session).
inline bool (*guest_read32)(unsigned long long address, unsigned& value) = nullptr;
inline void CountCondition(unsigned slot) {
    // Conditional-rendering decision counts are never needed to draw a frame.
    if (!detailed_gpu_profile.load(std::memory_order_relaxed) ||
        slot >= render_conditions.size()) return;
    render_conditions[slot].fetch_add(1, std::memory_order_relaxed);
}
inline bool BootTrace() {
    const auto end = boot_trace_end.load(std::memory_order_relaxed);
    if (end == 0) return false;
    const auto now = NowNs();
    return now >= boot_trace_begin.load(std::memory_order_relaxed) && now < end;
}
inline void AddSince(Totals& totals, long long start) {
    totals.nanoseconds.fetch_add(static_cast<unsigned long long>(NowNs() - start), std::memory_order_relaxed);
    totals.calls.fetch_add(1, std::memory_order_relaxed);
}
// A32/A64 memory accesses that left JIT code through the C++ callback (tracked,
// unmapped or misaligned pages, exclusive stores). Written only by the owning core.
struct alignas(64) JitCallbacks {
    std::atomic<unsigned long long> reads{}, writes{}, exclusive_writes{};
};
inline std::array<JitCallbacks, 4> jit_callbacks{};
inline void CountJit(std::atomic<unsigned long long>& counter) {
    // A32 memory callbacks can run extremely often. Development counters
    // must not bounce shared cache lines with Detailed Logging turned off.
    if (detailed_gpu_profile.load(std::memory_order_relaxed))
        counter.fetch_add(1, std::memory_order_relaxed);
}
// GPU thread only (Vulkan frame report): cumulative GPU-thread idle/dispatch/wait
// totals with the owner's CPU clock, then a guest-core CPU snapshot.
// Once per title, after the previous GPU owner has joined. Do not report
// the preceding title's last GPU frame as a freeze in this session.
void ResetGpuReportForTitle() noexcept;
void ReportGpuThread(unsigned frame);
inline std::atomic<unsigned> capture_passes{};

class Timer {
public:
    explicit Timer(Totals& target, unsigned long long bytes = 0)
        : totals(target), requested_bytes(bytes), start(Common::g_wall_clock.GetTimeNS()) {}
    Timer(const Timer&) = delete;
    Timer& operator=(const Timer&) = delete;
    ~Timer() {
        const auto elapsed = (Common::g_wall_clock.GetTimeNS() - start).count();
        totals.nanoseconds.fetch_add(static_cast<unsigned long long>(elapsed), std::memory_order_relaxed);
        if (requested_bytes) totals.requested_bytes.fetch_add(requested_bytes, std::memory_order_relaxed);
        totals.calls.fetch_add(1, std::memory_order_relaxed);
    }
private:
    Totals& totals;
    unsigned long long requested_bytes;
    std::chrono::nanoseconds start;
};

// GPU/guest waits can execute many thousands of times per second. A normal
// game must never sample two wall clocks or update global Totals for each
// dispatch/lock solely because the binary was compiled as EDEN_DEV_PROFILE.
// Expensive per-command timing is only active with Detailed Logging.
class DiagnosticTimer {
public:
    explicit DiagnosticTimer(Totals& target) noexcept
        : totals(detailed_gpu_profile.load(std::memory_order_relaxed) ? &target : nullptr) {
        if (totals) start = Common::g_wall_clock.GetTimeNS();
    }
    DiagnosticTimer(const DiagnosticTimer&) = delete;
    DiagnosticTimer& operator=(const DiagnosticTimer&) = delete;
    ~DiagnosticTimer() {
        if (!totals) return;
        const auto elapsed = (Common::g_wall_clock.GetTimeNS() - start).count();
        totals->nanoseconds.fetch_add(static_cast<unsigned long long>(elapsed),
                                      std::memory_order_relaxed);
        totals->calls.fetch_add(1, std::memory_order_relaxed);
    }
private:
    Totals* totals{};
    std::chrono::nanoseconds start{};
};

// R406: a blocking DMA or puller semaphore may never return during a freeze.
// DiagnosticTimer only counts completed calls. Publish an active timestamp
// without a per-iteration probe, and clear it on every normal/scope exit.
// GPU-owner single-writer; five-second presenter may read concurrently.
class DiagnosticActiveTimer {
public:
    DiagnosticActiveTimer(Totals& target, std::atomic<long long>& active_slot,
                          bool waiting = true) noexcept
        : totals(waiting && detailed_gpu_profile.load(std::memory_order_relaxed) ? &target : nullptr),
          active(totals ? &active_slot : nullptr) {
        if (totals) {
            start = Common::g_wall_clock.GetTimeNS();
            active->store(start.count(), std::memory_order_release);
        }
    }
    DiagnosticActiveTimer(const DiagnosticActiveTimer&) = delete;
    DiagnosticActiveTimer& operator=(const DiagnosticActiveTimer&) = delete;
    ~DiagnosticActiveTimer() {
        if (!totals) return;
        const auto end = Common::g_wall_clock.GetTimeNS();
        const auto delta = end - start;
        if (delta.count() > 0)
            totals->nanoseconds.fetch_add(static_cast<unsigned long long>(delta.count()),
                                         std::memory_order_relaxed);
        totals->calls.fetch_add(1, std::memory_order_relaxed);
        active->store(0, std::memory_order_release);
    }
private:
    Totals* totals{};
    std::atomic<long long>* active{};
    std::chrono::nanoseconds start{};
};
inline unsigned long long ActiveDiagnosticWaitNs(
        const std::atomic<long long>& active_slot) noexcept {
    const auto since = active_slot.load(std::memory_order_acquire);
    if (since <= 0) return 0;
    const auto now = Common::g_wall_clock.GetTimeNS().count();
    return now >= since ? static_cast<unsigned long long>(now - since) : 0ULL;
}

// Guest OnCPUWrite can run tens of millions of times per match. Counting
// every one using shared atomics makes the DEVELOPMENT logger itself contend
// across guest cores. Preserve exact per-callback wall-clock measurements,
// but publish each thread's accumulated calls/elapsed only every 64 writes.
// No guest cache mutex or buffer/texture resource lifetime is changed.
class BatchedGuestWriteTimer {
public:
    BatchedGuestWriteTimer() noexcept
        : enabled(detailed_gpu_profile.load(std::memory_order_relaxed)) {
        if (enabled) start = Common::g_wall_clock.GetTimeNS();
    }
    BatchedGuestWriteTimer(const BatchedGuestWriteTimer&) = delete;
    BatchedGuestWriteTimer& operator=(const BatchedGuestWriteTimer&) = delete;
    ~BatchedGuestWriteTimer() {
        if (!enabled) return;
        const auto elapsed = (Common::g_wall_clock.GetTimeNS() - start).count();
        auto& batch = LocalBatch();
        batch.nanoseconds += static_cast<unsigned long long>(elapsed > 0 ? elapsed : 0);
        if (++batch.calls == 64) batch.Flush();
    }

private:
    struct Batch {
        unsigned calls{};
        unsigned long long nanoseconds{};
        ~Batch() { Flush(); }
        void Flush() noexcept {
            if (!calls) return;
            guest_cpu_write.nanoseconds.fetch_add(nanoseconds, std::memory_order_relaxed);
            guest_cpu_write.calls.fetch_add(calls, std::memory_order_relaxed);
            calls = 0;
            nanoseconds = 0;
        }
    };
    static Batch& LocalBatch() noexcept {
        static thread_local Batch batch{};
        return batch;
    }
    bool enabled{};
    std::chrono::nanoseconds start{};
};

// Opt-in API wall times: calls may overlap across threads, so do not sum them as frame time.
inline std::atomic<bool> vulkan_cost_enabled{false};
inline std::array<Totals, 24> vulkan_api;
inline std::optional<Timer> VulkanTimer(unsigned index) {
    if (vulkan_cost_enabled.load(std::memory_order_relaxed))
        return std::optional<Timer>{std::in_place, vulkan_api.at(index)};
    return std::nullopt;
}
inline void ReportVulkan() {
    if (!vulkan_cost_enabled.load(std::memory_order_relaxed)) return;
    constexpr const char* names[]{"graphics_pipeline", "compute_pipeline", "submit",
                                  "fence_wait", "semaphore_wait", "device_idle",
                                  "guest_fence", "buffer_sync", "texture_sync", "present_sync",
                                  "descriptor_sync", "range_reuse", "astc_submit",
                                  "texture_gc", "texture_cpu_download", "texture_async_release",
                                  "pipeline_ready_wait", "shader_prepare", "pipeline_cache_save",
                                  "shader_pool_reset", "shader_cfg", "shader_ir",
                                  "shader_spirv", "shader_module"};
    static_assert(std::size(names) == vulkan_api.size());
    for (unsigned i = 0; i < vulkan_api.size(); ++i)
        std::printf("EDEN_VULKAN_COST api=%s calls=%llu ns=%llu\n", names[i],
                    vulkan_api[i].calls.load(std::memory_order_relaxed),
                    vulkan_api[i].nanoseconds.load(std::memory_order_relaxed));
}
// Call only before guest startup and after worker shutdown, respectively.
inline void Reset() {
    for (auto& entry : compilation) {
        entry.calls = 0;
        entry.nanoseconds = 0;
        entry.requested_bytes = 0;
    }
    for (auto& count : evacuations) count = 0;
    storage.calls = 0;
    storage.nanoseconds = 0;
    storage.requested_bytes = 0;
    jit_protection.calls = 0;
    jit_protection.nanoseconds = 0;
    jit_protection.requested_bytes = 0;
}
inline void Report() {
    for (unsigned core = 0; core < compilation.size(); ++core) {
        std::printf("EDEN_PERF_JIT core=%u compilations=%llu compile_ns=%llu evacuations=%llu\n",
                    core, compilation[core].calls.load(), compilation[core].nanoseconds.load(),
                    evacuations[core].load());

    }
    std::printf("EDEN_PERF_STORAGE calls=%llu read_ns=%llu requested_bytes=%llu\n",
                storage.calls.load(), storage.nanoseconds.load(), storage.requested_bytes.load());
    std::printf("EDEN_PERF_JIT_PROTECTION calls=%llu elapsed_ns=%llu requested_bytes=%llu\n",
                jit_protection.calls.load(), jit_protection.nanoseconds.load(), jit_protection.requested_bytes.load());
}
}
