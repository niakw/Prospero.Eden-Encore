#!/usr/bin/env python3
"""Fail-closed native guest-write coverage inventory (source only).

A PASS means the *known gaps* are still correctly blocked by the developer
runtime gate, NOT that native deferral is safe or any game is fixed.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source_root = root / "vendor/sources/eden/src"
read = lambda path: (source_root / path).read_text()
a64 = read("core/arm/dynarmic/arm_dynarmic_64.cpp")
a32 = read("core/arm/dynarmic/arm_dynarmic_32.cpp")
guest = read("core/guest_memory.h")
memory = read("core/memory.cpp")
page_table = read("common/page_table.h")
project_cmake = (root / "vendor/sources/eden/CMakeLists.txt").read_text()
core_cmake = read("core/CMakeLists.txt")
jit_emitter = read("dynarmic/src/dynarmic/backend/x64/emit_x64_memory.cpp.inc")
jit_lookup = read("dynarmic/src/dynarmic/backend/x64/emit_x64_memory.h")
port_cmake = (root / "headless/CMakeLists.txt").read_text()
checked_a32 = (root / "headless/checked-fastmem.cmake").read_text()
host_mem = (root / "src/host_memory.cpp").read_text()
host_jit_check = (root / "headless/memory_check.cpp").read_text()
gpu_guest = read("video_core/guest_memory.h")
gpu_manager = read("video_core/memory_manager.cpp")
gpu_dma = read("video_core/engines/maxwell_dma.cpp")
gpu_upload = read("video_core/engines/engine_upload.cpp")
gpu_blitter = read("video_core/engines/sw_blitter/blitter.cpp")
gpu_vic = read("video_core/host1x/vic.cpp")
gpu_driver = read("video_core/gpu.cpp")
nce = read("core/arm/nce/arm_nce.cpp")
bridge = (root / "headless/guest_write_deferred_bridge.cmake").read_text()
replay = (root / "headless/gpu_deferred_replay.h").read_text()
poststore = (root / "headless/gpu_deferred_store_publication.h").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

def expect(text: str, anchor: str, label: str) -> None:
    assert anchor in text, f"Review {label}: missing source anchor {anchor!r}"

# Both JITs may emit guest loads/stores through a directly mapped page
# table and fastmem, bypassing DynarmicCallbacksXX::MemoryWrite*.
for name, source, signature in (
    ("a64", a64, "void ArmDynarmic64::MakeJit("),
    ("a32", a32, "void ArmDynarmic32::MakeJit("),
):
    config = source.split(signature, 1)[1].split("m_jit.emplace(config);", 1)[0]
    expect(config, "config.page_table =", name)
    expect(config, "config.absolute_offset_page_table = true;", name)
    expect(config, "config.fastmem_pointer = page_table->fastmem_arena ?", name)
    expect(config, "config.fastmem_exclusive_access = config.fastmem_pointer", name)
    expect(config, "if (!Settings::IsFastmemEnabled())", name)
    expect(config, "config.fastmem_pointer = std::nullopt;", name)
    assert "GuestStoreOrderGate" not in config, name
    assert "CommitPostStore" not in config, name
    expect(source, "m_memory.Write32(vaddr, value);", name)

# A direct guest-memory span exposes the backing data for writes. In the
# scoped Safe/Cached case, the destructor uses InvalidateRegion AFTER writes,
# rather than necessarily calling Core::Memory::WriteBlock. The template is
# generic over M; it must not be claimed to cover only CPU producer paths.
expect(guest, "m_memory->GetSpan(m_addr, this->size_bytes())", "span")
expect(guest, "m_data_span = {reinterpret_cast<T*>(ptr), this->size()};", "span")
# Read-only FLAGS do not make returned aliases immutable: data(), Read()
# and operator[] expose mutable T or span<T>. Do not infer writer coverage
# from FLAGS & GuestMemoryFlags::Write call-site searches alone.
for anchor in (
    "T* data() noexcept {",
    "T& operator[](size_t index) noexcept {",
    "std::span<T> Read(u64 addr, std::size_t size,",
):
    expect(guest, anchor, "GuestMemory mutability independent of flags")
scoped = guest.split("~GuestMemoryScoped()", 1)[1]
expect(scoped, "this->m_memory->InvalidateRegion(this->m_addr, this->size_bytes());",
       "scoped span")
expect(scoped, "this->m_memory->WriteBlock(this->m_addr, this->data(), this->size_bytes());",
       "copy fallback")
expect(memory, "u8* Memory::GetSpan(const VAddr src_addr, const std::size_t size)", "memory span")
expect(memory, "return impl->GetSpan(src_addr, size);", "memory span")
assert "GuestStoreOrderGate" not in guest
assert "CommitPostStore" not in guest

# Existing SELECTIVE interception: tracked GPU pages are marked, and their
# host fastmem mapping loses write permission. This is a source-level route to
# investigate, NOT proof that every Dynarmic/JIT access or concurrent transition
# executes a callback. Ordinary untracked pages may still take direct paths.
expect(page_table, "RasterizerCachedMemory = 0b11", "tracked page type")
expect(page_table, "data_raw.fetch_or(0b111);", "atomic tracked mark")
expect(page_table, "return raw.marked && !ignore_marked ? 0", "masked direct pointer")
mark_region = memory.split("void RasterizerMarkRegionCached(", 1)[1].split("\n    /**", 1)[0]
for anchor in (
    "if (!Settings::values.use_reactive_flushing.GetValue() || !cached) {",
    "if (!cached) {",
    "host_buffer->Protect(vaddr, size, perm);",
    "entry.MarkRasterizerCached();",
):
    expect(mark_region, anchor, "tracked fastmem protection")
expect(memory, "Common::PageTable::PageEntryData::ExtractPointer(raw)", "pointer path")
expect(memory, "case Common::PageType::RasterizerCachedMemory: {", "tracked fallback")
expect(memory, "on_rasterizer();", "CPU fallback notification")
expect(memory, "HandleRasterizerWrite(addr, sizeof(T));", "scalar tracked store")
# Importantly GetSpan uses a silent raw pointer, so marking alone does not
# close the writable GuestMemory alias loophole.
expect(memory, "GetPointerSilent(addr) : nullptr;", "silent span alias")

# The tracked-page transition protects the fastmem view first, then marks
# the PTE. The byte-map update does NOT synchronously stop JIT workers that
# already passed the guard; host mapping mutex protects the updater, not JIT.
# This inventory deliberately does not claim transition linearization.
assert mark_region.index("host_buffer->Protect(vaddr, size, perm);") < mark_region.index(
    "entry.MarkRasterizerCached();"), "Re-audit protection/mark order"
a32_protect = host_mem.split("void Protect(std::size_t offset, std::size_t length, std::uint8_t access)", 1)[1]
a32_protect = a32_protect.split("\nprivate:", 1)[0]
expect(a32_protect, "std::fill(page_access.begin() + first, page_access.begin() + last + 1, access);", "A32 permission update")
expect(a32_protect, "Refresh(first, last);", "A32 checked guard refresh")
expect(checked_a32, "code.test(code.byte[r13 + index - checked_map_bytes], blocked_bit);", "JIT guard reads map")
# Compiler/JIT accesses that already read the old byte can still be in flight.
# No producer epoch/drain is present in this protection operation.

# GPU engines also hold mutable GuestMemory aliases. They are GPU-side
# producers, not direct evidence of bypassing CPU/JIT callbacks. Categorize
# them independently: cached writes and scoped post-write invalidation must
# remain ordered against dependent GPU work, not be mislabeled CPU stores.
for anchor in (
    "using GpuGuestMemoryScoped = Core::Memory::GuestMemoryScoped<Tegra::MemoryManager, T, FLAGS>;",
    "using DeviceGuestMemoryScoped =",
):
    expect(gpu_guest, anchor, "GPU scoped memory aliases")
for anchor in (
    "Tegra::Memory::GpuGuestMemoryScoped<u8,",
    "Tegra::Memory::GuestMemoryFlags::SafeReadCachedWrite>",
):
    expect(gpu_upload, anchor, "GPU upload writable alias")
expect(gpu_dma, "Tegra::Memory::GuestMemoryFlags::UnsafeReadCachedWrite>", "GPU DMA scoped write")
expect(gpu_blitter, "Tegra::Memory::GuestMemoryFlags::SafeReadWrite>", "GPU blitter scoped write")
expect(gpu_vic, "Core::Memory::GuestMemoryFlags::SafeWrite>", "GPU video scoped write")
expect(gpu_manager, "return memory.GetSpan(*dev_addr, size);", "GPU to backing span")
expect(gpu_manager, "accumulator.Add(gpu_dest_addr, size);", "GPU deferred cache invalidation")
expect(gpu_manager, "rasterizer->InvalidateRegion(dev_addr_base, copy_amount, which);", "GPU eager invalidation")
expect(gpu_driver, "WaitForSyncOperation(fence);", "existing CPU read synchronization")
expect(gpu_driver, "return renderer->ReadRasterizer()->OnCPUWrite(addr, size);", "CPU write-to-rasterizer")
# None of these anchors establishes a device fence for CAS or post-store
# CPU publication. A green source inventory remains a NO-GO verdict.

# Unlike a bare config-only inventory, the pinned x64 emitter DOES route
# marked page-table stores to callback fallback. The port's derived emitter
# replaces the marked-bit-zero test with test/jnz for both A32 and A64.
expect(jit_lookup, "if (ctx.conf.page_table_marked_bit)", "JIT marked page lookup")
expect(jit_lookup, "code.jc(abort, code.T_NEAR);", "JIT marked page fallback")
expect(jit_emitter, "void AxxEmitX64::EmitMemoryWrite(", "JIT store emitter")
expect(jit_emitter, "const auto dest_ptr = EmitVAddrLookup", "page-table store path")
expect(jit_emitter, "code.call(wrapped_fn);", "callback fallback")
expect(port_cmake, "if (*ctx.conf.page_table_marked_bit == 0) {", "derived bit-zero mark check")
expect(port_cmake, "code.test(page.cvt32(), 1);", "derived bit-zero test")
expect(port_cmake, "code.jnz(abort, code.T_NEAR);", "derived marked callback branch")
# Native A32 uses its own checked fastmem byte map. Protect() changes access
# bits instead of mprotect for these aliases; the blocked path checks its PTE.
expect(port_cmake, 'option(EDEN_A32_FASTMEM "A32 fastmem window with JIT fault recovery" ON)', "A32 fastmem build")
native_a32_memory = (root / "vendor/encore-active/eden-core/src/core/memory.cpp").read_text()
expect(port_cmake, 'list(APPEND core_sources "${EDEN_MAINTAINED_A32_MEMORY}")',
       "A32 guarded maintained unit selection")
expect(native_a32_memory, "!process.Is64Bit() && Settings::IsFastmemEnabled()",
       "A64 fastmem exclusion in maintained source")
expect(checked_a32, "constexpr u8 checked_read_blocked = 1, checked_write_blocked = 2;", "A32 read/write map bits")
expect(checked_a32, "EmitCheckedFastmemTest(code, vaddr, index, ${blocked_bit}, *blocked);", "A32 checked fastmem")
expect(checked_a32, "const auto fallback_ptr = EmitCheckedFallbackLookup", "A32 blocked path")
expect(checked_a32, "code.test(page.cvt32(), 1);", "A32 fallback PTE mark")
expect(checked_a32, "const auto fastmem_marker = checked_fastmem ? decltype(ShouldFastmem(ctx, inst)){} : ShouldFastmem(ctx, inst);", "A32 exclusives selection")
expect(host_mem, "std::fill(page_access.begin() + first, page_access.begin() + last + 1, access);", "A32 Protect access map")
expect(host_mem, "map[page] = Own(page) | Own(page + 1);", "A32 crossing protection")
# A CAS is a read-modify-write producer, not an eager "write follows"
# event. Both native WriteExclusive forms currently notify the rasterizer
# BEFORE AtomicCompareAndSwap, even if comparison fails; they do not perform
# HandleRasterizerDownload in that path. The *existing* GPU read fence lives
# in the separate OnCPURead path. The developer-only poststore model is not
# hooked to the native CAS read + GPU transfer + conditional outcome.
native_exclusives = memory.split("bool WriteExclusive(Common::ProcessAddress", 1)[1].split(
    "void HandleRasterizerDownload(", 1)[0]
expect(native_exclusives, "HandleRasterizerWrite(GetInteger(vaddr), sizeof(T));", "scalar CAS pre-notification")
expect(native_exclusives, "HandleRasterizerWrite(GetInteger(vaddr), sizeof(u128));", "128-bit CAS pre-notification")
expect(native_exclusives, "Common::AtomicCompareAndSwap(", "native CAS")
assert "HandleRasterizerDownload(" not in native_exclusives, "Re-audit native CAS read fence"
expect(gpu_driver, "WaitForSyncOperation(fence);", "GPU read fence exists separately")
expect(poststore, "CommitConditionalAfterRead(", "host-only conditional transaction")
# Absence of a native CAS read fence is a qualification gap, not proof of a
# game-level fault. Do not activate the deferred bridge on this evidence.

# The repository already has a REAL JIT harness for marked stores, checked
# A32 fastmem, concurrent page flips, and a table-vs-fastmem benchmark.
# Source anchors do not assert that any harness was run on this commit.
for anchor in ("static void CheckFastmemA32()", "static void StressFastmemA32()",
               "static void BenchFastmemA32()", "CheckFastmemA32();",
               "StressFastmemA32();", "require(memory.writes == (write ? callbacks : 0));"):
    expect(host_jit_check, anchor, "existing real JIT host harness")

# NCE is compiled only for ARM64 Linux/Android in the vendored project;
# its source file is not a native x86-64 console producer in that configuration.
# This is a build-selection fact, not a blanket claim about future ports.
expect(project_cmake, "if (ARCHITECTURE_arm64 AND (ANDROID OR LINUX))", "NCE platform gate")
expect(project_cmake, "set(HAS_NCE 1)", "NCE platform gate")
expect(core_cmake, "if (HAS_NCE)", "NCE build selection")
expect(core_cmake, "arm/nce/arm_nce.cpp", "NCE translation unit")

# NCE is a separate, platform-conditional native-execution mechanism.
# On the x86_64 host it is NOT proof of an active console write path.
expect(nce, "HaltReason ArmNce::RunThread(", "native execution")
expect(nce, "bool ArmNce::HandleGuestAccessFault(", "native access faults")

# The source-derived developer candidate is still eager PRE-store enqueue.
# No setting, source-generation refactor, or CI result can qualify it until
# all relevant direct-memory producers and GPU read/device fences are joined.
expect(bridge, "deferred_cpu_write_queue.Enqueue(core, address, size)", "bridge")
expect(replay, "inline constexpr bool kNativePostStorePublicationReady = false;", "gate")
assert "GuestStoreOrderGate" not in bridge
assert "CommitPostStore(" not in bridge
assert "CommitConditionalAfterRead(" not in bridge
expect(poststore, "class GuestStoreOrderGate final", "host model")
expect(workflow, "python3 -B tools/check-deferred-native-access-coverage.py", "CI")

print(
    "DEFERRED_NATIVE_ACCESS_COVERAGE_BLOCKED "
    "dynarmic_page_table_a32=1 dynarmic_page_table_a64=1 "
    "dynarmic_fastmem_a32=1 dynarmic_fastmem_a64=1 "
    "direct_guest_span=1 scoped_postwrite_notification=1 "
    "nce_platform_conditional=1 native_poststore_hook=0 "
    "native_gate_closed=1 "
    "tracked_page_marking=1 tracked_fastmem_write_protection=1 "
    "tracked_cpu_callback=1 nce_x64_build=0 jit_marked_callback_source=1 a32_checked_fastmem_source=1 "
    "a64_native_fastmem_disabled=1 real_jit_harness_present=1 "
    "jit_host_execution_this_commit=0 deferred_gpu_ordering_proof=0 "
    "transition_quiescence_proof=0 gpu_scoped_producers_inventoried=1 "
    "gpu_scoped_ordering_proof=0 "
    "guest_read_flag_immutable=0 "
    "cas_prewrite_notification=1 cas_device_read_fence_wired=0"
)
