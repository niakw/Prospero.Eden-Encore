#!/usr/bin/env python3
"""Compile the literal PS5 native MapPages no-backing guard and alias bound rule.

The source comes from the *actual* pinned backport hunks. This is a C++20
source regression with mocked guest page tables and direct backing, not a
native PS5 firmware/mapping/texture correctness measurement.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
patch = (root / "headless/backports/eden-ps5-guest-map-null-backing.patch").read_text()
alias_patch = (root / "headless/backports/eden-ps5-guest-zero-alias.patch").read_text()
apply = (root / "tools/apply-eden-backports.sh").read_text()
checker = (root / "tools/check-gpu-memory-mapping-source.py").read_text()
anchor = "                auto host_ptr = reinterpret_cast<u64>(system.DeviceMemory().GetPointer<u8>(target)) - (base << YUZU_PAGEBITS);;"
assert sum(line[1:].strip() == anchor.strip() for line in patch.splitlines()
           if line.startswith("-") and not line.startswith("---")) == 1
assert patch.startswith("--- a/src/core/memory.cpp\n+++ b/src/core/memory.cpp\n")
assert "invalid.Store(false, Common::PageType::Unmapped, current_block, 0);" in patch
assert "EDEN_GUEST_MAP_NO_BACKING" in patch
assert 'apply_one "$root/headless/backports/eden-ps5-guest-map-null-backing.patch"' in apply
assert "validate_ps5_guest_null_backing" in apply
assert (apply.index("eden-ps5-guest-zero-alias.patch") <
        apply.index("eden-ps5-guest-map-null-backing.patch") <
        apply.index("eden-ps5-guest-span.patch"))
assert "eden-ps5-guest-map-null-backing.patch" in checker

added = [line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
begin = added.index("#ifdef PS5_NATIVE")
end = added.index("#endif", begin)
guard = "\n".join(added[begin:end + 1])
assert "if (backing == nullptr)" in guard
assert "auto host_ptr = reinterpret_cast<u64>(backing)" in guard
assert guard.index("invalid.Store(") < guard.index("continue;")
assert guard.index("continue;") < guard.index("auto host_ptr")

alias_lines = [line[1:] for line in alias_patch.splitlines()
               if line.startswith("+") and not line.startswith("+++")]
alias_begin = next(i for i, line in enumerate(alias_lines)
                   if "bool IsDirectBackingAlias(" in line)
alias_end = next(i for i in range(alias_begin + 1, len(alias_lines))
                 if alias_lines[i].strip() == "}")
alias_method = "\n".join(alias_lines[alias_begin:alias_end + 1])
assert "GetIntendedMemorySize()" in alias_method
assert "address - base <= capacity - bytes" in alias_method
compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if compiler is None:
    raise SystemExit("C++20 compiler unavailable: guest null-backing proof unexecuted")

cpp = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
using u64 = std::uint64_t;
using u8 = std::uint8_t;
constexpr unsigned YUZU_PAGEBITS = 12;
constexpr std::size_t YUZU_PAGESIZE = 4096;
namespace Common {
enum class PageType { Unmapped, Memory };
}
struct Entry {
    Common::PageType type = Common::PageType::Unmapped;
    u64 delta = 0;
    unsigned stores = 0;
    void Store(bool, Common::PageType t, unsigned, u64 d) {
        type = t;
        delta = d;
        ++stores;
    }
};
struct PageEntries {
    std::array<Entry, 8> pages{};
    void CommitRegion(std::size_t, std::size_t) {}
    Entry& GetUnchecked(std::size_t idx) { return pages.at(idx); }
};
struct PageTable {
    PageEntries entries;
};
struct DeviceBuffer {
    std::uintptr_t base = 0x3000;
    void* BackingBasePointer() const {
        return reinterpret_cast<void*>(base);
    }
};
struct DeviceMemory {
    DeviceBuffer buffer;
    template <typename T>
    T* GetPointer(u64 physical) {
        if (physical == 0x301000)
            return reinterpret_cast<T*>(0x3000); // legal guest/host VA alias
        if (physical == 0x302000)
            return reinterpret_cast<T*>(0x9000); // ordinary nonzero host delta
        return nullptr;                         // truly missing physical page
    }
};
struct System {
    DeviceMemory device;
    DeviceMemory& DeviceMemory() { return device; }
};
namespace Kernel::Board::Nintendo::Nx {
struct KSystemControl {
    struct Init {
        static std::size_t GetIntendedMemorySize() { return 8192; }
    };
};
}
namespace Eden::GpuFault {
unsigned missing_reports = 0;
bool ShouldReportGuestMapZero() {
    ++missing_reports;
    return true;
}
}
u64 GetInteger(u64 value) { return value; }
static unsigned log_count = 0;
static u64 bad_guest = 0;
static u64 bad_physical = 0;
static void report_missing(u64 guest, u64 physical) {
    ++log_count;
    bad_guest = guest;
    bad_physical = physical;
}
#define LOG_CRITICAL(_category, _format, guest, phys) report_missing(guest, phys)
struct Impl {
    System& system;
__ALIAS_METHOD__
    void Map() {
        PageTable page_table;
        std::size_t base = 2;
        constexpr std::size_t end = 5;
        u64 target = 0x300000;
        unsigned current_block = 1;
        Common::PageType type = Common::PageType::Memory;
        page_table.entries.CommitRegion(base, end);
        while (base != end) {
__GUARD__
            auto& entry = page_table.entries.GetUnchecked(base);
            entry.Store(false, type, current_block, host_ptr);
            base += 1;
            target += YUZU_PAGESIZE;
        }
        const auto& missing = page_table.entries.pages[2];
        const auto& alias = page_table.entries.pages[3];
        const auto& ordinary = page_table.entries.pages[4];
        assert(missing.type == Common::PageType::Unmapped);
        assert(missing.delta == 0 && missing.stores == 1);
        assert(alias.type == Common::PageType::Memory);
        assert(alias.delta == 0 && alias.stores == 1);
        assert(IsDirectBackingAlias(0x3000, 4096));
        assert(!IsDirectBackingAlias(0x2000, 4096));
        assert(!IsDirectBackingAlias(0x5000, 1));
        assert(!IsDirectBackingAlias(0x3000, 8193));
        assert(!IsDirectBackingAlias(std::numeric_limits<u64>::max(), 1));
        assert(ordinary.type == Common::PageType::Memory);
        assert(ordinary.delta == 0x5000 && ordinary.stores == 1);
        assert(log_count == 1 && Eden::GpuFault::missing_reports == 1);
        assert(bad_guest == 0x2000 && bad_physical == 0x300000);
        system.device.buffer.base = 0;
        assert(!IsDirectBackingAlias(0x3000, 4096));
    }
};
int main() {
    System system;
    Impl impl{system};
    impl.Map();
}
"""
cpp = cpp.replace("__GUARD__", guard).replace("__ALIAS_METHOD__", alias_method)
with tempfile.TemporaryDirectory(prefix="eden-guest-null-backing-") as folder:
    source = Path(folder) / "check.cpp"
    binary = Path(folder) / "check"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-DPS5_NATIVE=1",
                    str(source), "-o", str(binary)], check=True, timeout=120)
    subprocess.run([str(binary)], check=True, timeout=120)
print("PASS extracted PS5 MapPages: missing PA -> Unmapped; identity host alias remains Memory; ordinary nonzero delta ASan/UBSan")
print("Not firmware 13.60 mapping execution or proof of FC27 texture reconstruction")
