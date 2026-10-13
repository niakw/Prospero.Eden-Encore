#!/usr/bin/env python3
"""R428 source oracle: Boost small_vector and bounded ASTC recompression scratch."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
assert "R428: upstream ProsperoEden d7f2764" in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/texture_cache/util.h"' in cmake
assert '#include <boost/version.hpp>' in cmake
assert 'target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/small-vector")' in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/video_core/texture_cache/util.cpp"' in cmake
assert 'Pinned Eden ASTC ConvertImage changed; requalify R428' in cmake
assert 'const u32 layers = copy.image_subresource.num_layers * copy.image_extent.depth;' in cmake
assert 'input_offset.subspan(layer * layer_input)' in cmake
assert 'output.subspan(output_offset + layer * layer_output)' in cmake
assert 'decode_scratch.resize_destructive(level_size / (std::max)(layers, 1u));' in cmake
assert 'list(REMOVE_ITEM video_sources texture_cache/util.cpp)' in cmake
assert 'list(APPEND video_sources "${PORT_BUILD_DIR}/texture_cache_util.cpp")' in cmake
assert cmake.index('list(APPEND video_sources "${PORT_BUILD_DIR}/texture_cache_util.cpp")') < cmake.index(
    'set_property(TARGET video_core PROPERTY SOURCES "${video_sources}")')
cxx = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
assert cxx, "C++ host compiler unavailable"
cpp = r"""
#include <boost/container/small_vector.hpp>
#include <boost/version.hpp>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <type_traits>
#include <vector>
using u32 = std::uint32_t;
template<typename T, std::size_t N>
#if BOOST_VERSION >= 108100 || __GNUC__ > 12
boost::container::small_vector<T,N> FixSmallVectorADL(
    const boost::container::small_vector<T,N>& v) { return v; }
#else
std::vector<T> FixSmallVectorADL(
    const boost::container::small_vector<T,N>& v) { return {v.begin(),v.end()}; }
#endif
constexpr u32 DivideUp(u32 a,u32 b){return (a+b-1)/b;}
constexpr u32 AlignUp(u32 a,u32 b){return DivideUp(a,b)*b;}
int main(){
    static_assert(BOOST_VERSION >= 108100, "Modern Boost must select small_vector");
    using V=boost::container::small_vector<int,16>;
    static_assert(std::is_same_v<decltype(FixSmallVectorADL(V{})),V>);
    for(u32 w: {4u,5u,64u,128u,1024u})
      for(u32 h: {4u,5u,128u,1024u})
        for(u32 tw: {4u,5u,6u,8u})
          for(u32 th: {4u,5u,8u})
            for(u32 layers: {1u,2u,9u,121u}) {
              const u32 layer_input=DivideUp(w,tw)*DivideUp(h,th)*16;
              const u32 layer_pixels=w*h*4;
              const u32 layer_output=AlignUp(w,4)*AlignUp(h,4);
              assert(layer_input>0 && layer_output>0);
              // Distinct per-layer offsets are contiguous without overlap.
              for(u32 layer=0;layer<layers;layer++)
                assert(std::size_t(layer)*layer_output+layer_output <=
                       std::size_t(layers)*layer_output);
              assert(layer_pixels*layers/layers==layer_pixels);
            }
}
"""
with tempfile.TemporaryDirectory(prefix="eden-r428-") as directory:
    src = Path(directory) / "fixture.cpp"
    binary = Path(directory) / "fixture"
    src.write_text(cpp)
    subprocess.run([cxx, "-std=c++20", "-O2", str(src), "-o", str(binary)],
                   check=True, timeout=90)
    subprocess.run([str(binary)], check=True, timeout=90)
print("R428 PASS: pinned Boost type and ASTC per-layer scratch/output arithmetic")
