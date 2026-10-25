#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05 native nvdisp+Host1x -> Vulkan renderer+async Present integration.

Link TWO source-extracted C++ translation units together. TU1 executes real
nvdisp::Composite/WaitForComposite, GPU::Impl::RequestComposite and selected
Host1x syncpoint operations. Its mock Renderer forwards *only delivered*
framebuffer layers to TU2. TU2 executes the selected RendererVulkan::Composite
and PresentManager::{GetRenderFrame,Present,WaitPresent,PresentThread}.
The same 260 guest-fence-gated frame submissions must appear at the copy
completion boundary in the same order, without a stale/duplicate frame.
No actual HID/IPC, guest scheduling, Vulkan GPU/WSI, game or console proof.
"""
from pathlib import Path
import ast
import importlib.util
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
cmd="python3 -B tools/check-fc27-f05-native-nvdisp-vulkan-present-chain-host.py"
assert cmd in fast and cmd in pre
NV=(ROOT/"vendor/sources/eden/src/core/hle/service/nvdrv/devices/nvdisp_disp0.cpp").read_text()
GPU=(ROOT/"vendor/sources/eden/src/video_core/gpu.cpp").read_text()
SYNC=(ROOT/"vendor/encore-active/eden-core/src/video_core/host1x/syncpoint_manager.cpp").read_text()
RENDER=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_renderer.cpp").read_text()
PRESENT=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
cmake=(ROOT/"headless/vulkan.cmake").read_text()
assert "vulkan_present_manager.cpp" in cmake and "vulkan_renderer.cpp" in cmake
assert "renderer->Composite(composite_layers);" in GPU
assert "CopyToSwapchain(frame);" in PRESENT

def native(text,signature):
    assert text.count(signature)==1,("source drift",signature)
    start=text.index(signature)
    brace=text.index("{",start)
    depth=0
    for i in range(brace,len(text)):
        if text[i]=="{":depth+=1
        if text[i]=="}":
            depth-=1
            if depth==0:return text[start:i+1]
    raise AssertionError("unbalanced source "+signature)

def fixture(path):
    parsed=ast.parse((ROOT/path).read_text())
    matches=[ast.literal_eval(node.value) for node in parsed.body
             if isinstance(node,ast.Assign)
             and any(isinstance(t,ast.Name) and t.id=="cpp" for t in node.targets)
             and isinstance(node.value,ast.Constant)
             and isinstance(node.value.value,str)]
    assert len(matches)==1,(path,len(matches))
    return matches[0]

def once(text,old,new,label):
    assert text.count(old)==1,(label,text.count(old))
    return text.replace(old,new)

host=fixture("tools/check-native-gpu-composite-syncpoint-host.py")
nvmethods="\n".join(native(NV,signature) for signature in (
    "void nvdisp_disp0::Composite(",
    "void nvdisp_disp0::WaitForComposite(",
))
gpumethods="\n".join(native(GPU,signature) for signature in (
    "    void RequestComposite(",
    "    void WaitForComposite(",
))
start=SYNC.index("namespace {\n// Each domain")
stop=SYNC.index("\nSyncpointManager::ActionHandle",start)
helpers=SYNC[start:stop].replace("std::array<std::recursive_mutex, 192>& HostDispatchLocks()",
                                   "[[maybe_unused]] std::array<std::recursive_mutex, 192>& HostDispatchLocks()")
syncmethods="\n".join(native(SYNC,signature) for signature in (
    "SyncpointManager::ActionHandle SyncpointManager::RegisterAction(",
    "void SyncpointManager::IncrementGuest(",
    "void SyncpointManager::Increment(",
))
host=once(host,"__NV_METHODS__",nvmethods,"nvdisp")
host=once(host,"__GPU_METHODS__",gpumethods,"GPU")
host=once(host,"__SYNC_METHODS__",helpers+"\n"+syncmethods,"Host1x")
host=once(host,"namespace Service::Nvidia {",
    """extern "C" void F05PipeStart();
extern "C" void F05PipeForward(std::uint64_t game,std::uint64_t hud);
extern "C" void F05PipeDrain(unsigned count);
namespace Service::Nvidia {""","bridge prototypes")
host=once(host,"        deliveries.push_back(std::move(ids));",
    """        assert(!layers.empty());
        const u64 game=layers.front().address;
        const u64 hud=layers.size()>1 ? layers[1].address : (game ^ 0x9aULL);
        F05PipeForward(game,hud);
        deliveries.push_back(std::move(ids));""",
    "native renderer bridge")
host=once(host,"int main() {\n    Core::System system;",
    "int main() {\n    F05PipeStart();\n    Core::System system;","start pipeline")
host=once(host,"    assert(renderer.deliveries.size()==260);\n    std::puts(",
    "    assert(renderer.deliveries.size()==260);\n    F05PipeDrain(260);\n    std::puts(","complete pipeline")
assert "F05PipeForward(game,hud);" in host and "F05PipeDrain(260);" in host

vulkan=fixture("tools/check-native-vulkan-renderer-handoff-host.py")
presentmethods="\n\n".join(native(PRESENT,sig) for sig in (
    "Frame* PresentManager::GetRenderFrame() {",
    "void PresentManager::Present(Frame* frame) {",
    "void PresentManager::WaitPresent() {",
    "void PresentManager::PresentThread(std::stop_token token) {",
))
composite=native(RENDER,"void RendererVulkan::Composite(")
# Both C++ translation units instantiate std::span<Tegra::FramebufferConfig>.
# Reuse the full pinned guest FramebufferConfig declaration verbatim. Two
# different definitions with the same C++ mangled type would violate ODR and
# can silently use the wrong stride for the second layer on some compilers.
guest_fb=native(host,"struct FramebufferConfig {")
# Also include its BlendMode member type in precisely the same form.
vulkan=once(vulkan,
    "namespace Tegra {\nstruct FramebufferConfig {std::uint64_t address{};};\n}",
    "using u64 = std::uint64_t;\nnamespace Tegra {\nenum class BlendMode { Opaque };\n"+guest_fb+";\n}",
    "identical guest/renderer span layout")
vulkan=once(vulkan,"__PRESENT_METHODS__",presentmethods,"present methods")
vulkan=once(vulkan,"__RENDER_METHOD__",composite,"renderer")
vulkan=once(vulkan,"int main(){","void F05StandalonePresentationReplay(){","different mains")
# One living instance of the real native renderer/presenter methods accepts
# every Host1x-gated completion, rather than resetting the mock each frame.
vulkan+=r"""
static std::unique_ptr<PresentManager> pipeline_present;
static std::unique_ptr<RendererVulkan> pipeline_renderer;
static std::vector<std::pair<std::uint32_t,std::uint32_t>> pipeline_expected;
extern "C" void F05PipeStart() {
    assert(!pipeline_present && !pipeline_renderer && pipeline_expected.empty());
    pipeline_present=std::make_unique<PresentManager>(7);
    pipeline_renderer=std::make_unique<RendererVulkan>(*pipeline_present);
}
extern "C" void F05PipeForward(std::uint64_t game,std::uint64_t hud) {
    assert(pipeline_present && pipeline_renderer);
    assert(game<=UINT32_MAX && hud<=UINT32_MAX);
    auto g=static_cast<std::uint32_t>(game),h=static_cast<std::uint32_t>(hud);
    pipeline_expected.emplace_back(g,h);
    Deliver(*pipeline_renderer,g,h);
}
extern "C" void F05PipeDrain(unsigned expected_count) {
    assert(pipeline_present && pipeline_renderer);
    pipeline_present->WaitPresent();
    assert(pipeline_expected.size()==expected_count);
    if(pipeline_present->presented!=pipeline_expected) {
        const auto& observed=pipeline_present->presented;
        const auto& expected=pipeline_expected;
        std::size_t first=0;
        while(first<observed.size() && first<expected.size() &&
              observed[first]==expected[first])++first;
        auto og=first<observed.size()?observed[first].first:0;
        auto oh=first<observed.size()?observed[first].second:0;
        auto eg=first<expected.size()?expected[first].first:0;
        auto eh=first<expected.size()?expected[first].second:0;
        std::fprintf(stderr,
            "F05_NATIVE_PRESENT_MISMATCH expected_count=%zu actual_count=%zu "
            "first=%zu expected_game=%u expected_hud=%u "
            "actual_game=%u actual_hud=%u\\n",
            expected.size(),observed.size(),first,eg,eh,og,oh);
        assert(false && "guest layers and Vulkan-present image revisions diverged");
    }
    assert(pipeline_present->copies==expected_count);
    assert(pipeline_renderer->render_window.displayed==expected_count);
    assert(pipeline_renderer->gpu.notifications==expected_count);
    assert(pipeline_renderer->scheduler.dispatches==expected_count);
    assert(pipeline_renderer->rasterizer.ticks==expected_count);
    {
        std::lock_guard lock{pipeline_present->queue_mutex};
        assert(pipeline_present->present_queue.empty() && !pipeline_present->present_in_flight);
    }
    {
        std::lock_guard lock{pipeline_present->free_mutex};
        assert(pipeline_present->free_queue.size()==7);
    }
    pipeline_renderer.reset();
    pipeline_present.reset();
    pipeline_expected.clear();
    std::printf("F05_NATIVE_NVDISP_VULKAN_PRESENT_CHAIN_PASS requests=%u copies=%u "
                "async_frame_pool=7 fence_gated=1 frame_order_preserved=1 "
                "scope=source_extracted_host_mock_wsi_and_gpu\n",
                expected_count,expected_count);
}
"""
assert 'extern "C" void F05PipeForward' in host
assert 'extern "C" void F05PipeForward' in vulkan
assert "CopyToSwapchain(frame);" in presentmethods

# F05 surface producer/consumer extension: embed the precise C++ body
# extracted by the existing maintained HardwareComposer liveness witness.
# The resulting third TU routes queue-acquired graphic-buffer identities to
# the same Vulkan presenter as the native NvDisp -> GPU -> Host1x replay.
# This is a combined *host* witness; incoming guest Binder/IPC and WSI are
# still replaced by explicitly named adapters.
installer_path=ROOT/"tools/install-vendored-surface-lifecycle.py"
spec=importlib.util.spec_from_file_location("f05_surface_owner",installer_path)
assert spec and spec.loader
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
original_composer,active_composer=installer.check_composer()
assert original_composer!=active_composer
hw_source=active_composer.decode()
normalized=native(hw_source,"s32 NormalizeSwapInterval(")
hw_methods="\n\n".join(native(hw_source,signature) for signature in (
    "u32 HardwareComposer::ComposeLocked(",
    "void HardwareComposer::ReleaseFramebuffersLocked(",
    "bool HardwareComposer::TryAcquireFramebufferLocked(",
    "HardwareComposer::CacheStatus HardwareComposer::CacheFramebufferLocked(",
))
consumer_source=(ROOT/"vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp").read_text()
consumer_methods="\n\n".join(native(consumer_source,signature) for signature in (
    "Status BufferQueueConsumer::AcquireBuffer(",
    "Status BufferQueueConsumer::ReleaseBuffer(",
))
producer_source=(ROOT/"vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
queued=producer_source[producer_source.index("Status BufferQueueProducer::QueueBuffer("):
                       producer_source.index("\nvoid BufferQueueProducer::CancelBuffer(")]
producer_publish=queued[queued.index("        ++core->frame_counter;"):
                       queued.index("        output->Inflate(")]
producer_callback=queued[queued.index("    // Notify consumers with the actual queued item:"):]
assert producer_callback.endswith("return Status::NoError;\n}\n")
assert "slots[slot].fence = fence;" in producer_publish
assert "listener_available->OnFrameAvailable(item);" in producer_callback
compositor_module=ast.parse((ROOT/"tools/check-native-hardware-composer-liveness-host.py").read_text())
assignments=[n.value for n in compositor_module.body if isinstance(n,ast.Assign)
             and any(isinstance(target,ast.Name) and target.id=="fixture"
                     for target in n.targets)
             and isinstance(n.value,ast.BinOp)]
assert len(assignments)==1
def resolve_template(expression):
    if isinstance(expression,ast.Constant) and isinstance(expression.value,str):
        return expression.value
    if isinstance(expression,ast.Name):
        return {"helper":normalized,"methods":hw_methods}[expression.id]
    if isinstance(expression,ast.BinOp) and isinstance(expression.op,ast.Add):
        return resolve_template(expression.left)+resolve_template(expression.right)
    raise AssertionError("unrecognized native compositor fixture expression")
compositor=resolve_template(assignments[0])
for key,value in (
    ("__CONSUMER_METHODS__",consumer_methods),
    ("__PRODUCER_PUBLISH__",producer_publish),
    ("__PRODUCER_CALLBACK__",producer_callback),
):
    compositor=once(compositor,key,value,"compositor "+key)
# The full historical test main has its own standalone stress cases; the
# three-TU integration replaces only that entrypoint with a shared adapter.
assert compositor.count("int main() {")==1
compositor=compositor[:compositor.index("int main() {")]
compositor=once(compositor,
    "namespace Nvidia::Devices {",
    'extern "C" void F05PipeForward(std::uint64_t game,std::uint64_t hud);\n'
    'namespace Nvidia::Devices {',
    "present adapter declaration")
compositor=once(compositor,
    "        composed.push_back(std::move(ids));",
    """        if (pipe_enabled) {
            assert(ids.size()==2);
            // Only the identities emitted by native BufferQueue and the
            // source-extracted HardwareComposer may enter the presenter.
            F05PipeForward(static_cast<u64>(ids[0]),static_cast<u64>(ids[1]));
        }
        composed.push_back(std::move(ids));""",
    "composer forwarding")
compositor=once(compositor,
    "    int wait_count{};\n    std::vector<std::vector<int>> composed;",
    "    int wait_count{};\n    bool pipe_enabled{};\n    std::vector<std::vector<int>> composed;",
    "composer enabled")
compositor+=r"""
struct F05QueuePipeline {
    HardwareComposer composer;
    Display display;
    Nvidia::Devices::nvdisp_disp0 nvdisp;
    std::shared_ptr<MockConsumer> game_consumer=std::make_shared<MockConsumer>();
    std::shared_ptr<MockConsumer> hud_consumer=std::make_shared<MockConsumer>();
    std::shared_ptr<Layer> game_layer=std::make_shared<Layer>();
    std::shared_ptr<Layer> hud_layer=std::make_shared<Layer>();
    unsigned submitted{};
    F05QueuePipeline() {
        game_layer->consumer_id=37;
        game_layer->buffer_item_consumer=game_consumer;
        hud_layer->consumer_id=38;
        hud_layer->z_index=1;
        hud_layer->is_overlay=true;
        hud_layer->buffer_item_consumer=hud_consumer;
        display.stack.layers={game_layer,hud_layer};
        nvdisp.pipe_enabled=true;
    }
};
static std::unique_ptr<F05QueuePipeline> pipeline_queue;
extern "C" void F05QueueStart(){
    assert(!pipeline_queue);
    pipeline_queue=std::make_unique<F05QueuePipeline>();
}
extern "C" void F05QueueSubmit(std::uint64_t game,std::uint64_t hud){
    assert(pipeline_queue);
    assert(game<=static_cast<std::uint64_t>(std::numeric_limits<int>::max()));
    assert(hud<=static_cast<std::uint64_t>(std::numeric_limits<int>::max()));
    auto& pipe=*pipeline_queue;
    const auto before=pipe.nvdisp.composed.size();
    pipe.game_consumer->pending.push_back(frame(static_cast<int>(game),1));
    pipe.hud_consumer->pending.push_back(frame(static_cast<int>(hud),1));
    f32 speed=0;
    assert(pipe.composer.ComposeLocked(&speed,pipe.display,pipe.nvdisp)==1);
    assert(pipe.nvdisp.composed.size()==before+1);
    assert((pipe.nvdisp.composed.back()==std::vector<int>{
        static_cast<int>(game),static_cast<int>(hud)}));
    assert(pipe.nvdisp.fences.back()==pipe.nvdisp.composed.back());
    ++pipe.submitted;
}
extern "C" void F05QueueDrain(unsigned expected){
    assert(pipeline_queue);
    auto& pipe=*pipeline_queue;
    assert(pipe.submitted==expected);
    assert(pipe.nvdisp.composed.size()==expected);
    assert(pipe.nvdisp.wait_count==static_cast<int>(expected));
    assert(pipe.game_consumer->successful_acquires==expected);
    assert(pipe.hud_consumer->successful_acquires==expected);
    assert(pipe.game_consumer->queue->consumer_listener->available==expected);
    assert(pipe.hud_consumer->queue->consumer_listener->available==expected);
    assert(pipe.game_consumer->pending.empty() && pipe.hud_consumer->pending.empty());
    assert(pipe.game_consumer->releases+1==expected);
    assert(pipe.hud_consumer->releases+1==expected);
    pipeline_queue.reset();
    std::printf("F05_NATIVE_BUFFERQUEUE_TO_VULKAN_CHAIN_PASS "
                "queued=%u acquired_game=%u acquired_hud=%u "
                "composite=%u callback_frames=%u "
                "scope=source_extracted_host_mock_binder_and_wsi\n",
                expected,expected,expected,expected,expected);
}
"""
# Keep the prior passing fence/Vulkan C++ methods and assertions untouched,
# changing ONLY their bridge from a direct fixture call into the queue producer.
host=once(host,
    'extern "C" void F05PipeDrain(unsigned count);',
    'extern "C" void F05PipeDrain(unsigned count);\n'
    'extern "C" void F05QueueStart();\n'
    'extern "C" void F05QueueSubmit(std::uint64_t game,std::uint64_t hud);\n'
    'extern "C" void F05QueueDrain(unsigned count);',
    "queue adapter declarations")
host=once(host,"        F05PipeForward(game,hud);",
          "        F05QueueSubmit(game,hud);","queue submission")
host=once(host,"    F05PipeStart();\n    Core::System system;",
          "    F05PipeStart();\n    F05QueueStart();\n    Core::System system;",
          "queue startup")
host=once(host,"    F05PipeDrain(260);\n    std::puts(",
          "    F05QueueDrain(260);\n    F05PipeDrain(260);\n    std::puts(",
          "queue drain")
assert "F05QueueSubmit(game,hud);" in host
assert "F05PipeForward(static_cast<u64>(ids[0]),static_cast<u64>(ids[1]));" in compositor

compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f05-guest-to-present-") as d:
    p=Path(d)
    a=p/"guest.cpp";b=p/"present.cpp";c=p/"surface.cpp"
    a.write_text(host);b.write_text(vulkan);c.write_text(compositor)
    for opt in ("-O0","-O2"):
        exe=p/("chain"+opt)
        build=subprocess.run([compiler,"-std=c++20",opt,"-pthread","-Wall",
                 "-Wextra","-Werror","-fsanitize=undefined",
                 "-fno-sanitize-recover=all",str(a),str(b),str(c),"-o",str(exe)],
                 text=True,capture_output=True,timeout=90)
        assert build.returncode==0,(opt,build.stderr[-9000:])
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=45)
        assert run.returncode==0,(opt,run.stderr[-6000:],run.stdout[-6000:])
        assert "F05_NATIVE_BUFFERQUEUE_TO_VULKAN_CHAIN_PASS queued=260" in run.stdout
        assert "F05_NATIVE_NVDISP_VULKAN_PRESENT_CHAIN_PASS requests=260 copies=260" in run.stdout
        assert "F05_NV_DISP_GPU_SYNCPOINT_SOURCE_PASS requests=260" in run.stdout
        print(run.stdout.strip(),opt,flush=True)
print("F05_HID_IPC_AND_REAL_VULKAN_GPU_PRESENT_NOT_PROVEN")
