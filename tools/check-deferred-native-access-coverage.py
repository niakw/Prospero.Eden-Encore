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
    "tracked_cpu_callback=1 nce_x64_build=0 selective_jit_proof=0"
)
