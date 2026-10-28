#!/usr/bin/env python3
"""Execute full old/new presentation Draw through real deferred scheduler chunks."""
from pathlib import Path
import ast
import hashlib
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / 'vendor/encore-active/eden-vulkan'
tree = ast.parse((ROOT / 'tools/prepare-vulkan-port.py').read_text())
edits = next(ast.literal_eval(n.value) for n in tree.body
             if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
             t.id == 'present_draw_edits' for t in n.targets))
current = (ACTIVE / 'vulkan_window_adapt_pass.cpp').read_text()
previous = current
# Source-owning audit already validates the five exact Vulkan warm-up
# presentation deltas against the generated native code. Restore those
# deltas in the OLD-side comparison only: preserve the original pinned
# Git blob SHA, while exercising the actual new shipping Draw() below.
validator = ast.parse((ROOT / 'tools/check-vendored-vulkan-fork.py').read_text())
loader_edits = next(ast.literal_eval(node.iter) for node in ast.walk(validator)
    if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple)
    and [v.id for v in node.target.elts if isinstance(v, ast.Name)] == ['before', 'after']
    and isinstance(node.iter, ast.Tuple))
assert len(loader_edits) == 5
for old, new in reversed(loader_edits):
    assert previous.count(new) == 1, 'unreviewed loading-presenter modification'
    previous = previous.replace(new, old)
for old, new in reversed(edits):
    assert previous.count(new) == 1, new
    previous = previous.replace(new, old)
blob = previous.encode()
assert hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest() == '888b70b1e9d9a2e4bd47d2417a41c093b03d51b6', 'unreviewed presentation source change'
def draw(source):
    start = source.index('void WindowAdaptPass::Draw(')
    return source[start:source.index('\nVkDescriptorSetLayout WindowAdaptPass::GetDescriptorSetLayout', start)]
header = (ACTIVE / 'include/video_core/renderer_vulkan/vk_scheduler.h').read_text()
chunk = header[header.index('    class Command {'):header.index('    struct State {')].replace('private:', 'public:')
record_start = '    template <typename T>\n        requires std::is_invocable_v<T, vk::CommandBuffer, vk::CommandBuffer>'
record = header[header.index(record_start):header.index('    /// Returns the current command buffer tick.')]
scheduler = (ACTIVE / 'vulkan_scheduler.cpp').read_text()
begin = scheduler.index('void Scheduler::CommandChunk::ExecuteAll(')
execute = scheduler[begin:scheduler.index('\n}\n', begin) + 3]
cpp = r'''
#include <vulkan/vulkan_core.h>
#include <boost/container/small_vector.hpp>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <initializer_list>
#include <list>
#include <memory>
#include <new>
#include <span>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>
#include "video_core/renderer_vulkan/present/present_push_constants.h"
#include "hud.h"
using u8 = std::uint8_t; using u64 = std::uint64_t;
unsigned allocations;
void* operator new(std::size_t n) { ++allocations; if (void* p=std::malloc(n)) return p; throw std::bad_alloc{}; }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }
namespace Common { std::size_t AlignUp(std::size_t n,std::size_t a){return (n+a-1)&~(a-1);} }
struct Event { unsigned kind; std::vector<u8> data; bool operator==(const Event&) const=default; };
namespace vk { struct CommandBuffer {
    std::vector<Event>* events;
    template<class... T> void Log(unsigned kind,const T&... value) const {
        Event event{kind,{}};
        const auto append=[&](const auto& v) { const auto* b=reinterpret_cast<const u8*>(&v); event.data.insert(event.data.end(),b,b+sizeof(v)); };
        (append(value),...);events->push_back(std::move(event));
    }
    void ClearAttachments(std::initializer_list<VkClearAttachment> a,std::initializer_list<VkClearRect> r) const {Log(1,*a.begin(),*r.begin());}
    void BindPipeline(VkPipelineBindPoint b,VkPipeline p) const {Log(2,b,p);}
    template<class T> void PushConstants(VkPipelineLayout l,VkShaderStageFlags s,const T& v) const {Log(3,l,s,v);}
    void BindDescriptorSets(VkPipelineBindPoint b,VkPipelineLayout l,unsigned i,VkDescriptorSet d,std::initializer_list<unsigned>) const {Log(4,b,l,i,d);}
    void Draw(unsigned a,unsigned b,unsigned c,unsigned d) const {Log(5,a,b,c,d);}
    void SetViewport(unsigned i,VkViewport v) const {Log(6,i,v);}
    void SetScissor(unsigned i,VkRect2D r) const {Log(7,i,r);}
    void EndRenderPass() const {Log(8,0u);}
}; }
namespace Vulkan {
class Scheduler {
public:
CHUNK
RECORD
    std::array<CommandChunk,2> chunks;
    CommandChunk* chunk=&chunks[0];
    unsigned switches{};
    unsigned invalidations{};
    // The production RecordWithUploadBuffer reset hook is part of the
    // extracted scheduler, even though this fixture tests accepted draws.
    void InvalidateState() { ++invalidations; }
    void DispatchWork() { assert(++switches==1);chunk=&chunks[1]; }
    void ForceRollover() { chunks[0].command_offset=0x8000-1; }
    void Drain(std::vector<Event>& events) { for(auto& c:chunks)c.ExecuteAll({&events},{&events}); assert(chunks[0].Empty()&&chunks[1].Empty()); }
};
EXECUTE
}
namespace Settings {
struct Setting { unsigned value; unsigned GetValue() const {return value;} };
struct Values { Setting bg_red{13},bg_green{71},bg_blue{129}; } values;
}
namespace Eden { HudSnapshot snapshot; HudSnapshot GetVulkanHud(){return snapshot;} }
namespace Tegra { enum class BlendMode { Opaque,Premultiplied,Coverage }; struct FramebufferConfig {BlendMode blending; unsigned seed;}; }
namespace Layout { struct FramebufferLayout {}; }
template<class T> T Handle(std::uintptr_t value) { if constexpr(std::is_pointer_v<T>)return reinterpret_cast<T>(value); else return static_cast<T>(value); }
template<class T> struct Owned { T value{}; T operator*()const{return value;} explicit operator bool()const{return value!=T{};} };
struct Logical { Owned<VkPipelineLayout> CreatePipelineLayout(const VkPipelineLayoutCreateInfo&) const {return {Handle<VkPipelineLayout>(91)};} };
struct Device {Logical GetLogical() const{return {};}};
struct RasterizerVulkan {};
struct Frame { Owned<VkFramebuffer> framebuffer{Handle<VkFramebuffer>(7)};unsigned width=1920,height=1080;};
struct Layer {
    void ConfigureDraw(const Device&,Vulkan::PresentPushConstants* constants,VkDescriptorSet* descriptor,
        RasterizerVulkan&,VkSampler,std::size_t image_index,const Tegra::FramebufferConfig& config,const Layout::FramebufferLayout&) {
        for(std::size_t i=0;i<constants->modelview_matrix.size();++i)constants->modelview_matrix[i]=float(config.seed*5+i+image_index);
        for(auto& vertex:constants->vertices)vertex=Vulkan::ScreenRectVertex(float(config.seed),1.f,2.f,3.f);
        *descriptor=Handle<VkDescriptorSet>(1000+config.seed);
    }
};
struct Shader {};
constexpr unsigned EDEN_HUD_VERT_SPV=1,EDEN_HUD_FRAG_SPV=2;
Shader BuildShader(const Device&,unsigned){return {};}
template<class T> Owned<VkPipeline> CreateWrappedCoverageBlendingPipeline(const Device&,Owned<VkRenderPass>,Owned<VkPipelineLayout>,T){return {Handle<VkPipeline>(92)};}
void BeginRenderPass(vk::CommandBuffer cmd,VkRenderPass r,VkFramebuffer f,VkExtent2D area){cmd.Log(0,r,f,area);}
struct Pass {
    Owned<VkRenderPass> render_pass{Handle<VkRenderPass>(1)};
    Owned<VkPipelineLayout> pipeline_layout{Handle<VkPipelineLayout>(2)},hud_layout{};
    Owned<VkSampler> sampler{Handle<VkSampler>(3)};
    Owned<VkPipeline> opaque_pipeline{Handle<VkPipeline>(4)},premultiplied_pipeline{Handle<VkPipeline>(5)},coverage_pipeline{Handle<VkPipeline>(6)},hud_pipeline{};
};
#define DECLARE_DRAW void Draw(const Device&,RasterizerVulkan&,Vulkan::Scheduler&,size_t,std::list<Layer>&,std::span<const Tegra::FramebufferConfig>,const Layout::FramebufferLayout&,Frame*,bool);
namespace Before { using Vulkan::PresentPushConstants;using Vulkan::Scheduler;struct WindowAdaptPass:Pass {DECLARE_DRAW}; BEFORE }
namespace After { using Vulkan::PresentPushConstants;using Vulkan::Scheduler;struct WindowAdaptPass:Pass {DECLARE_DRAW}; AFTER }
template<class P> unsigned Submit(P& pass,Vulkan::Scheduler& scheduler,unsigned count,unsigned hud_mode,unsigned frame) {
    Device device;RasterizerVulkan rasterizer;Layout::FramebufferLayout layout;
    Frame target;target.width=frame==2?96u:1920u;target.height=frame==2?40u:1080u;
    std::list<Layer> layers(count);
    std::vector<Tegra::FramebufferConfig> configs;
    for(unsigned i=0;i<count;++i)configs.push_back({static_cast<Tegra::BlendMode>((i+frame)%4),i+frame*100});
    Eden::snapshot=hud_mode==2?Eden::MakeLoadingSnapshot(1.25):Eden::HudSnapshot{};
    if(hud_mode==1){Eden::snapshot.width=100;Eden::snapshot.glyphs[0]=33;}
    const auto before=allocations;
    pass.Draw(device,rasterizer,scheduler,frame,layers,configs,layout,&target,hud_mode!=0);
    return allocations-before;
}
int main() {
    for(unsigned count:{0u,1u,2u,8u,32u})for(unsigned hud:{0u,1u,2u}) {
        Before::WindowAdaptPass before;After::WindowAdaptPass after;
        Vulkan::Scheduler old_scheduler,new_scheduler;
        old_scheduler.ForceRollover();new_scheduler.ForceRollover();
        unsigned old_alloc{},new_alloc{};
        for(unsigned f=0;f<3;++f){old_alloc+=Submit(before,old_scheduler,count,hud,f);new_alloc+=Submit(after,new_scheduler,count,hud,f);}
        assert(old_alloc==(count?18u:0u));assert(new_alloc==(count>1?3u:0u));
        Eden::snapshot={};Settings::values.bg_red.value=51;
        std::vector<Event> old_events,new_events;
        old_scheduler.Drain(old_events);new_scheduler.Drain(new_events);
        assert(old_scheduler.switches==1 && new_scheduler.switches==1);
        // Every scheduled draw was accepted: no false state invalidation.
        assert(old_scheduler.invalidations==0 && new_scheduler.invalidations==0);
        if(hud!=2) {
            // Real game layers, blend modes and the user-controlled FPS HUD
            // must remain byte-for-byte equal to the pinned renderer.
            assert(old_events==new_events);
        } else {
            // The *only intentional* visual difference is during warm-up:
            // no obsolete purple fullscreen HUD, same layer draws and
            // same number of completed render passes.
            assert(old_events!=new_events);
            const auto tally=[](const std::vector<Event>& events,unsigned kind) {
                unsigned n=0;for(const auto& e:events)n+=e.kind==kind;return n;
            };
            assert(tally(new_events,5)==3u*count);
            assert(tally(old_events,5)==3u*(count+1u));
            assert(tally(new_events,8)==3u && tally(old_events,8)==3u);
            assert(tally(new_events,6)==0u && tally(new_events,7)==0u);
        }
        assert(old_events.size()>=9);
        // Reuse the actual chunks after command destruction.
        Submit(before,old_scheduler,count,hud,3);Submit(after,new_scheduler,count,hud,3);
        old_scheduler.Drain(old_events);new_scheduler.Drain(new_events);
        if(hud!=2) assert(old_events==new_events);
        if(hud==0)std::printf("PRESENT_STORAGE layers=%u allocations_per_frame=%u->%u\n",count,old_alloc/3,new_alloc/3);
    }
    std::puts("PRESENT_STORAGE_PASS configurations=15 delayed_frames=3 blend_order=preserved HUD=preserved caller_storage_destroyed=1 actual_chunk_rollover_reuse=1 ASan_UBSan=1");
}
'''.replace('CHUNK',chunk).replace('RECORD',record).replace('EXECUTE',execute).replace('BEFORE',draw(previous)).replace('AFTER',draw(current))
compiler=shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
includes=['-I'+str(p) for p in sorted((ROOT/'vendor/sources/eden-cpm/boost/boost-1.90.0').glob('libs/*/include'))]
includes += ['-I'+str(ROOT/'vendor/sources/eden-cpm/vulkanheaders/v1.4.345/include'),'-I'+str(ROOT/'vendor/sources/eden/src'),'-I'+str(ROOT/'headless')]
with tempfile.TemporaryDirectory(prefix='encore-present-storage-') as temp:
    unit,binary=Path(temp)/'main.cpp',Path(temp)/'present';unit.write_text(cpp)
    subprocess.run([compiler,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-DPS5_NATIVE=1',
                    '-fsanitize=address,undefined','-fno-sanitize-recover=all',*includes,str(unit),'-o',str(binary)],check=True,timeout=90)
    subprocess.run([str(binary)],check=True,timeout=30)
print('PRESENT_STORAGE_HOST_ONLY real_GPU_pixels_and_PS5_frametimes=unverified')
