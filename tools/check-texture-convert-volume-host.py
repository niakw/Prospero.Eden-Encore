#!/usr/bin/env python3
"""Execute real ConvertImage layout code; decoder stubs enforce full-volume writes."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
def method(path):
    text = path.read_text()
    start = text.index('void ConvertImage(')
    return text[start:text.index('\nboost::container::small_vector<BufferImageCopy, 16> FullDownloadCopies', start)]
previous = method(ROOT / 'vendor/sources/eden/src/video_core/texture_cache/util.cpp')
current = method(ROOT / 'vendor/encore-active/eden-core/src/video_core/texture_cache/util.cpp')
decoder = (ROOT / 'vendor/sources/eden/src/video_core/texture_cache/decode_bc.cpp').read_text()
assert 'const u32 depth = copy.image_extent.depth;' in decoder
assert 'for (u32 slice = 0; slice < depth; ++slice)' in decoder
cpp = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <span>
#include <vector>
#include "common/scratch_buffer.h"
using u8=std::uint8_t; using u32=std::uint32_t; using s32=std::int32_t;
#define ASSERT(x) assert(x)
enum class PixelFormat { ASTC, BC7, A8B8G8R8_UNORM };
struct Extent2D { u32 width,height; };
struct Extent3D { u32 width,height,depth; bool operator==(const Extent3D&) const=default; };
struct Offset3D { s32 x{},y{},z{}; bool operator==(const Offset3D&) const=default; };
struct Subresource { u32 base_level{},base_layer{},num_layers{}; };
struct ImageInfo { Extent3D size; PixelFormat format; };
struct BufferImageCopy {
    std::size_t buffer_offset{},buffer_size{};
    u32 buffer_row_length{},buffer_image_height{};
    Subresource image_subresource; Offset3D image_offset; Extent3D image_extent;
};
namespace Common {
template<class A,class B> auto AlignUp(A n,B a) { return (n+a-1)/a*a; }
u32 DivideUp(u32 n,u32 d) { return (n+d-1)/d; }
}
namespace Settings {
enum class AstcRecompression { Uncompressed,Bc1,Bc3 };
unsigned reads;
struct Setting {
    AstcRecompression mode;
    AstcRecompression GetValue() const { ++reads; return mode; }
};
struct Values { Setting astc_recompression; } values;
}
Extent2D DefaultBlockSize(PixelFormat) { return {4,4}; }
Extent3D AdjustMipSize(Extent3D s,s32 l) { return {std::max(1u,s.width>>l),std::max(1u,s.height>>l),std::max(1u,s.depth>>l)}; }
bool IsPixelFormatASTC(PixelFormat f) { return f==PixelFormat::ASTC; }
u32 BytesPerBlock(PixelFormat) { return 4; }
u32 ConvertedBytesPerBlock(PixelFormat) { return 4; }
void Decode(std::span<const u8> input,u32 w,u32 h,u32 layers,std::span<u8> output) {
    const auto bytes=std::size_t(w)*h*layers*4;
    assert(!input.empty() && output.size()>=bytes);
    std::fill_n(output.begin(),bytes,input.front());
}
namespace Tegra::Texture::ASTC {
void Decompress(std::span<const u8> input,u32 w,u32 h,u32 layers,u32,u32,std::span<u8> output) { Decode(input,w,h,layers,output); }
}
namespace Tegra::Texture::BCN {
void Compress(std::span<const u8> input,u32 w,u32 h,u32 layers,std::span<u8> output,u32 divisor) {
    const auto bytes=std::size_t(Common::AlignUp(w,4))*Common::AlignUp(h,4)*layers/divisor;
    assert(!input.empty() && output.size()>=bytes);
    std::fill_n(output.begin(),bytes,input.front());
}
void CompressBC1(std::span<const u8> in,u32 w,u32 h,u32 n,std::span<u8> out) { Compress(in,w,h,n,out,2); }
void CompressBC3(std::span<const u8> in,u32 w,u32 h,u32 n,std::span<u8> out) { Compress(in,w,h,n,out,1); }
}
void DecompressBCn(std::span<const u8> in,std::span<u8> out,BufferImageCopy& c,PixelFormat) {
    Decode(in,c.image_extent.width,c.image_extent.height,c.image_extent.depth*c.image_subresource.num_layers,out);
}
namespace Before { BEFORE }
namespace After { AFTER }
using Converter=void(*)(std::span<const u8>,const ImageInfo&,std::span<u8>,std::span<BufferImageCopy>);
bool Run(Converter convert,const ImageInfo& info,u32 layers,Settings::AstcRecompression mode,unsigned& reads) {
    Settings::values.astc_recompression.mode=mode;
    std::vector<u8> input,expected;
    std::vector<BufferImageCopy> copies;
    std::vector<std::size_t> expected_offsets;
    for(u32 level=0;level<3;++level) {
        auto size=AdjustMipSize(info.size,level);
        const auto input_bytes=std::size_t(Common::DivideUp(size.width,4))*Common::DivideUp(size.height,4)*16*size.depth*layers;
        copies.push_back({input.size(),input_bytes,Common::AlignUp(size.width,4),Common::AlignUp(size.height,4),{level,0,layers},{},size});
        input.insert(input.end(),input_bytes,static_cast<u8>(0x40+level));
        expected_offsets.push_back(expected.size());
        const bool compressed=info.format==PixelFormat::ASTC && mode!=Settings::AstcRecompression::Uncompressed;
        const auto bytes=compressed ? std::size_t(Common::AlignUp(size.width,4))*Common::AlignUp(size.height,4)*size.depth*layers/(mode==Settings::AstcRecompression::Bc1?2:1)
                                    : std::size_t(size.width)*size.height*size.depth*layers*4;
        expected.insert(expected.end(),bytes,static_cast<u8>(0x40+level));
    }
    std::vector<u8> output(expected.size()+32,0xcc);
    Settings::reads=0;
    convert(input,info,std::span<u8>(output).first(expected.size()),copies);
    reads=Settings::reads;
    bool good=std::equal(expected.begin(),expected.end(),output.begin());
    for(std::size_t i=0;i<copies.size();++i) good&=copies[i].buffer_offset==expected_offsets[i];
    assert(std::all_of(output.end()-32,output.end(),[](u8 b){return b==0xcc;}));
    return good;
}
int main() {
    using R=Settings::AstcRecompression;
    unsigned old_reads{},new_reads{};
    for(auto format:{PixelFormat::ASTC,PixelFormat::BC7}) {
        ImageInfo volume{{16,16,4},format};
        assert(!Run(Before::ConvertImage,volume,1,R::Uncompressed,old_reads));
        assert(Run(After::ConvertImage,volume,1,R::Uncompressed,new_reads));
        assert(old_reads==3 && new_reads==1);
        ImageInfo array{{16,16,1},format};
        assert(Run(Before::ConvertImage,array,3,R::Uncompressed,old_reads));
        assert(Run(After::ConvertImage,array,3,R::Uncompressed,new_reads));
        assert(old_reads==3 && new_reads==1);
    }
    for(auto mode:{R::Bc1,R::Bc3})
        for(u32 depth:{1u,4u})
            assert(Run(After::ConvertImage,{{16,16,depth},PixelFormat::ASTC},2,mode,new_reads));
    Settings::reads=0;
    After::ConvertImage({},{{16,16,1},PixelFormat::ASTC},{},{});
    assert(Settings::reads==0);
    std::puts("TEXTURE_VOLUME_LAYOUT_PASS old_3D_overlap_reproduced=2 current_mip_ranges_disjoint=1 arrays=preserved BC1_BC3=preserved settings_reads=3->1 empty_reads=0");
}
'''.replace('BEFORE',previous).replace('AFTER',current)
compiler=shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
with tempfile.TemporaryDirectory(prefix='encore-texture-volume-') as temp:
    source,binary=Path(temp)/'main.cpp',Path(temp)/'volume';source.write_text(cpp)
    subprocess.run([compiler,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                    '-I'+str(ROOT/'vendor/sources/eden/src'),str(source),'-o',str(binary)],check=True,timeout=60)
    subprocess.run([str(binary)],check=True,timeout=30)
print('TEXTURE_LAYOUT_HOST_ONLY decoded_pixel_quality_and_PS5_graphics=unverified')
