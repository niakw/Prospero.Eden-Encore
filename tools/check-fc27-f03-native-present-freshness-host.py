#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F03: one native C++ fixture ties TIC recovery to async Vulkan presentation.

Reuses the source-extracted selected TIC/sampler/feedback/descriptor program
from F03 plus the actual selected RendererVulkan::Composite and
PresentManager::GetRenderFrame/Present/WaitPresent/PresentThread. Mock GPU
render targets carry an explicit HUD frame-content revision, not real pixels.
The test proves no lost revision across source-backed CPU orchestration,
including 12 paused game ticks and a midstream texture remap. It is NOT
Vulkan device submission, WSI scanout, guest FC27 fidelity, or FPS evidence.
"""
import ast
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
CMD="python3 -B tools/check-fc27-f03-native-present-freshness-host.py"
assert CMD in FAST and CMD in FULL
VULKAN_CMAKE=(ROOT/"headless/vulkan.cmake").read_text()
for name in ("vulkan_renderer.cpp","vulkan_present_manager.cpp","vk_graphics_pipeline"):
    assert name in VULKAN_CMAKE,name

# Run independent F03 source-extraction assertions and get its exact C++
# source (methods + descriptor loop), then splice the class definitions
# before the selected real renderer/presenter C++ host fixture.
stage=runpy.run_path(str(ROOT/"tools/check-fc27-f03-native-texture-feedback-chain-host.py"))
textures=stage["source"]
assert textures.count("int main(){")==1
texture_types=textures.split("int main(){",1)[0]
f05=(ROOT/"tools/check-native-vulkan-renderer-handoff-host.py").read_text()
tree=ast.parse(f05)
templates=[]
for stmt in tree.body:
    if isinstance(stmt,ast.Assign) and any(
        isinstance(target,ast.Name) and target.id=="cpp" for target in stmt.targets
    ) and isinstance(stmt.value,ast.Constant) and isinstance(stmt.value.value,str):
        templates.append(stmt.value.value)
assert len(templates)==1
template=templates[0]
RENDER=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_renderer.cpp").read_text()
PRESENT=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
def native(text,start):
    assert text.count(start)==1,start
    begin=text.index(start)
    opening=text.index("{",begin)
    depth=0
    for i in range(opening,len(text)):
        if text[i]=="{":depth+=1
        elif text[i]=="}":
            depth-=1
            if depth==0:return text[begin:i+1]
    raise AssertionError(start)
present_methods="\n\n".join(native(PRESENT,s) for s in (
    "Frame* PresentManager::GetRenderFrame() {",
    "void PresentManager::Present(Frame* frame) {",
    "void PresentManager::WaitPresent() {",
    "void PresentManager::PresentThread(std::stop_token token) {",
))
render_method=native(RENDER,"void RendererVulkan::Composite(")
assert "#ifdef PS5_NATIVE" in texture_types
assert "CopyToSwapchain(frame);" in present_methods
assert "present_in_flight = false;" in present_methods
assert "present_manager.Present(frame);" in render_method
assert "scheduler.DispatchWork();" in render_method
cpp=template.replace("__PRESENT_METHODS__",present_methods).replace("__RENDER_METHOD__",render_method)
anchor="static void Deliver(RendererVulkan& renderer,"
assert cpp.count(anchor)==1
cpp=cpp.replace(anchor,texture_types+"\n"+anchor)
inject=r"""
    // F03: the same source-selected TIC view and sampler that produced
    // feedback barriers enter the selected native renderer + async
    // presentation handoff in one executable, without an inferred ACK.
    PresentManager fresh_present{7};
    RendererVulkan fresh_renderer{fresh_present};
    TextureCache<int> texture;
    texture.channel.graphics_image_table.descriptor=27;
    texture.channel.graphics_sampler_table.descriptor=4;
    texture.fail_first_view_creation=true;
    assert(texture.gpu_memory==&texture.memory);
    assert(texture.channel_state==&texture.channel);
    assert(texture.VisitImageView(5,false)==NULL_IMAGE_VIEW_ID);
    assert(texture.VisitImageView(5,false)==127);
    assert(texture.texture_bindings_serial==1);
    Info texture_draw{{Descriptor{{{127,3},{127,3}},2}}};
    std::vector<std::pair<std::uint32_t,std::uint32_t>> fresh_expected;
    std::uint32_t fresh_game=100;
    constexpr unsigned hud_ticks=240;
    for(unsigned tick=0;tick<hud_ticks;++tick){
        const bool paused=tick>=100 && tick<112;
        if(!paused && tick%2==0)++fresh_game;
        if(tick==120){
            // Guest TIC unchanged while backing image is remapped.
            texture.slot_images[127].flags.remapped=true;
            texture.rt_depth_image_id=128;
        }
        const auto view=texture.VisitImageView(5,false);
        assert(view==(tick<120?127u:128u));
        texture_draw.texture_descriptors[0].handles={{view,3},{view,3}};
        const auto output=BuildDraw(texture,texture_draw);
        assert(output.views.size()==2 && output.views[0].id==view);
        assert(output.samplers.size()==2 && output.samplers[0]==304);
        texture.CheckFeedbackLoop(output.views);
        assert(texture.runtime.calls==tick+1);
        // A real Vulkan resource would contain the HUD at revision 'tick'.
        // The mock render target carries both its view identity and the
        // content revision to prove ordering through native PresentThread.
        const std::uint32_t hud_content=view*100000u+tick;
        Deliver(fresh_renderer,fresh_game,hud_content);
        fresh_expected.emplace_back(fresh_game,hud_content);
        if(paused)assert(fresh_game==150);
    }
    fresh_present.WaitPresent();
    assert(fresh_present.presented==fresh_expected);
    assert(fresh_present.copies==hud_ticks);
    assert(fresh_renderer.gpu.notifications==hud_ticks);
    assert(fresh_renderer.rasterizer.ticks==hud_ticks);
    assert(fresh_renderer.render_window.displayed==hud_ticks);
    assert(texture.texture_bindings_serial==2);
    assert(texture.views_created==3);
    assert(texture.samplers_found==1);
    assert(texture.runtime.calls==hud_ticks);
    std::printf("F03_NATIVE_TIC_TO_PRESENT_FRESHNESS_PASS frames=%u "
                "hud_unique=%u remaps=1 pause_ticks=12 barriers=%u "
                "source_sections=9 scope=source_extracted_host_mock_gpu\n",
                hud_ticks,hud_ticks,texture.runtime.calls);
"""
tag='    std::printf("F05_VULKAN_RENDER_PRESENT_HOST_PASS '
assert cpp.count(tag)==1
cpp=cpp.replace(tag,inject+"\n"+tag)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f03-present-") as directory:
    source=Path(directory)/"hud_present.cpp"
    source.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(directory)/("hud"+opt)
        cmd=[compiler,"-std=c++20",opt,"-DPS5_NATIVE=1","-g","-pthread","-Wall","-Wextra",
             "-Werror","-fsanitize=undefined","-fno-sanitize-recover=all",
             str(source),"-o",str(exe)]
        built=subprocess.run(cmd,capture_output=True,text=True,timeout=70)
        assert built.returncode==0,(opt,built.stderr[-6500:])
        executed=subprocess.run([str(exe)],capture_output=True,text=True,timeout=40)
        assert executed.returncode==0,(opt,executed.stdout,executed.stderr[-5000:])
        assert executed.stdout.count("F03_NATIVE_TIC_TO_PRESENT_FRESHNESS_PASS")==1
        print(executed.stdout.strip(),opt,flush=True)
print("F03_REAL_GPU_PIXELS_AND_SCANOUT_NOT_PROVEN")
