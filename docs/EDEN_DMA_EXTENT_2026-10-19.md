# DMA extent correction · 19 October 2026

`AccelerateDMA::DmaBufferImageCopy` previously multiplied two u32
guest dimensions before converting the already-wrapped product to
u32 for the Vulkan buffer cache. The accelerated path now widens first
and returns `false` for unrepresentable transfers.

The complete maintained native
`vendor/encore-active/eden-core/src/video_core/engines/maxwell_dma.cpp`
now handles three software fallback extents using u64 arithmetic and
u32 upper bounds. The intermediate calculation checks division before
multiplication to avoid overflow even at u64 width. Negative minimum
pitch magnitude is widened before absolute value. The outer DMA
launch still releases its guest semaphore; normal-size copies follow
the original path.

Native CMake selects this complete unit under `encore-active`; host
builds and pinned sources remain unchanged. The source-extracted
`tools/check-native-dma-extent-host.py` enforces full replay parity
and executes the real guard expressions under ASan/UBSan, covering
large/normal/zero and signed-minimum cases. No console-build or FPS
improvement is claimed from this host-only witness.
