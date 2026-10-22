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
source = active.decode()
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
    module.install(stage)
    assert target.read_bytes() == active
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
print("SURFACE_LIFECYCLE_COMPILER_INPUT_PASS full versioned source, pinned input and conflict rejection")
