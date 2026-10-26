#!/usr/bin/env python3
"""Source-extracted release Font::fit - check codepoint output and no prefix copies."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
s=(root/"headless/prosperoeden/pe/gfx/font.cpp").read_text()
assert "pe/gfx/font.cpp" in (root/"headless/CMakeLists.txt").read_text()
start="std::string Font::fit(std::string_view text, float size, float max_width, float tracking) const"
assert s.count(start)==1
real=start+s.split(start,1)[1].split("\n}\n\n} // namespace pe::gfx",1)[0]+"\n}"
assert "result.append(text.substr(start, index - start));" in real
assert "result.resize(previous_size);" in real
assert "std::string candidate =" not in real
cpp=r"""
#include <cassert>
#include <cstddef>
#include <string>
#include <string_view>
#include <vector>
namespace pe::gfx {
char32_t next_codepoint(std::string_view s,std::size_t* i) {
 const auto lead=(unsigned char)s[*i];
 if(lead<128){++*i;return lead;}
 if((lead&0xe0)==0xc0&&*i+1<s.size()){*i+=2;return 0xe9;}
 if((lead&0xf0)==0xe0&&*i+2<s.size()){*i+=3;return 0x301;}
 if((lead&0xf8)==0xf0&&*i+3<s.size()){*i+=4;return 0x1f600;}
 ++*i;return '?';
}
namespace bidi {bool attaches(char32_t c){return c==0x301;}}
class Font {
public:
 float measure(std::string_view s,float size,float tracking)const {
   float width=0;
   for(std::size_t p=0;p<s.size();) {next_codepoint(s,&p);width+=size+tracking;}
   return width;
 }
 std::string fit(std::string_view,float,float,float)const;
};
""" + real + r"""
std::string before(const Font& f,std::string_view text,float size,float max_width,float tracking) {
 if(f.measure(text,size,tracking)<=max_width)return std::string(text);
 static constexpr std::string_view ellipsis="\xE2\x80\xA6";
 float room=max_width-f.measure(ellipsis,size,tracking)-tracking;
 std::string result;
 for(std::size_t index=0;index<text.size();) {
   const std::size_t start=index;
   next_codepoint(text,&index);
   for(std::size_t next=index;next<text.size();) {
     if(!bidi::attaches(next_codepoint(text,&next)))break;
     index=next;
   }
   const std::string candidate=result+std::string(text.substr(start,index-start));
   if(f.measure(candidate,size,tracking)>room)break;
   result=candidate;
 }
 while(!result.empty()&&result.back()==' ')result.pop_back();
 return result+std::string(ellipsis);
}
}
int main() {
 pe::gfx::Font font;
 const std::vector<std::string> cases={"FC27 player career mode",
 "Zelda Breath of the Wild", "Éden a\xCC\x81 feat. HUD",
 "menu menu menu menu menu menu",
 "  with trailing spaces  ","", "\xF0\x9F\x98\x80 emoji"};
 for(const auto& s:cases)for(float w:{-1.f,0.f,2.f,6.f,20.f,100.f})
 for(float track:{-.2f,0.f,.4f})
  assert(font.fit(s,1.f,w,track)==pe::gfx::before(font,s,1.f,w,track));
 for(int n=0;n<120;++n){
  const std::string s(n,'A');
  assert(font.fit(s,1.f,n/2.f,0)==pe::gfx::before(font,s,1.f,n/2.f,0));
 }
}
""";
with tempfile.TemporaryDirectory(prefix="encore-font-fit-") as tmp:
 p=Path(tmp)/"fit.cpp";p.write_text(cpp)
 for opt in ("-O0","-O2"):
  exe=Path(tmp)/("fit"+opt[2:])
  subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",opt,
                  str(p),"-o",str(exe)],check=True,capture_output=True,text=True)
  subprocess.run([str(exe)],check=True,capture_output=True,text=True)
print("ENCORE_RELEASE_FONT_FIT_HOST_PASS source=1 O0=1 O2=1 no_temp_candidate=1")
