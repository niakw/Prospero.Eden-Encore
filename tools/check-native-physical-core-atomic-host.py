#!/usr/bin/env python3
"""Run maintained PhysicalCore atomic-ref implementation through actual core methods.

The pinned bool ABI is unchanged. Every source access must be atomic; the
host fixture confirms interrupt observation under concurrent toggles.
Does not qualify native JIT quiescence or GPU handoff / bridge #187.
"""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/sources/eden/src/core/hle/kernel/physical_core.h").read_text()
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/physical_core.cpp").read_text()
cmake_source = (root / "headless/CMakeLists.txt").read_text()
owned = root / "vendor/encore-active/eden-core/src/core/hle/kernel"
existing_fixture = root / "tools/check-native-physical-core-interrupt-ack-host.py"
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert "    bool m_is_interrupted{};" in header
assert not (root / "headless/physical_core_interrupt_atomic.cmake").exists()
assert 'configure_file("${EDEN_PHYSICAL_CORE_SOURCE}" "${PORT_BUILD_DIR}/physical_core.cpp" COPYONLY)' in cmake_source
assert "python3 -B tools/check-native-physical-core-atomic-host.py" in workflow
assert pinned.count("m_is_interrupted") == 5
assert "std::atomic_ref" not in pinned
for filename in ("physical_core_standard.cpp", "physical_core_dev.cpp"):
    derived = (owned / filename).read_text()
    assert derived.startswith("#include <atomic>\\n")
    assert "std::atomic_ref<const bool>" in derived

compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler and shutil.which("cmake"), "CMake and C++20 compiler required"


def method(text, start, end):
    assert text.count(start) == 1 and text.count(end) == 1
    return start + text.split(start, 1)[1].split(end, 1)[0]


def fixture_literal(name):
    tree = ast.parse(existing_fixture.read_text())
    matches = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
    ]
    assert len(matches) == 1, f"host fixture {name} changed"
    return ast.literal_eval(matches[0])


with tempfile.TemporaryDirectory(prefix="encore-physical-atomic-") as folder:
    base = Path(folder)
    snapshots = {}
    for profile in (False, True):
        path = base / ("profile.cpp" if profile else "default.cpp")
        build_script = base / ("profile.cmake" if profile else "default.cmake")
        maintained = owned / ("physical_core_dev.cpp" if profile else "physical_core_standard.cpp")
        selection_begin = cmake_source.index('set(EDEN_PHYSICAL_CORE_DIR "')
        selection_end = cmake_source.index('list(REMOVE_ITEM core_sources "hle/kernel/physical_core.cpp")', selection_begin)
        selection = cmake_source[selection_begin:selection_end]
        build_script.write_text(
            "cmake_minimum_required(VERSION 3.25)\n"
            + f'set(PORT_ROOT "{root.as_posix()}")\n'
            + f'set(PORT_BUILD_DIR "{base.as_posix()}")\n'
            + f'set(EDEN_DEV_PROFILE {"ON" if profile else "OFF"})\n'
            + selection
        )
        subprocess.run(["cmake", "-P", str(build_script)], check=True, timeout=20)
        staged = base / "physical_core.cpp"
        assert staged.read_bytes() == maintained.read_bytes()
        derived = staged.read_text()
        assert derived.startswith("#include <atomic>\n")
        assert derived.count("m_is_interrupted") == (6 if profile else 5)
        assert derived.count("std::atomic_ref<const bool>{m_is_interrupted}.load(std::memory_order_relaxed)") == (4 if profile else 3)
        assert derived.count("std::atomic_ref<bool>{m_is_interrupted}.store(") == 2
        assert "return m_is_interrupted;" not in derived
        assert "m_is_interrupted = true;" not in derived
        assert "m_is_interrupted = false;" not in derived
        snapshots[profile] = derived

    source = snapshots[False]
    maintained_run = method(source,
        "void PhysicalCore::RunThread(KernelCore& kernel, Kernel::KThread* thread) {",
        "\nvoid PhysicalCore::LoadContext(")
    # This fixture stubs only the scheduler/JIT handoff ABI. The maintained
    # RunThread additionally captures a fatal page-table/guest context, which
    # is checked against both full sources by check-ps5-guest-fault-recovery.py.
    # For the concurrent atomic harness, preserve the exact pinned scheduler
    # method and substitute only its single interrupted-load site.
    actual_run = method(pinned,
        "void PhysicalCore::RunThread(KernelCore& kernel, Kernel::KThread* thread) {",
        "\nvoid PhysicalCore::LoadContext(").replace(
            "if (m_is_interrupted)",
            "if (std::atomic_ref<const bool>{m_is_interrupted}.load(std::memory_order_relaxed))"
        )
    assert "if (std::atomic_ref<const bool>{m_is_interrupted}.load(std::memory_order_relaxed))" in maintained_run
    assert "if (prefetch_abort)" in maintained_run
    assert "::Eden::RecordGuestFault(eden_fault);" in maintained_run
    actual_interrupt = method(source, "void PhysicalCore::Interrupt() {",
        "\nvoid PhysicalCore::ClearInterrupt() {")
    actual_clear = method(source, "void PhysicalCore::ClearInterrupt() {",
        "\n} // namespace Kernel")
    actual_is_interrupted = method(source,
        "bool PhysicalCore::IsInterrupted() const {",
        "\nvoid PhysicalCore::Interrupt() {")

    prelude = fixture_literal("prelude")
    postlude = fixture_literal("postlude")
    anchor = "    void ClearInterrupt();\nprivate:"
    assert prelude.count(anchor) == 1
    prelude = prelude.replace(anchor, "    void ClearInterrupt();\n    bool IsInterrupted() const;\nprivate:")
    old = '    std::puts("PINNED_PHYSICAL_CORE_NATIVE_HANDOFF_UNQUALIFIED");'
    assert postlude.count(old) == 1
    postlude = postlude.replace(old, r"""
    assert(core.IsInterrupted());
    core.ClearInterrupt();
    assert(!core.IsInterrupted());
    std::atomic<bool> stop{false};
    std::thread reader([&] {
        while (!stop.load(std::memory_order_relaxed)) {
            (void)core.IsInterrupted();
        }
    });
    std::thread toggler([&] {
        for (unsigned i = 0; i < 25000; ++i) {
            core.Interrupt();
            core.ClearInterrupt();
        }
        core.Interrupt();
    });
    toggler.join();
    stop.store(true, std::memory_order_relaxed);
    reader.join();
    assert(core.IsInterrupted());
    std::puts("PINNED_PHYSICAL_CORE_ATOMIC_CONCURRENT_OBSERVATION_PASS");
""" + old)
    unit = base / "fixture.cpp"
    binary = base / "fixture"
    unit.write_text(prelude + "\n" + actual_run + "\n"
                    + actual_is_interrupted + "\n" + actual_interrupt
                    + "\n" + actual_clear + "\n" + postlude)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-pthread", str(unit), "-o", str(binary)], check=True, timeout=30)
    output = subprocess.run([str(binary)], capture_output=True, text=True,
                            check=True, timeout=15).stdout
    assert "PINNED_PHYSICAL_CORE_ATOMIC_CONCURRENT_OBSERVATION_PASS" in output
    print(output, end="")
print("PINNED_PHYSICAL_CORE_DIAGNOSTIC_ATOMIC_ACCESS_PASS")
print("PINNED_PHYSICAL_CORE_NATIVE_GPU_HANDOFF_STILL_DISABLED")
