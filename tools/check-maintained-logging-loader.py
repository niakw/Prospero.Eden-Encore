#!/usr/bin/env python3
"""Check maintained translation-unit parity against pinned sources (host-only)."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / "vendor/sources/eden/src"
active = root / "vendor/encore-active/eden-core/src"
cmake = (root / "headless/CMakeLists.txt").read_text()

loader = (base / "core/loader/deconstructed_rom_directory.cpp").read_text()
old = "? ::Settings::values.rng_seed.GetValue() : Common::Random::Random64(0)) << 12) & 0xfff000;"
new = "? ::Settings::values.rng_seed.GetValue() : Common::Random::Random64(0)) << 14) & 0xffc000;"
assert loader.count(old) == 1
assert (active / "core/loader/deconstructed_rom_directory.cpp").read_text() == loader.replace(old, new)

logging = (base / "common/logging.cpp").read_text()
old_flush = """            if (write_limit_exceeded)
                enabled = false;
            file->Flush();"""
new_flush = """            if (write_limit_exceeded)
                enabled = false;
            const auto flush_now = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now().time_since_epoch()).count();
            if (write_limit_exceeded ||
                flush_now - error_flushed_ms.load(std::memory_order_relaxed) >= 100) {
                error_flushed_ms.store(flush_now, std::memory_order_relaxed);
                file->Flush();
            }"""
field = "    std::optional<FS::IOFile> file;"
assert logging.count(old_flush) == logging.count(field) == 1
expected = ("#include <atomic>\n#include <chrono>\n" +
            logging.replace(old_flush, new_flush).replace(
                field, field + "\n    std::atomic<long long> error_flushed_ms{-1000};"))
assert (active / "common/logging.cpp").read_text() == expected

assert 'list(APPEND core_sources "${EDEN_MAINTAINED_CODE_LOADER}")' in cmake
assert 'list(APPEND eden_common_sources "${EDEN_MAINTAINED_LOGGING}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/deconstructed_rom_directory.cpp"' not in cmake
assert 'write_derived("${PORT_BUILD_DIR}/logging.cpp"' not in cmake
assert cmake.count("EDEN_MAINTAINED_CODE_LOADER") >= 3
assert cmake.count("EDEN_MAINTAINED_LOGGING") >= 3
print("MAINTAINED_LOADER_LOGGING_PARITY_PASS")
