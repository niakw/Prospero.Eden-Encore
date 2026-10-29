#!/usr/bin/env python3
"""F07 C02: compile actual FillImageViews with stable, remapped and dirty HUD views.

This test must retain PrepareImageView on nonadjacent TIC memo hits; avoiding
the lookup does not justify skipping a modified guest image refresh. It also
exercises the existing retry/blacklist behavior, empty latch reset, and
desktop original algorithm using the *source-extracted* method, O0/O2 UBSan.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
file = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
begin = file.index("void TextureCache<P>::FillImageViews(std::span<ImageViewInOut> views, bool compute, bool blacklist) {")
end = file.index("\n}\n", begin) + 2
actual = file[begin:end]
assert "if (views.empty()) {" in actual
assert "has_deleted_images = false;" in actual
assert "std::array<ViewMemo, 16> view_memo{};" in actual
assert "cached_view.IsBuffer()" in actual
assert "ImageFlagBits::Remapped" in actual
assert "PrepareImageView(cached.id, false, false);" in actual
assert "view.id = VisitImageView(view.index, compute);" in actual
assert "has_deleted_images || (blacklist && has_blacklisted)" in actual

code = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <span>
#include <vector>
using u32 = std::uint32_t;
using ImageViewId = u32;
using ImageId = u32;
constexpr ImageViewId NULL_IMAGE_VIEW_ID{};
enum class ImageFlagBits : u32 { Remapped = 1 };
bool True(ImageFlagBits flags) { return static_cast<u32>(flags) != 0; }
ImageFlagBits operator&(u32 flags, ImageFlagBits bit) {
    return static_cast<ImageFlagBits>(flags & static_cast<u32>(bit));
}
struct ImageViewInOut {
    u32 index{};
    bool blacklist{};
    ImageViewId id{};
};
struct ImageViewBase {
    ImageId image_id{};
    bool is_buffer{};
    bool IsBuffer() const { return is_buffer; }
};
struct Image { u32 flags{}; u32 scale_rating{}; };
template<class P>
class TextureCache {
public:
    bool has_deleted_images = false;
    std::vector<ImageViewBase> slot_image_views{{}, {1}, {2}, {3}};
    std::vector<Image> slot_images{{}, {}, {}, {}};
    unsigned visit_calls{}, prepare_calls{}, refreshes{}, scales{};
    bool one_deleted_retry{}, one_blacklist_retry{};
    ImageViewId VisitImageView(u32 index, bool compute) {
        assert(index > 0 && index < 4);
        (void)compute;
        ++visit_calls;
        if (one_deleted_retry) {
            one_deleted_retry = false;
            has_deleted_images = true;
        }
        PrepareImageView(index, false, false);
        return index;
    }
    void PrepareImageView(ImageViewId id, bool, bool) {
        assert(id != NULL_IMAGE_VIEW_ID);
        ++prepare_calls;
        if (slot_images[slot_image_views[id].image_id].flags)
            ++refreshes;
    }
    bool ScaleDown(Image&) {
        ++scales;
        if (one_blacklist_retry) {
            one_blacklist_retry = false;
            return true;
        }
        return false;
    }
    void FillImageViews(std::span<ImageViewInOut> views, bool compute, bool blacklist);
};
template <class P>
__ACTUAL_FILL__
struct Mock {};
int main() {
    TextureCache<Mock> texture;
    std::array<ImageViewInOut, 4> repeated{{{1}, {2}, {1}, {2}}};
    texture.FillImageViews(repeated, false, false);
#ifdef PS5_NATIVE
    assert(texture.visit_calls == 2); // nonadjacent TIC lookup reuse
    assert(texture.prepare_calls == 4); // NEVER elide freshness preparation
#else
    assert(texture.visit_calls == 4 && texture.prepare_calls == 4);
#endif
    for (auto view : repeated) assert(view.id == view.index);
    texture.visit_calls = texture.prepare_calls = texture.refreshes = 0;
    texture.slot_images[1].flags = 1; // remapped guest texture
    std::array<ImageViewInOut, 3> remapped{{{1}, {2}, {1}}};
    texture.FillImageViews(remapped, false, false);
    assert(texture.visit_calls == 3); // memo cannot reuse remapped view
    assert(texture.refreshes == 2);
    texture.slot_images[1].flags = 0;
    texture.visit_calls = texture.prepare_calls = 0;
    texture.one_deleted_retry = true;
    std::array<ImageViewInOut, 2> deleted{{{1}, {2}}};
    texture.FillImageViews(deleted, false, false);
    assert(!texture.has_deleted_images);
    assert(texture.visit_calls == 4); // complete restart after deletion
    texture.one_blacklist_retry = true;
    texture.scales = texture.visit_calls = 0;
    std::array<ImageViewInOut, 2> blacklist{{{1,true}, {1,true}}};
    texture.FillImageViews(blacklist, false, true);
    assert(texture.scales == 4); // both iterations apply blacklist
    assert(texture.visit_calls == 4); // no unsafe memo reuse under blacklist
    texture.has_deleted_images = true;
    texture.visit_calls = 0;
    std::span<ImageViewInOut> empty;
    texture.FillImageViews(empty, false, false);
    assert(!texture.has_deleted_images);
    assert(texture.visit_calls == 0);
}
""".replace("__ACTUAL_FILL__", actual)
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-hud-tic-freshness-") as tmp:
    src = Path(tmp) / "fill.cpp"
    src.write_text(code)
    for native in (False, True):
        for opt in ("-O0", "-O2"):
            exe = Path(tmp) / f"{'ps5' if native else 'desktop'}-{opt[1:]}"
            build = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native else []),
                 str(src), "-o", str(exe)], capture_output=True, text=True, timeout=45
            )
            assert build.returncode == 0, (native, opt, build.stderr[-6000:])
            out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=12)
            assert out.returncode == 0, (native, opt, out.stderr[-4000:])
            print(f"F07_HUD_TIC_FRESHNESS_PASS native={int(native)} {opt} repeated=1 remapped=1 deleted_retry=1 blacklist_retry=1 empty=1")
print("HOST_ONLY, no actual console HUD freshness or FC27 FPS claim")
