#!/usr/bin/env python3
"""Native release: locale-ranked physical cases keep order without N^2 dedup.

Compiles actual selected C++ SafeCaseFilename/SafeCaseCandidate/
LocaleCaseCandidates at -O0/-O2. The old linear dedup is kept as a test-only
oracle, never selected in the PS5 release.
"""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"headless/prosperoeden/eden_services.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
assert "prosperoeden/eden_services.cpp" in cmake or "eden_services.cpp" in cmake
begin="bool SafeCaseFilename(const std::string& file) {"
end="\nconst BoxIndex& RetailCaseIndex() {"
assert source.count(begin)==1 and source.count(end)==1
actual=begin+source.split(begin,1)[1].split(end,1)[0]
assert actual.count("std::unordered_set<std::string> seen;")==1
assert actual.count("if (seen.insert(candidate.file).second)")==1
assert "std::find(sorted.begin(), sorted.end(), candidate.file)" not in actual
assert "#include <unordered_set>" in source

cpp=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cctype>
#include <cstddef>
#include <string>
#include <unordered_set>
#include <vector>
namespace Eden {
static constexpr const char* kLanguageKeys[]={"en-US","fr","en-GB"};
}
""" + actual + r"""
std::vector<std::string> reference(const std::vector<std::string>& entries,
                                    int language_choice, int face) {
  // Previous linear duplicate elimination for a given region-ranked input.
  // Compare with source first-pass insertion order, including equal priorities.
  const std::string locale=Eden::kLanguageKeys[language_choice];
  std::vector<std::string> regions;
  if(locale=="fr")regions={"fr","eu","world","uk","ca","us"};
  else if(locale=="en-GB")regions=face==1?
      std::vector<std::string>{"uk","us","ca","world","eu"}:
      std::vector<std::string>{"uk","eu","us","world","ca"};
  else regions={"us","ca","world","uk","eu","fr"};
  struct Candidate{int priority;std::size_t order;std::string file;};
  std::vector<Candidate> choices;
  for(std::size_t i=0;i<entries.size();++i) {
    const auto& token=entries[i];
    if(!SafeCaseCandidate(token))continue;
    const auto colon=token.find(':');
    const std::string region=colon==std::string::npos?"other":token.substr(0,colon);
    const std::string file=colon==std::string::npos?token:token.substr(colon+1);
    int priority=100;
    for(std::size_t p=0;p<regions.size();++p)if(regions[p]==region){priority=int(p);break;}
    choices.push_back({priority,i,file});
  }
  std::stable_sort(choices.begin(),choices.end(),[](const auto& a,const auto& b){
    return a.priority < b.priority;
  });
  std::vector<std::string> sorted;
  for(const auto& c:choices)
    if(std::find(sorted.begin(),sorted.end(),c.file)==sorted.end())sorted.push_back(c.file);
  return sorted;
}
int main() {
  const std::string a(36,'A'),b(36,'B'),c(36,'C');
  std::vector<std::string> examples{
    "us:"+a+".jpg","fr:"+b+".png","eu:"+a+".jpg",
    "world:"+c+".jpg","us:"+b+".png","other:"+c+".jpg",
    "invalid/../../"+a+".jpg","eu:"+a+".jpg",
    a+".jpg"};
  for(int lang=0;lang<3;++lang)
    for(int face=0;face<2;++face) {
      auto expected=reference(examples,lang,face);
      auto produced=LocaleCaseCandidates(examples,lang,face);
      assert(produced==expected);
      assert(produced.size()==3);
    }
  std::vector<std::string> many;
  many.reserve(1200);
  for(int i=0;i<1200;++i) {
    std::string name(36,char('A'+(i%26)));
    many.push_back(std::string(i%3==0?"fr:":i%3==1?"us:":"eu:")+name+".jpg");
  }
  for(int lang=0;lang<3;++lang)
    for(int face=0;face<2;++face)
      assert(LocaleCaseCandidates(many,lang,face)==reference(many,lang,face));
  assert(LocaleCaseCandidates({},0,0).empty());
}
""";
with tempfile.TemporaryDirectory(prefix="encore-case-rank-") as td:
    src=Path(td)/"test.cpp";src.write_text(cpp)
    for opt in ("-O0","-O2"):
        binary=Path(td)/("test"+opt[2:])
        subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",opt,
                        str(src),"-o",str(binary)],check=True,capture_output=True,text=True)
        subprocess.run([str(binary)],check=True,capture_output=True,text=True)
print("ENCORE_RELEASE_CASE_RANK_DEDUP_HOST_PASS exact_native=1 O0=1 O2=1 stable_rank=1")
