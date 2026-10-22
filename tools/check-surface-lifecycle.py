#!/usr/bin/env python3
"""Execute the real R352 native SurfaceFlinger teardown methods in a tiny C++20 host harness.

Only surrounding external classes are mocked; the actual three methods plus
FindDisplay() are compiled unmodified from our versioned translation unit.
No PS5 SDK, network, GPU hardware or permanent test files are required.
"""
from __future__ import annotations
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import importlib.util

installer = ROOT / "tools/install-vendored-surface-lifecycle.py"
spec = importlib.util.spec_from_file_location("surface_installer", installer)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original, active = module.check()
composer_original, composer_active = module.check_composer()
source = active.decode()
composer_source = composer_active.decode()

# The second maintained TU is part of the exact native ownership graph.
# Do not let a future staged installer silently omit its inventory contract.
catalog = (ROOT / "docs/EDEN_ACTIVE_SOURCE_CATALOG.md").read_text()
audit = (ROOT / "docs/EDEN_CORE_AUDIT_DEPENDENCIES.md").read_text()
owner = "eden-surface-lifecycle/src/core/hle/service/nvnflinger/hardware_composer.cpp"
assert f"| `{owner}` | `maintained-override` | N23 |" in catalog
assert f"| N23 | P0 | N03,N06 | vendor/encore-active/{owner} |" in audit
original_source = original.decode()


def extract(name: str, prefix: str = "void") -> str:
    marker = prefix + " SurfaceFlinger::" + name + "("
    assert source.count(marker) == 1, marker
    start = source.index(marker)
    brace = source.index("{", start)
    level = 0
    for end in range(brace, len(source)):
        if source[end] == "{":
            level += 1
        elif source[end] == "}":
            level -= 1
            if not level:
                return source[start:end + 1]
    raise ValueError("Unterminated actual SurfaceFlinger method " + name)


methods = "\n\n".join(
    (extract("FindDisplay", "Display*"),
     extract("RemoveLayerFromDisplayStack"),
     extract("DestroyLayer"),
     extract("RemoveDisplay"),
     extract("FindLayer", "std::shared_ptr<Layer>"),
     extract("AddLayerToDisplayStack"))
)

for marker in ("WaitForComposite();", "RemoveLayerLocked(", "RemoveLayerFromDisplayStack("):
    assert marker in methods
assert methods.count("WaitForComposite();") == 2
assert "WaitForComposite();" not in original_source
assert "m_composer.RemoveLayerLocked" not in original_source.split("void SurfaceFlinger::RemoveDisplay", 1)[1].split("bool SurfaceFlinger::ComposeDisplay", 1)[0]

mock = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>
using u64 = std::uint64_t;
using s32 = std::int32_t;
namespace Nvidia { namespace Devices { struct nvdisp_disp0 {}; } }
struct Layer { s32 consumer_id; };
struct Display {
    u64 id{};
    struct { std::vector<std::shared_ptr<Layer>> layers; } stack;
};
struct MasterLayers { std::vector<std::shared_ptr<Layer>> layers; };
struct MockGpu {
    std::vector<std::string>* events{};
    void WaitForComposite() { events->push_back("wait"); }
};
struct MockNvDrv {
    MockGpu* gpu{};
    template<class T> MockGpu* GetDevice(int) { return gpu; }
};
struct MockComposer {
    std::vector<std::string>* events{};
    void RemoveLayerLocked(Display&, s32 id) {
        events->push_back("release:" + std::to_string(id));
    }
};
class SurfaceFlinger {
public:
    std::vector<std::string> events;
    MockGpu gpu{&events};
    MockNvDrv driver{&gpu};
    MockNvDrv* nvdrv{&driver};
    int disp_fd{};
    MockComposer m_composer{&events};
    MasterLayers m_layers;
    std::vector<Display> m_displays;

    Display* FindDisplay(u64 display_id);
    void RemoveDisplay(u64 display_id);
    void DestroyLayer(s32 consumer_binder_id);
    void RemoveLayerFromDisplayStack(u64 display_id, s32 consumer_binder_id);
    std::shared_ptr<Layer> FindLayer(s32 consumer_binder_id);
    void AddLayerToDisplayStack(u64 display_id, s32 consumer_binder_id);

    std::shared_ptr<Layer> attach(u64 display, s32 id) {
        auto value = std::make_shared<Layer>(Layer{id});
        auto found = FindDisplay(display);
        assert(found);
        found->stack.layers.push_back(value);
        m_layers.layers.push_back(value);
        return value;
    }
};
'''
checks = r'''
int main() {
    {
        // A binder can be attached to several displays, but only once per
        // display. Duplicate calls must not double-compose one BufferItem.
        SurfaceFlinger s;
        s.m_displays.push_back(Display{1, {}});
        s.m_displays.push_back(Display{2, {}});
        auto a = std::make_shared<Layer>(Layer{7});
        auto b = std::make_shared<Layer>(Layer{9});
        s.m_layers.layers = {a, b};
        s.AddLayerToDisplayStack(1, 7);
        s.AddLayerToDisplayStack(1, 7);
        s.AddLayerToDisplayStack(1, 9);
        s.AddLayerToDisplayStack(1, 7);
        s.AddLayerToDisplayStack(2, 7);
        s.AddLayerToDisplayStack(2, 7);
        s.AddLayerToDisplayStack(1, 99); // unknown binder, no insertion
        s.AddLayerToDisplayStack(99, 7); // unknown display, no insertion
        assert(s.m_displays[0].stack.layers.size() == 2);
        assert(s.m_displays[1].stack.layers.size() == 1);
        assert(s.m_displays[0].stack.layers[0] == a);
        assert(s.m_displays[0].stack.layers[1] == b);
        assert(s.m_displays[1].stack.layers[0] == a);
        s.RemoveLayerFromDisplayStack(1, 7);
        assert(s.m_displays[0].stack.layers.size() == 1);
        assert(s.m_displays[1].stack.layers.size() == 1);
        assert((s.events == std::vector<std::string>{"wait", "release:7"}));
        s.RemoveLayerFromDisplayStack(1, 7); // no second release
        assert(s.events.size() == 2);
        s.RemoveDisplay(2);
        assert((s.events == std::vector<std::string>{
            "wait", "release:7", "wait", "release:7"}));
    }
    {
        SurfaceFlinger s;
        s.m_displays.push_back(Display{42, {}});
        s.attach(42, 7);
        s.RemoveLayerFromDisplayStack(42, 7);
        assert((s.events == std::vector<std::string>{"wait", "release:7"}));
        assert(s.m_displays[0].stack.layers.empty());
        s.RemoveLayerFromDisplayStack(42, 7); // idempotent; no needless fence waits
        assert(s.events.size() == 2);
    }
    {
        SurfaceFlinger s;
        s.m_displays.push_back(Display{99, {}});
        s.attach(99, 17);
        s.DestroyLayer(17); // Container::OnTerminate bypasses CloseLayerLocked
        assert((s.events == std::vector<std::string>{"wait", "release:17"}));
        assert(s.m_displays[0].stack.layers.empty());
        assert(s.m_layers.layers.empty());
        s.DestroyLayer(17);
        assert(s.events.size() == 2);
    }
    {
        SurfaceFlinger s;
        s.m_displays.push_back(Display{13, {}});
        s.attach(13, 23);
        s.attach(13, 24);
        s.RemoveDisplay(13);
        assert((s.events == std::vector<std::string>{"wait", "release:23", "release:24"}));
        assert(s.m_displays.empty());
        s.RemoveDisplay(13);
        assert(s.events.size() == 3);
    }
    {
        SurfaceFlinger s;
        s.m_displays.push_back(Display{1, {}});
        s.m_displays.push_back(Display{2, {}});
        s.attach(1, 6);
        s.attach(2, 6);
        s.DestroyLayer(6);
        assert((s.events == std::vector<std::string>{
            "wait", "release:6", "wait", "release:6"
        }));
        assert(s.m_displays[0].stack.layers.empty());
        assert(s.m_displays[1].stack.layers.empty());
    }
    std::puts("SURFACE_LIFECYCLE_HOST_PASS actual source method bodies, acquired-slot cleanup and fence order");
}
'''

with tempfile.TemporaryDirectory(prefix="eden-surface-lifecycle-") as tmp:
    stage = Path(tmp)
    (stage / "GIT-COMMIT").write_text(module.EDEN_COMMIT + "\n")
    target = stage / module.PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    composer_target = stage / module.COMPOSER_PATH
    composer_target.parent.mkdir(parents=True, exist_ok=True)
    composer_target.write_bytes(composer_original)
    module.install(stage)
    assert composer_target.read_bytes() == composer_active
    assert target.read_bytes() == active
    assert composer_target.read_bytes() == composer_active
    module.install(stage)
    # Reproduce the exact previous maintained TU from the current one, without
    # storing a second source copy. Only its immutable Git blob may migrate.
    dedup_guard = "    // A layer is identified by its consumer binder within a display stack.\n    // Duplicate insertion would compose the same acquired BufferItem twice on\n    // each refresh and could needlessly retain an otherwise released slot.\n    if (std::any_of(display->stack.layers.begin(), display->stack.layers.end(),\n                    [consumer_binder_id](const auto& attached) {\n                        return attached->consumer_id == consumer_binder_id;\n                    })) {\n        return;\n    }\n\n"
    assert source.count(dedup_guard) == 1
    previous = source.replace(dedup_guard, "").encode()
    assert module.blob_sha(previous) == module.PREVIOUS_ACTIVE_GIT_BLOB
    target.write_bytes(previous)
    module.install(stage)
    assert target.read_bytes() == active
    module.install(stage)  # Idempotence after upgrading an old staged tree.
    composer_target.write_bytes(b"unexpected third-party change")
    try:
        module.install(stage)
    except RuntimeError as exc:
        assert "Unknown HardwareComposer input" in str(exc)
    else:
        raise AssertionError("unknown HardwareComposer source must fail closed")
    composer_target.write_bytes(composer_active)
    target.write_bytes(b"unexpected third-party change")
    try:
        module.install(stage)
    except RuntimeError as exc:
        assert "Unknown SurfaceFlinger input" in str(exc)
    else:
        raise AssertionError("unknown third-party source must fail closed")
    unit = stage / "test.cpp"
    binary = stage / "test"
    unit.write_text(mock + methods + checks)
    env = os.environ.copy()
    if sys.platform == "darwin":
        # Older Apple linker cannot parse the SDK v27 architecture tags.
        for name in ("MacOSX15.4.sdk", "MacOSX15.sdk"):
            candidate = Path("/Library/Developer/CommandLineTools/SDKs") / name
            if candidate.is_dir():
                env["SDKROOT"] = str(candidate)
                break
    subprocess.run(["c++", "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
                    str(unit), "-o", str(binary)], check=True, timeout=50, env=env)
    subprocess.run([str(binary)], check=True, timeout=10)

# Exercise the precise CacheFramebufferLocked implementation that ships to
# the PS5. Reuse of a still-acquired slot is valid; a RELEASED slot must not
# appear in another layer's new composite when acquire fails.
def extract_composer(name: str) -> str:
    marker = "HardwareComposer::CacheStatus HardwareComposer::" + name + "("
    assert composer_source.count(marker) == 1
    first = composer_source.index(marker)
    opening = composer_source.index("{", first)
    depth = 0
    for end in range(opening, len(composer_source)):
        if composer_source[end] == "{":
            depth += 1
        elif composer_source[end] == "}":
            depth -= 1
            if depth == 0:
                return composer_source[first:end + 1]
    raise AssertionError("Unterminated HardwareComposer native implementation")

composer_method = extract_composer("CacheFramebufferLocked")
assert "if (it->second.is_acquired)" in composer_method
assert "return CacheStatus::CachedBufferReused;" in composer_method
assert "return CacheStatus::NoBufferAvailable;" in composer_method
assert "this->TryAcquireFramebufferLocked(layer, it->second)" in composer_method
compose_real = composer_source.split("u32 HardwareComposer::ComposeLocked(", 1)[1]
assert compose_real.index("if (result == CacheStatus::NoBufferAvailable)") < compose_real.index("const auto& igbp_buffer = *item.graphic_buffer;")
composer_fixture = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <map>
using ConsumerId = std::int32_t;
struct Layer {};
class HardwareComposer {
public:
    enum class CacheStatus : std::uint32_t {
        NoBufferAvailable, BufferAcquired, CachedBufferReused
    };
    struct Framebuffer {
        int item{-1};
        bool is_acquired{};
    };
    std::map<ConsumerId, Framebuffer> m_framebuffers;
    bool next_available{};
    int next_item{10};
    unsigned attempts{};
    bool TryAcquireFramebufferLocked(Layer&, Framebuffer& framebuffer) {
        ++attempts;
        if (!next_available) return false;
        framebuffer.is_acquired = true;
        framebuffer.item = next_item++;
        next_available = false;
        return true;
    }
    CacheStatus CacheFramebufferLocked(Layer&, ConsumerId);
};
""" + composer_method + r"""
int main() {
    HardwareComposer h;
    Layer layer;
    using Status = HardwareComposer::CacheStatus;
    // First acquire failure must not invent a cached frame.
    assert(h.CacheFramebufferLocked(layer, 7) == Status::NoBufferAvailable);
    assert(h.m_framebuffers.empty());
    h.next_available = true;
    assert(h.CacheFramebufferLocked(layer, 7) == Status::BufferAcquired);
    assert(h.m_framebuffers[7].item == 10 && h.m_framebuffers[7].is_acquired);
    unsigned acquired_calls = h.attempts;
    // Reusing an acquired image is valid until its release.
    assert(h.CacheFramebufferLocked(layer, 7) == Status::CachedBufferReused);
    assert(h.attempts == acquired_calls);
    // Releasing to the producer revokes permission to sample stale memory.
    h.m_framebuffers[7].is_acquired = false;
    assert(h.CacheFramebufferLocked(layer, 7) == Status::NoBufferAvailable);
    assert(h.m_framebuffers[7].item == 10 && !h.m_framebuffers[7].is_acquired);
    assert(h.CacheFramebufferLocked(layer, 7) == Status::NoBufferAvailable);
    // A fresh, valid producer buffer restores the regular presentation path.
    h.next_available = true;
    assert(h.CacheFramebufferLocked(layer, 7) == Status::BufferAcquired);
    assert(h.m_framebuffers[7].item == 11 && h.m_framebuffers[7].is_acquired);
    // Separate layer never inherits an old cached acquisition.
    assert(h.CacheFramebufferLocked(layer, 8) == Status::NoBufferAvailable);
    h.next_available = true;
    assert(h.CacheFramebufferLocked(layer, 8) == Status::BufferAcquired);
    assert(h.m_framebuffers[8].item == 12 && h.m_framebuffers[7].item == 11);
    std::puts("HARDWARE_COMPOSER_RELEASED_FRAME_HOST_PASS");
}
"""
with tempfile.TemporaryDirectory(prefix="eden-composer-released-frame-") as tmp:
    stage = Path(tmp)
    unit = stage / "hardware_composer.cpp"
    unit.write_text(composer_fixture)
    for opt in ("-O0", "-O2"):
        exe = stage / ("hardware_composer" + opt)
        subprocess.run(["c++", "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(unit), "-o", str(exe)], check=True, timeout=45)
        subprocess.run([str(exe)], check=True, timeout=15)
        print("COMPOSER_RELEASED_FRAME_NATIVE_HOST_PASS", opt)

# Reuse the real native Composer implementation for a full multi-layer
# acquisition -> release -> presentation regression, not only a status mock.
subprocess.run([sys.executable, str(ROOT / "tools/check-native-hardware-composer-liveness-host.py")], check=True, timeout=110)

print("SURFACE_LIFECYCLE_COMPILER_INPUT_PASS full versioned source, pinned input and conflict rejection")
