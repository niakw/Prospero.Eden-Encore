#!/usr/bin/env python3
"""F07 C02: compile genuine graphics descriptor scratch lease and check HUD fastpaths.

Host-only: bounded reentrancy, stable spare descriptor capacity, independent
GPU-thread slots and dirty/decoding skip-order. Does NOT imply real FPS gain.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
graphics = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
texture = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
start = graphics.index("struct GraphicsDescriptorScratch {")
end = graphics.index("\nDescriptorLayoutBuilder MakeBuilder", start)
actual_scratch = graphics[start:end]
assert "thread_local GraphicsDescriptorScratch graphics_descriptor_scratch;" in actual_scratch
assert "thread_local GraphicsDescriptorScratch graphics_descriptor_nested_scratch;" in actual_scratch
assert "current->views.clear();" in actual_scratch
assert "current->samplers.clear();" in actual_scratch
assert "if (!nested) current->in_use = false;" in actual_scratch
assert "std::make_unique<GraphicsDescriptorScratch>()" in actual_scratch
begin = graphics.index("bool GraphicsPipeline::ConfigureImpl(bool is_indexed) {")
finish = graphics.index("\nbool GraphicsPipeline::ConfigureDraw(", begin)
config = graphics[begin:finish]
assert "GraphicsDescriptorScratchLease scratch;" in config
assert "auto& views = scratch.Views();" in config
assert "auto& samplers = scratch.Samplers();" in config
assert "views.reserve(num_image_elements);" in config
assert "samplers.reserve(num_textures);" in config
assert "if (num_image_elements != 0) {" in config
assert "texture_cache.SynchronizeDescriptors(false);" in config
assert "texture_cache.FillImageViews(std::span(views.data(), views.size()), false," in config
# An empty pass intentionally resets deletion/refresh retry state. Even a hot
# no-texture draw is NOT permission to skip required framebuffer work.
fill_at = texture.index("void TextureCache<P>::FillImageViews(")
fill_end = texture.index("\n}\n", fill_at) + 2
fill = texture[fill_at:fill_end]
assert "if (views.empty()) {" in fill
assert "has_deleted_images = false;" in fill
assert "return;" in fill.split("if (views.empty()) {", 1)[1].split("}", 1)[0]
assert "PrepareImageView(cached.id, false, false);" in fill
assert "VisitImageView(view.index, compute)" in fill
assert "has_deleted_images || (blacklist && has_blacklisted)" in fill
refresh_at = texture.index("void TextureCache<P>::RefreshContents(")
refresh_end = texture.index("\n}\n", refresh_at) + 2
refresh = texture[refresh_at:refresh_end]
assert refresh.index("if (False(image.flags & ImageFlagBits::CpuModified))") < refresh.index(
    "image.flags &= ~ImageFlagBits::CpuModified;"
)
assert refresh.index("if (True(image.flags & ImageFlagBits::IsDecoding))") < refresh.index(
    "image.flags &= ~ImageFlagBits::CpuModified;"
)
assert "image.flags |= ImageFlagBits::CpuModified;" in refresh
assert "bool upload_completed = false;" in refresh
assert "if (!upload_completed)" in refresh
# The chosen overlay must still carry BOTH fastpath and failed-staging logic.
assert "F07" in generator and "GraphicsDescriptorScratch" in generator

cpp = r"""
#include <boost/container/small_vector.hpp>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <memory>
#include <thread>
namespace VideoCommon {
struct ImageViewInOut { std::uint32_t index{}, flags{}, id{}; };
using SamplerId = std::uint32_t;
}
__SCRATCH__
int main() {
    assert(!graphics_descriptor_scratch.in_use);
    assert(!graphics_descriptor_nested_scratch.in_use);
    VideoCommon::ImageViewInOut* retained = nullptr;
    {
        GraphicsDescriptorScratchLease main;
        assert(graphics_descriptor_scratch.in_use);
        assert(!graphics_descriptor_nested_scratch.in_use);
        main.Views().reserve(384);
        main.Samplers().reserve(384);
        for (unsigned i = 0; i < 192; ++i) {
            main.Views().push_back({i, 0, i});
            main.Samplers().push_back(i);
        }
        retained = main.Views().data();
        assert(main.Views().capacity() >= 384);
        {
            GraphicsDescriptorScratchLease nested;
            assert(graphics_descriptor_scratch.in_use);
            assert(graphics_descriptor_nested_scratch.in_use);
            nested.Views().push_back({21, 0, 21});
            {
                GraphicsDescriptorScratchLease fallback;
                assert(graphics_descriptor_scratch.in_use);
                assert(graphics_descriptor_nested_scratch.in_use);
                fallback.Views().push_back({37, 0, 37});
                assert(fallback.Views()[0].id == 37);
                assert(main.Views()[0].id == 0);
                assert(nested.Views()[0].id == 21);
            }
            assert(nested.Views().size() == 1);
            assert(main.Views().size() == 192);
        }
        assert(graphics_descriptor_scratch.in_use);
        assert(!graphics_descriptor_nested_scratch.in_use);
    }
    assert(!graphics_descriptor_scratch.in_use);
    {
        GraphicsDescriptorScratchLease reused;
        assert(reused.Views().empty() && reused.Samplers().empty());
        assert(reused.Views().data() == retained);
        assert(reused.Views().capacity() >= 384);
        assert(reused.Samplers().capacity() >= 384);
    }
    std::atomic<bool> other_ok{false};
    std::thread other([&] {
        assert(!graphics_descriptor_scratch.in_use);
        GraphicsDescriptorScratchLease worker;
        worker.Views().push_back({17, 0, 17});
        other_ok.store(worker.Views()[0].id == 17 &&
                       worker.Views().data() != retained, std::memory_order_relaxed);
    });
    other.join();
    assert(other_ok.load(std::memory_order_relaxed));
    assert(!graphics_descriptor_scratch.in_use);
}
""".replace("__SCRATCH__", actual_scratch)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-graphics-scratch-") as folder:
    source = Path(folder) / "graphics.cpp"
    source.write_text(cpp)
    for native in (False, True):
        for opt in ("-O0", "-O2"):
            exe = Path(folder) / f"{'ps5' if native else 'desktop'}-{opt[1:]}"
            cmd = [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-pthread", opt,
                   "-fsanitize=undefined", "-fno-sanitize-recover=all",
                   *(["-DPS5_NATIVE=1"] if native else []),
                   str(source), "-o", str(exe)]
            build = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
            assert build.returncode == 0, (native, opt, build.stderr[-6000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert run.returncode == 0, (native, opt, run.stderr[-4000:])
            print(f"F07_GRAPHICS_HUD_SCRATCH_PASS native={int(native)} {opt} reentrant=1 retained_heap=1 tls=1 quiet=1 dirty_source_guard=1")
print("HOST_ONLY: no FC27 frame latency, Vulkan allocation timing or console pixels proof")
