#!/usr/bin/env python3
"""Compile native AMD dynamic logic-op method and dirty transition with UBSan."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
deferred = (root / "vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
state_flags = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_state_tracker.cpp").read_text()
assert "FillBlock(tables[1], OFF(vertex_attrib_format), Regs::NumVertexAttributes, VertexInput);" in state_flags

sig = "void RasterizerVulkan::UpdateLogicOpEnable(Tegra::Engines::Maxwell3D::Regs& regs) {"
def extract(src, begin, end):
    assert src.count(begin) == 1
    start = src.index(begin)
    return src[start:src.index(end, start)].rstrip()
method = extract(native, sig, "\nvoid RasterizerVulkan::UpdateDepthClampEnable(")
assert "regs.logic_op.enable =" not in method
assert "enable = !std::any_of(" in method
assert method == extract(deferred, sig, "\nvoid RasterizerVulkan::UpdateDepthClampEnable(")
begin = "        // The AMD host workaround depends on vertex formats"
end = "        UpdateDepthClampEnable(regs);"
block = extract(native, begin, end)
assert block == extract(deferred, begin, end)
assert "flags[Dirty::VertexInput]" in block
assert "flags[Dirty::LogicOpEnable] = true;" in block
assert "regs.logic_op.enable =" not in block
assert "regs.logic_op.enable = static_cast<u32>(!has_float)" in pinned

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <utility>
using u32 = std::uint32_t;
enum class VkDriverIdKHR { VK_DRIVER_ID_AMD_OPEN_SOURCE, VK_DRIVER_ID_AMD_PROPRIETARY, OTHER };
namespace Dirty { enum : unsigned { VertexInput, LogicOpEnable, Count }; }
namespace Tegra::Engines {
struct Maxwell3D {
    struct Regs {
        struct VertexAttribute {
            enum class Type { Float, Integer };
            Type type{Type::Integer};
        };
        std::array<VertexAttribute, 4> vertex_attrib_format{};
        struct { u32 enable{}; } logic_op{};
    } regs;
    struct { std::array<bool, Dirty::Count> flags{}; } dirty;
};
}
namespace vk { struct CommandBuffer {
    bool* target{};
    void SetLogicOpEnableEXT(bool enable) { *target = enable; }
}; }
struct Device {
    VkDriverIdKHR driver{VkDriverIdKHR::OTHER};
    bool supported{true};
    unsigned* driver_reads{};
    VkDriverIdKHR GetDriverID() const {
        if (driver_reads) ++*driver_reads;
        return driver;
    }
    bool SupportsDynamicState3LogicOpEnable() const { return supported; }
    bool IsExtExtendedDynamicState3EnablesSupported() const { return true; }
};
struct Tracker {
    Tegra::Engines::Maxwell3D* maxwell{};
    bool TouchLogicOpEnable() {
        auto& flag = maxwell->dirty.flags[Dirty::LogicOpEnable];
        return std::exchange(flag, false);
    }
};
struct Scheduler {
    bool logic_op{};
    unsigned records{};
    template<class Callback> void Record(Callback cb) {
        vk::CommandBuffer cmd{&logic_op};
        cb(cmd);
        ++records;
    }
};
struct RasterizerVulkan {
    Tegra::Engines::Maxwell3D* maxwell3d{};
    Device device{};
    Tracker state_tracker{};
    Scheduler scheduler{};
    void UpdateLogicOpEnable(Tegra::Engines::Maxwell3D::Regs& regs);
    void UpdateDynamicStates();
};
""" + "\n" + method + r"""
void RasterizerVulkan::UpdateDynamicStates() {
    auto& regs = maxwell3d->regs;
    auto& flags = maxwell3d->dirty.flags;
    if (device.IsExtExtendedDynamicState3EnablesSupported()) {
        using namespace Tegra::Engines;
""" + block + r"""
    }
}
int main() {
    Tegra::Engines::Maxwell3D m{};
    RasterizerVulkan r{};
    unsigned driver_reads{};
    r.maxwell3d=&m;
    r.device.driver_reads=&driver_reads;
    r.state_tracker.maxwell=&m;
    m.regs.logic_op.enable=1;
    m.dirty.flags[Dirty::LogicOpEnable]=true;
    r.UpdateDynamicStates();
    assert(r.scheduler.logic_op && m.regs.logic_op.enable == 1);
    assert(r.scheduler.records == 1);
    driver_reads = 0;
    r.UpdateDynamicStates();
    assert(driver_reads == 0 && r.scheduler.records == 1);
    // An AMD float vertex disables the host command, NOT the guest reg.
    r.device.driver=VkDriverIdKHR::VK_DRIVER_ID_AMD_OPEN_SOURCE;
    m.regs.vertex_attrib_format[0].type =
        Tegra::Engines::Maxwell3D::Regs::VertexAttribute::Type::Float;
    m.dirty.flags[Dirty::VertexInput]=true;
    r.UpdateDynamicStates();
    assert(!r.scheduler.logic_op && m.regs.logic_op.enable == 1);
    assert(r.scheduler.records == 2);
    m.dirty.flags[Dirty::VertexInput]=false;
    driver_reads=0;
    r.UpdateDynamicStates();
    assert(driver_reads == 0 && r.scheduler.records == 2);
    // Rebinding after switching away from float uses the original reg.
    m.regs.vertex_attrib_format[0].type =
        Tegra::Engines::Maxwell3D::Regs::VertexAttribute::Type::Integer;
    m.dirty.flags[Dirty::VertexInput]=true;
    r.UpdateDynamicStates();
    assert(r.scheduler.logic_op && m.regs.logic_op.enable == 1);
    assert(r.scheduler.records == 3);
    m.dirty.flags[Dirty::VertexInput]=false;
    // Guest actually disables logic op.
    m.regs.logic_op.enable=0;
    m.dirty.flags[Dirty::LogicOpEnable]=true;
    r.UpdateDynamicStates();
    assert(!r.scheduler.logic_op && m.regs.logic_op.enable == 0);
    assert(r.scheduler.records == 4);
    // A vertex change while guest logic op is already off does not rebind.
    m.dirty.flags[Dirty::VertexInput]=true;
    r.UpdateDynamicStates();
    assert(r.scheduler.records == 4);
    m.dirty.flags[Dirty::VertexInput]=false;
    // Proprietary AMD driver is covered as well.
    r.device.driver=VkDriverIdKHR::VK_DRIVER_ID_AMD_PROPRIETARY;
    m.regs.logic_op.enable=1;
    m.regs.vertex_attrib_format[1].type =
        Tegra::Engines::Maxwell3D::Regs::VertexAttribute::Type::Float;
    m.dirty.flags[Dirty::LogicOpEnable]=true;
    r.UpdateDynamicStates();
    assert(!r.scheduler.logic_op && m.regs.logic_op.enable==1);
    assert(r.scheduler.records == 5);
    // Non-AMD drivers preserve the exact unmodified guest enable.
    r.device.driver=VkDriverIdKHR::OTHER;
    m.dirty.flags[Dirty::LogicOpEnable]=true;
    r.UpdateDynamicStates();
    assert(r.scheduler.logic_op && m.regs.logic_op.enable==1);
    assert(r.scheduler.records == 6);
}
"""
compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-amd-logic-") as tmp:
    source = Path(tmp) / "logic_op.cpp"
    source.write_text(cpp)
    for opt in ("-O0", "-O2"):
        exe = Path(tmp) / ("logic" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(source), "-o", str(exe)], check=True, timeout=45)
        subprocess.run([str(exe)], check=True, timeout=20)
        print("NATIVE_AMD_LOGIC_OP_REGISTER_PASS", opt)
