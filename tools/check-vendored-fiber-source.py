#!/usr/bin/env python3
"""Prove the migrated PS5 fiber handoff compiles the exact previously derived code.

This byte-exact check prevents ABI/runtime drift when replacing CMake
string(REPLACE) generation with vendor/encore-active source.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pinned = (root/"vendor/sources/eden/src/common/fiber.cpp").read_text()
active = (root/"vendor/encore-active/eden-core/src/common/fiber.cpp").read_text()
cmake = (root/"headless/CMakeLists.txt").read_text()
first = "    to.impl->previous_fiber = weak_from.lock();"
old = '    // "from" might no longer be valid if the thread was killed\n    if (auto from = weak_from.lock()) {'
new = '    if (auto* from = static_cast<Fiber*>(transfer.data)) {'
assert pinned.count(first) == 1
assert pinned.count(old) == 1
expected = pinned.replace(first, first + "\n    ASSERT(to.impl->previous_fiber);\n    weak_from.reset();")
expected = expected.replace(old, new)
stack_before = 'struct Fiber::FiberImpl {\n    FiberImpl() {}\n\n    u32 canary_1 = CANARY_VALUE;\n    std::array<u8, DEFAULT_STACK_SIZE> stack{};\n    std::array<u8, DEFAULT_STACK_SIZE> rewind_stack{};\n    u32 canary_2 = CANARY_VALUE;\n'
stack_after = 'namespace {\nstruct FiberStack {\n    // Native thread stacks need writable storage, not zero-filled payloads.\n    // Keep both canaries adjacent to the allocated stack itself.\n    FiberStack() noexcept : canary_1{CANARY_VALUE}, canary_2{CANARY_VALUE} {}\n    u32 canary_1;\n    std::array<u8, DEFAULT_STACK_SIZE> bytes;\n    u32 canary_2;\n};\n} // namespace\n\nstruct Fiber::FiberImpl {\n    FiberImpl() = default;\n\n    // Host-thread fibers already use their OS stack. Guest/switch fibers\n    // allocate just their active stack; the old rewind array was unused.\n    std::unique_ptr<FiberStack> stack;\n'
assert expected.count(stack_before) == 1
expected = expected.replace(stack_before, stack_after)
for before, after in (
    ('    impl->stack_limit = impl->stack.data();\n    impl->rewind_stack_limit = impl->rewind_stack.data();',
     '    impl->stack = std::make_unique<FiberStack>();\n    impl->stack_limit = impl->stack->bytes.data();'),
    ('make_fcontext(stack_base, impl->stack.size(),', 'make_fcontext(stack_base, impl->stack->bytes.size(),'),
    ('ASSERT(fiber->impl->canary_1 == CANARY_VALUE);', 'ASSERT(fiber->impl->stack->canary_1 == CANARY_VALUE);'),
    ('ASSERT(fiber->impl->canary_2 == CANARY_VALUE);', 'ASSERT(fiber->impl->stack->canary_2 == CANARY_VALUE);'),
):
    assert expected.count(before) == 1
    expected = expected.replace(before, after)
assert active == expected, "tracked fiber source differs beyond the reviewed stack/lifetime changes"
assert 'set(EDEN_FIBER_ACTIVE "${PORT_ROOT}/vendor/encore-active/eden-core/src/common/fiber.cpp")' in cmake
assert 'list(APPEND common_sources "${EDEN_FIBER_ACTIVE}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/fiber.cpp"' not in cmake
assert 'list(APPEND common_sources "${PORT_BUILD_DIR}/fiber.cpp")' not in cmake
print("PASS: exact fiber transition and weak-ref cleanup moved from CMake generation to tracked C++")
