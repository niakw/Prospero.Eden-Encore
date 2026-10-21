// ProsperoEden - RGBA images for textures: TGA files and box downsampling.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/gfx/image.hpp"

#include <cstdio>
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace pe::gfx
{

bool load_tga(const std::string &path, Image *image)
{
    *image = Image{};
    std::FILE *file = std::fopen(path.c_str(), "rb");
    if (file == nullptr)
        return false;
    unsigned char header[18]{};
    bool ok = std::fread(header, 1, sizeof(header), file) == sizeof(header);
    const int width = header[12] | (header[13] << 8);
    const int height = header[14] | (header[15] << 8);
    const int bytes = header[16] / 8;
    // No colour map, uncompressed true colour, at most 8192 pixels a side.
    ok = ok && header[1] == 0 && header[2] == 2 && (bytes == 3 || bytes == 4) && width > 0 &&
         height > 0 && width <= 8192 && height <= 8192;
    ok = ok && std::fseek(file, header[0], SEEK_CUR) == 0; // image ID field
    std::vector<std::uint8_t> raw;
    if (ok)
    {
        raw.resize(static_cast<std::size_t>(width) * static_cast<std::size_t>(height) *
                   static_cast<std::size_t>(bytes));
        ok = std::fread(raw.data(), 1, raw.size(), file) == raw.size();
    }
    std::fclose(file);
    if (!ok)
        return false;

    const bool top_first = (header[17] & 0x20) != 0;
    image->width = width;
    image->height = height;
    image->rgba.resize(static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 4);
    for (int y = 0; y < height; ++y)
    {
        const int source_row = top_first ? y : height - 1 - y;
        const std::uint8_t *in =
            raw.data() + static_cast<std::size_t>(source_row) * static_cast<std::size_t>(width) *
                             static_cast<std::size_t>(bytes);
        std::uint8_t *out =
            image->rgba.data() + static_cast<std::size_t>(y) * static_cast<std::size_t>(width) * 4;
        for (int x = 0; x < width; ++x, in += bytes, out += 4)
        {
            out[0] = in[2];
            out[1] = in[1];
            out[2] = in[0];
            out[3] = bytes == 4 ? in[3] : 255;
        }
    }
    return true;
}

Image halve(const Image &image)
{
    Image result;
    result.width = image.width / 2;
    result.height = image.height / 2;
    if (result.empty())
        return Image{};
    result.rgba.resize(static_cast<std::size_t>(result.width) *
                       static_cast<std::size_t>(result.height) * 4);
    const std::size_t stride = static_cast<std::size_t>(image.width) * 4;
    for (int y = 0; y < result.height; ++y)
    {
        const std::uint8_t *row = image.rgba.data() + static_cast<std::size_t>(y) * 2 * stride;
        std::uint8_t *out =
            result.rgba.data() + static_cast<std::size_t>(y) * static_cast<std::size_t>(result.width) * 4;
        for (int x = 0; x < result.width; ++x, out += 4)
        {
            const std::uint8_t *block[4] = {row + static_cast<std::size_t>(x) * 8,
                                            row + static_cast<std::size_t>(x) * 8 + 4,
                                            row + stride + static_cast<std::size_t>(x) * 8,
                                            row + stride + static_cast<std::size_t>(x) * 8 + 4};
            unsigned alpha = 0;
            unsigned color[3] = {0, 0, 0};
            for (const std::uint8_t *pixel : block)
            {
                alpha += pixel[3];
                for (int channel = 0; channel < 3; ++channel)
                    color[channel] += static_cast<unsigned>(pixel[channel]) * pixel[3];
            }
            for (int channel = 0; channel < 3; ++channel)
                out[channel] =
                    static_cast<std::uint8_t>(alpha != 0 ? (color[channel] + alpha / 2) / alpha : 0);
            out[3] = static_cast<std::uint8_t>((alpha + 2) / 4);
        }
    }
    return result;
}


namespace avatar_detail {
inline std::uint16_t U16(const std::uint8_t* p) noexcept {
    return std::uint16_t(p[0]) | (std::uint16_t(p[1]) << 8);
}
inline std::uint32_t U32(const std::uint8_t* p) noexcept {
    return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) |
           (std::uint32_t(p[2]) << 16) | (std::uint32_t(p[3]) << 24);
}
inline std::uint8_t Channel(std::uint32_t pixel, std::uint32_t mask,
                            std::uint8_t absent = 0) noexcept {
    if (!mask) return absent;
    unsigned shift = 0;
    while (!(mask & 1u)) { mask >>= 1; ++shift; }
    const std::uint32_t bits = (pixel >> shift) & mask;
    return static_cast<std::uint8_t>((std::uint64_t(bits) * 255u + mask / 2u) / mask);
}
using Pixel = std::array<std::uint8_t, 4>;
inline Pixel Rgb565(std::uint16_t bits) noexcept {
    return {static_cast<std::uint8_t>(((bits >> 11) & 31u) * 255u / 31u),
            static_cast<std::uint8_t>(((bits >> 5) & 63u) * 255u / 63u),
            static_cast<std::uint8_t>((bits & 31u) * 255u / 31u), 255u};
}
inline void Colors(const std::uint8_t* p, bool opaque, Pixel (&table)[4]) noexcept {
    const auto a = U16(p), b = U16(p + 2);
    table[0] = Rgb565(a);
    table[1] = Rgb565(b);
    if (a > b || opaque) {
        for (int channel = 0; channel < 3; ++channel) {
            table[2][channel] = static_cast<std::uint8_t>(
                (2u * table[0][channel] + table[1][channel]) / 3u);
            table[3][channel] = static_cast<std::uint8_t>(
                (table[0][channel] + 2u * table[1][channel]) / 3u);
        }
        table[2][3] = table[3][3] = 255;
    } else {
        for (int channel = 0; channel < 3; ++channel)
            table[2][channel] = static_cast<std::uint8_t>(
                (table[0][channel] + table[1][channel]) / 2u);
        table[2][3] = 255;
        table[3] = {0, 0, 0, 0};
    }
}
} // namespace avatar_detail

inline bool load_avatar_dds(const std::string& path, Image* image) {
    if (!image) return false;
    *image = {};
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    if (std::fseek(f, 0, SEEK_END) != 0) { std::fclose(f); return false; }
    const long length = std::ftell(f);
    // An avatar cannot legitimately need megabytes of compressed payload.
    if (length < 128 || length > (4L << 20) || std::fseek(f, 0, SEEK_SET) != 0) {
        std::fclose(f);
        return false;
    }
    std::vector<std::uint8_t> data(static_cast<std::size_t>(length));
    const bool read = std::fread(data.data(), 1, data.size(), f) == data.size();
    std::fclose(f);
    if (!read) return false;
    using namespace avatar_detail;
    const auto* b = data.data();
    if (U32(b) != 0x20534444u || U32(b + 4) != 124 ||
        U32(b + 76) != 32) return false;
    const auto height = U32(b + 12), width = U32(b + 16);
    if (!width || !height || width > 512 || height > 512) return false;

    constexpr std::uint32_t dxt1 = 0x31545844u, dxt3 = 0x33545844u,
                            dxt5 = 0x35545844u, dx10 = 0x30315844u;
    auto format = U32(b + 84);
    std::size_t offset = 128;
    if (format == dx10) {
        if (data.size() < 148) return false;
        const auto dxgi = U32(b + 128);
        offset = 148;
        format = (dxgi == 71 || dxgi == 72) ? dxt1 :
                 (dxgi == 74 || dxgi == 75) ? dxt3 :
                 (dxgi == 77 || dxgi == 78) ? dxt5 :
                 (dxgi == 28 || dxgi == 29 || dxgi == 87 || dxgi == 91) ? 0u : 0xffffffffu;
    }
    const bool compressed = format == dxt1 || format == dxt3 || format == dxt5;
    if (!compressed && format != 0) return false;
    const std::size_t blocks_w = (width + 3u) / 4u, blocks_h = (height + 3u) / 4u;
    const std::size_t bytes_per_block = format == dxt1 ? 8u : 16u;
    std::size_t pitch = static_cast<std::size_t>(width) * 4u;
    if (!compressed && (U32(b + 8) & 8u) && U32(b + 20) >= pitch)
        pitch = U32(b + 20);
    if (pitch > 8192u) return false;
    const std::size_t required = compressed ? blocks_w * blocks_h * bytes_per_block :
                                                pitch * height;
    if (offset > data.size() || required > data.size() - offset) return false;
    std::uint32_t red = U32(b + 92), green = U32(b + 96),
                  blue = U32(b + 100), alpha = U32(b + 104);
    if (!compressed && !red && !green && !blue) {
        // Explicit DX10 RGBA and BGRA formats; legacy unmasked RGB is rejected.
        if (U32(b + 84) != dx10) return false;
        const auto dxgi = U32(b + 128);
        if (dxgi == 28 || dxgi == 29) {
            red = 0x000000ffu; green = 0x0000ff00u;
            blue = 0x00ff0000u; alpha = 0xff000000u;
        } else {
            red = 0x00ff0000u; green = 0x0000ff00u;
            blue = 0x000000ffu; alpha = 0xff000000u;
        }
    }
    if (!compressed && U32(b + 88) != 32 && U32(b + 84) != dx10) return false;
    image->width = static_cast<int>(width);
    image->height = static_cast<int>(height);
    image->rgba.resize(static_cast<std::size_t>(width) * height * 4u);
    if (!compressed) {
        for (std::size_t y = 0; y < height; ++y)
            for (std::size_t x = 0; x < width; ++x) {
                const auto pixel = U32(b + offset + y * pitch + x * 4u);
                const auto out = (y * width + x) * 4u;
                image->rgba[out] = Channel(pixel, red);
                image->rgba[out + 1] = Channel(pixel, green);
                image->rgba[out + 2] = Channel(pixel, blue);
                image->rgba[out + 3] = Channel(pixel, alpha, 255);
            }
        return true;
    }
    for (std::size_t by = 0; by < blocks_h; ++by)
        for (std::size_t bx = 0; bx < blocks_w; ++bx) {
            const auto* block = b + offset + (by * blocks_w + bx) * bytes_per_block;
            const auto* color = block + (format == dxt1 ? 0 : 8);
            Pixel palette[4]{};
            Colors(color, format != dxt1, palette);
            const auto indices = U32(color + 4);
            std::uint64_t alpha_bits = 0;
            if (format == dxt5)
                for (unsigned j = 0; j < 6; ++j)
                    alpha_bits |= std::uint64_t(block[j + 2]) << (j * 8);
            std::uint8_t alpha_palette[8]{};
            if (format == dxt5) {
                alpha_palette[0] = block[0]; alpha_palette[1] = block[1];
                if (block[0] > block[1]) {
                    for (unsigned k = 2; k < 8; ++k)
                        alpha_palette[k] = static_cast<std::uint8_t>(
                            ((8u - k) * block[0] + (k - 1u) * block[1]) / 7u);
                } else {
                    for (unsigned k = 2; k < 6; ++k)
                        alpha_palette[k] = static_cast<std::uint8_t>(
                            ((6u - k) * block[0] + (k - 1u) * block[1]) / 5u);
                    alpha_palette[6] = 0; alpha_palette[7] = 255;
                }
            }
            for (unsigned py = 0; py < 4; ++py)
                for (unsigned px = 0; px < 4; ++px) {
                    const auto x = bx * 4u + px, y = by * 4u + py;
                    if (x >= width || y >= height) continue;
                    const unsigned i = py * 4u + px;
                    Pixel rgba = palette[(indices >> (2u * i)) & 3u];
                    if (format == dxt3)
                        rgba[3] = static_cast<std::uint8_t>(
                            ((block[i / 2u] >> ((i & 1u) * 4u)) & 15u) * 17u);
                    else if (format == dxt5)
                        rgba[3] = alpha_palette[(alpha_bits >> (3u * i)) & 7u];
                    const auto out = (static_cast<std::size_t>(y) * width + x) * 4u;
                    for (unsigned channel = 0; channel < 4; ++channel)
                        image->rgba[out + channel] = rgba[channel];
                }
        }
    return true;
}
} // namespace pe::gfx
