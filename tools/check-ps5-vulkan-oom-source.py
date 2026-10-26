#!/usr/bin/env python3
"""F07: verify the shipping PS5 allocator emits allocation-specific OOM evidence.

This deliberately checks the actual fork staged by CMake, not a source snippet
that is absent from the native binary. Runtime memory data remains console-only.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/vulkan.cmake").read_text(encoding="utf-8")
original = (root / "vendor/sources/eden/src/video_core/vulkan_common/vulkan_memory_allocator.cpp").read_text(encoding="utf-8")
fork = (root / "vendor/encore-active/eden-vulkan/vulkan_memory_allocator.cpp").read_text(encoding="utf-8")

assert 'vulkan_common/vulkan_memory_allocator.cpp' in cmake
assert '"${PORT_BUILD_DIR}/vulkan_memory_allocator.cpp"' in cmake
assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in cmake
assert 'vk::Check(vmaCreateImage(' in original  # upstream pinned unchanged

def valid(source: str) -> bool:
    begin = source.index("vk::Image MemoryAllocator::CreateImage(")
    end = source.index("vk::Buffer MemoryAllocator::CreateBuffer(", begin)
    f = source[begin:end]
    contract = (
        "VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT" in f
        and "const VkResult result = vmaCreateImage(" in f
        and "#ifdef PS5_NATIVE" in f
        and "result == VK_ERROR_OUT_OF_DEVICE_MEMORY" in f
        and "result == VK_ERROR_OUT_OF_HOST_MEMORY" in f
        and 'EDEN_VULKAN_IMAGE_ALLOC_FAILED' in f
        and 'EDEN_VULKAN_IMAGE_HEAP' in f
        and "ci.extent.width, ci.extent.height, ci.extent.depth" in f
        and "ci.mipLevels, ci.arrayLayers" in f
        and "vmaGetHeapBudgets(allocator, budgets.data())" in f
        and "std::fflush(stderr)" in f
        and "vk::Check(result);" in f
        and "vmaAllocateMemory(" not in f
    )
    if not contract:
        return False
    return (f.index("vmaCreateImage(") < f.index("if (result == VK_ERROR_OUT_OF_DEVICE_MEMORY")
            < f.index("vmaGetHeapBudgets(") < f.index("std::fflush(stderr)")
            < f.index("vk::Check(result);"))

# The active fork must differ from upstream ONLY by the reviewed OOM hook.
# This is a stronger oracle than generic source/token assertions.
reconstructed = fork.replace("#include <array>\\n#include <cstdio>\\n", "")
start = reconstructed.index("    const VkResult result = vmaCreateImage(")
end = reconstructed.index("    vk::Check(result);", start) + len("    vk::Check(result);")
upstream_call = "    vk::Check(vmaCreateImage(allocator, &ci, &alloc_ci, &handle, &allocation, &alloc_info));"
reconstructed = reconstructed[:start] + upstream_call + reconstructed[end:]
assert reconstructed == original, "native allocator diverges from pinned upstream outside F07 diagnostic"

assert valid(fork), "F07 native OOM allocation proof missing"
assert not valid(fork.replace("vk::Check(result);", "// missing exception"))
assert not valid(fork.replace("#ifdef PS5_NATIVE", "// missing PS5 guard"))
assert not valid(fork.replace("vmaGetHeapBudgets(allocator, budgets.data())", "// removed budgets"))
print("PASS F07: production VMA image OOM emits exact image and heap evidence before exception")
