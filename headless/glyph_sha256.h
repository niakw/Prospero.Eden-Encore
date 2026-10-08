// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal bounded SHA-256 for validating installed in-game graphic assets.
// This does NOT authenticate the Nintendo original currently mounted by Eden.
// Host-tested known vectors; a cryptographic signature of the catalogue is
// a separate distribution/trust problem. Never execute on the frame hotpath.
#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>

namespace Eden::GlyphIntegrity {
class Sha256 {
    std::array<std::uint32_t, 8> state_{
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    std::array<std::uint8_t, 64> buffer_{};
    std::size_t filled_ = 0;
    std::uint64_t bytes_ = 0;

    static constexpr std::array<std::uint32_t, 64> kRound{
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    static constexpr std::uint32_t Rot(std::uint32_t v, unsigned count) noexcept {
        return (v >> count) | (v << (32u - count));
    }
    void Block(const std::uint8_t* input) noexcept {
        std::array<std::uint32_t, 64> words{};
        for (unsigned i = 0; i < 16; ++i)
            words[i] = (std::uint32_t(input[i * 4]) << 24) |
                       (std::uint32_t(input[i * 4 + 1]) << 16) |
                       (std::uint32_t(input[i * 4 + 2]) << 8) | input[i * 4 + 3];
        for (unsigned i = 16; i < 64; ++i) {
            const auto a = words[i - 15], b = words[i - 2];
            words[i] = words[i - 16] + (Rot(a, 7) ^ Rot(a, 18) ^ (a >> 3)) +
                       words[i - 7] + (Rot(b, 17) ^ Rot(b, 19) ^ (b >> 10));
        }
        auto [a,b,c,d,e,f,g,h] = state_;
        for (unsigned i = 0; i < 64; ++i) {
            const auto choose = (e & f) ^ (~e & g);
            const auto majority = (a & b) ^ (a & c) ^ (b & c);
            const auto t1 = h + (Rot(e, 6) ^ Rot(e, 11) ^ Rot(e, 25)) + choose +
                            kRound[i] + words[i];
            const auto t2 = (Rot(a, 2) ^ Rot(a, 13) ^ Rot(a, 22)) + majority;
            h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }
        state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
        state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
    }
public:
    void Update(const void* bytes, std::size_t size) noexcept {
        const auto* source = static_cast<const std::uint8_t*>(bytes);
        bytes_ += size;
        while (size != 0) {
            const std::size_t count = std::min(size, buffer_.size() - filled_);
            std::memcpy(buffer_.data() + filled_, source, count);
            filled_ += count; source += count; size -= count;
            if (filled_ == buffer_.size()) {
                Block(buffer_.data());
                filled_ = 0;
            }
        }
    }
    std::string FinishHex() noexcept {
        const std::uint64_t bits = bytes_ * 8;
        buffer_[filled_++] = 0x80;
        if (filled_ > 56) {
            std::fill(buffer_.begin() + filled_, buffer_.end(), 0);
            Block(buffer_.data());
            filled_ = 0;
        }
        std::fill(buffer_.begin() + filled_, buffer_.begin() + 56, 0);
        for (unsigned i = 0; i < 8; ++i)
            buffer_[56 + i] = static_cast<std::uint8_t>(bits >> (56 - 8 * i));
        Block(buffer_.data());
        constexpr char alphabet[] = "0123456789abcdef";
        std::string out(64, '0');
        for (unsigned i = 0; i < 8; ++i)
            for (unsigned j = 0; j < 4; ++j) {
                const auto octet = static_cast<unsigned>((state_[i] >> (24 - 8 * j)) & 0xff);
                out[i * 8 + j * 2] = alphabet[octet >> 4];
                out[i * 8 + j * 2 + 1] = alphabet[octet & 15];
            }
        return out;
    }
};

// Reads a bounded file in 32 KiB chunks, checking I/O state; no allocation
// proportional to the graphics asset. Return nullopt on missing/truncated,
// oversized, unreadable or otherwise unstable files.
inline std::optional<std::string> FileSha256(
    const std::filesystem::path& path, std::uintmax_t max_bytes = 128u * 1024u * 1024u) {
    std::error_code error;
    const auto length = std::filesystem::file_size(path, error);
    if (error || length > max_bytes) return std::nullopt;
    std::ifstream input(path, std::ios::binary);
    if (!input) return std::nullopt;
    Sha256 hash;
    std::array<char, 32768> buffer{};
    std::uintmax_t observed = 0;
    while (input) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto got = input.gcount();
        if (got < 0 || observed + static_cast<std::uintmax_t>(got) > max_bytes) return std::nullopt;
        if (got > 0) {
            hash.Update(buffer.data(), static_cast<std::size_t>(got));
            observed += static_cast<std::uintmax_t>(got);
        }
    }
    if (!input.eof() || observed != length) return std::nullopt;
    return hash.FinishHex();
}
} // namespace Eden::GlyphIntegrity
