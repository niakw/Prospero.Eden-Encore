#!/usr/bin/env python3
"""Host source-extracted release launcher cover clock + sorted missing lookup."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
hdr=(root/"headless/prosperoeden/pe/ui/textures.hpp").read_text()
src=(root/"headless/prosperoeden/pe/ui/textures.cpp").read_text()
lib=(root/"headless/prosperoeden/pe/ui/library.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
begin="Cover Textures::cover(const std::string &path, float size)"
end="\nvoid Textures::invalidate("
assert src.count(begin)==1 and end in src.split(begin,1)[1]
cover=begin+src.split(begin,1)[1].split(end,1)[0]
assert "double loaded_at_seconds = 0.0;" in hdr
assert "double uptime_seconds_ = 0.0;" in hdr
assert "uptime_seconds_ - it->second.loaded_at_seconds" in cover
assert "entry.age += dt;" not in src
pump=src.split("void Textures::pump(float dt, int budget)",1)[1]
assert "uptime_seconds_ += static_cast<double>(dt);" in pump
assert "entry.loaded_at_seconds = uptime_seconds_;" in pump
assert "it->second.loaded_at_seconds = uptime_seconds_;" in pump
assert "pe/ui/textures.cpp" in cmake and "pe/ui/library.cpp" in cmake
assert "std::sort(paths.begin(), paths.end());" in lib
assert "std::set_intersection(observed_missing.begin(), observed_missing.end()," in lib
assert lib.count("drop_missing_games(&missing);")==1
candidate="return std::binary_search(known_missing->begin(), known_missing->end(), game.file);"
assert lib.count(candidate)==1 and candidate in lib.split("bool Launcher::drop_missing_games(",1)[1]
cpp=r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <deque>
#include <iterator>
#include <string>
#include <unordered_map>
#include <vector>
struct Cover {std::uint32_t texture=0;float age=0;bool missing=false;float aspect=1;};
class Textures {
 public:
 struct Entry {std::uint32_t texture=0;double loaded_at_seconds=0;
  bool loaded=false;std::uint64_t generation=0;unsigned failed_loads=0;
  std::uint64_t used=0;std::string path;int target_pixels=64;float aspect=1;};
 std::unordered_map<std::string,Entry> covers_;
 std::deque<std::string> queue_;
 std::uint64_t frame_=0,next_generation_=0;
 double uptime_seconds_=0;float output_scale_=1;
 Cover cover(const std::string&,float);
 void tick(float dt){++frame_; uptime_seconds_+=static_cast<double>(dt);}
};
""" + cover + r"""
struct Game {std::string file;};
bool absent(const std::vector<std::string>* known_missing,const Game& game){
""" + candidate + r"""
}
int main(){
 Textures t;
 assert(t.cover("",256).missing && t.queue_.empty());
 for(int i=0;i<160;++i)t.cover("box-"+std::to_string(i),300);
 assert(t.covers_.size()==160);
 auto& e=t.covers_.at("box-0#512");
 t.tick(60);
 assert(t.cover("box-0",300).age==0);
 e.loaded=true;e.loaded_at_seconds=t.uptime_seconds_;
 t.tick(0.4f);
 auto a=t.cover("box-0",300);
 assert(a.missing && a.age>0.399f && a.age<0.401f);
 t.tick(0.06f);
 a=t.cover("box-0",300);
 assert(!e.loaded && a.age==0 && !a.missing);
 e.loaded=true;e.texture=812;e.aspect=0.75f;
 e.loaded_at_seconds=t.uptime_seconds_;t.tick(0.27f);
 a=t.cover("box-0",300);
 assert(a.texture==812 && !a.missing && std::fabs(a.age-.27f)<.001f && a.aspect==.75f);
 auto& retry=t.covers_.at("box-1#512");
 retry.loaded=true;retry.failed_loads=2;retry.loaded_at_seconds=t.uptime_seconds_;
 t.tick(1.49f);assert(t.cover("box-1",300).missing && retry.loaded);
 t.tick(.03f);assert(t.cover("box-1",300).missing && !retry.loaded);
 retry.loaded=true;retry.failed_loads=3;retry.loaded_at_seconds=t.uptime_seconds_;
 t.tick(2.9f);assert(t.cover("box-1",300).missing && retry.loaded);
 t.tick(.15f);assert(t.cover("box-1",300).missing && !retry.loaded);
 std::vector<std::string> old{"A","C","E","G"},now{"A","B","E","Z"},known;
 std::set_intersection(old.begin(),old.end(),now.begin(),now.end(),std::back_inserter(known));
 assert((known==std::vector<std::string>{"A","E"}));
 for(const char* p:{"A","B","C","E","F","G","Z"}){
   Game g{p};
   assert(absent(&known,g)==(std::find(known.begin(),known.end(),g.file)!=known.end()));
 }
 std::vector<std::string> many;
 for(int i=0;i<5000;++i)many.push_back("game-"+std::to_string(i));
 std::sort(many.begin(),many.end());
 for(int i=0;i<10000;++i){
   Game g{"game-"+std::to_string(i)};
   assert(absent(&many,g)==(std::find(many.begin(),many.end(),g.file)!=many.end()));
 }
}
""";
with tempfile.TemporaryDirectory(prefix="encore-launcher-release-") as td:
 p=Path(td)/"test.cpp";p.write_text(cpp)
 for opt in ("-O0","-O2"):
  binary=Path(td)/("test"+opt[2:])
  subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",opt,str(p),"-o",str(binary)],
                 check=True,capture_output=True,text=True)
  subprocess.run([str(binary)],check=True,capture_output=True,text=True)
print("ENCORE_RELEASE_LAUNCHER_HOTPATHS_PASS source_cover=1 O0=1 O2=1 sorted_worker=1")
