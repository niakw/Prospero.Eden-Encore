#!/usr/bin/env python3
"""Source-extracted native launcher GL scissor reuse; no real GL driver needed."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"headless/prosperoeden/pe/gfx/gl_batch.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
head="void GlBatch::draw(const DrawList &list, const Viewport &viewport, int surface_width,"
assert source.count(head)==1 and "pe/gfx/gl_batch.cpp" in cmake
method=head+source.split(head,1)[1].split("\n}\n\n} // namespace pe::gfx",1)[0]+"\n}"
assert method.count("glScissor(")==1
assert method.count("last_scissor_clip = run.clip;")==1
assert "const bool new_scissor =" in method
assert "if (!scissor)" in method and "else if (scissor)" in method
code=r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <tuple>
#include <vector>
using GLuint=unsigned; using GLint=int; using GLsizei=int; using GLsizeiptr=std::ptrdiff_t;
#define GL_ARRAY_BUFFER 1
#define GL_STREAM_DRAW 2
#define GL_BLEND 3
#define GL_SRC_ALPHA 4
#define GL_ONE_MINUS_SRC_ALPHA 5
#define GL_ONE 6
#define GL_DEPTH_TEST 7
#define GL_CULL_FACE 8
#define GL_TEXTURE0 9
#define GL_TEXTURE_2D 10
#define GL_SCISSOR_TEST 11
#define GL_TRIANGLES 12
#define glBindBuffer(...) ((void)0)
#define glBufferData(...) ((void)0)
#define glBufferSubData(...) ((void)0)
#define glViewport(...) ((void)0)
#define glBlendFuncSeparate(...) ((void)0)
#define glUseProgram(...) ((void)0)
#define glUniform4f(...) ((void)0)
#define glUniform2f(...) ((void)0)
#define glUniform1i(...) ((void)0)
#define glActiveTexture(...) ((void)0)
#define glBindVertexArray(...) ((void)0)
#define glBindTexture(...) ((void)0)
#define glDrawArraysInstancedBaseInstance(...) ((void)0)
struct Rect {float x=0,y=0,w=0,h=0;};
struct Viewport {float scale=1,offset_x=0,offset_y=0;};
struct Instance {char bytes[96]{};};
struct Run {std::uint32_t first=0,count=0,texture=0;bool clipped=false;Rect clip;};
struct DrawList {
 std::vector<Instance> values;
 std::vector<Run> segments;
 const std::vector<Instance>& instances()const{return values;}
 const std::vector<Run>& runs()const{return segments;}
};
std::vector<std::tuple<int,int,int,int>> submitted;
int scissor_enable=0,scissor_disable=0;
void glEnable(int mode){if(mode==GL_SCISSOR_TEST)++scissor_enable;}
void glDisable(int mode){if(mode==GL_SCISSOR_TEST)++scissor_disable;}
void glScissor(GLint x,GLint y,GLsizei w,GLsizei h){submitted.emplace_back(x,y,w,h);}
constexpr std::size_t kStreamBufferSlots=3;
std::size_t StreamCapacity(std::size_t old,std::size_t required){return std::max(old,required);}
class GlBatch {
 public:
 GLuint buffers_[3]{1,2,3},vaos_[3]{1,2,3},program_=1;
 std::size_t capacities_[3]{},next_slot_=0,draw_calls_=0;
 void draw(const DrawList&,const Viewport&,int,int);
};
""" + method + r"""
int main(){
 GlBatch batch;
 DrawList list;
 const Rect first{3,4,20,10}, second{7,8,8,6};
 for(int i=0;i<6;++i){
   Run r;
   r.first=i;r.count=1;r.texture=i+1;
   r.clipped=i!=4;
   r.clip=(i<3?first:second);
   list.segments.push_back(r);
   list.values.emplace_back();
 }
 const Viewport viewport{2,10,6};
 batch.draw(list,viewport,200,100);
 assert(batch.draw_calls_==6);
 assert(submitted.size()==3); // first, different, re-enabled after off
 assert((submitted[0]==std::tuple<int,int,int,int>{16,66,40,20}));
 assert((submitted[1]==std::tuple<int,int,int,int>{24,66,16,12}));
 assert(submitted[2]==submitted[1]);
 assert(scissor_enable==2 && scissor_disable==2);
 submitted.clear();scissor_enable=0;scissor_disable=0;
 batch.draw(list,viewport,200,100);
 assert(submitted.size()==3); // never leaks state across framebuffer draws
}
""";
with tempfile.TemporaryDirectory(prefix="encore-release-gl-scissor-") as d:
 src=Path(d)/"case.cpp";src.write_text(code)
 for opt in ("-O0","-O2"):
  exe=Path(d)/("case"+opt[2:])
  subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Wno-unused-parameter","-Werror",opt,
                  str(src),"-o",str(exe)],check=True,capture_output=True,text=True)
  subprocess.run([str(exe)],check=True,capture_output=True,text=True)
print("ENCORE_GL_SCISSOR_REUSE_HOST_PASS selected_source=1 O0=1 O2=1 clipping_preserved=1")
