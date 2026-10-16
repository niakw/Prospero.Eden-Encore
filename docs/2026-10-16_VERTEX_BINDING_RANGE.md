# Protect Vulkan vertex-binding counts from reversed ranges

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

The native Vulkan `BufferCacheRuntime::BindVertexBuffers` clamps each
`HostBindings` endpoint to `device.GetMaxVertexInputBindings()`, then
previously subtracted two unsigned `u32` endpoints and rejected only an
**exactly zero** result. An inverted range could therefore underflow to
a giant `binding_count`, passed to Vulkan with much smaller backing vectors.

The caller normally constructs ordered ranges. This is a defensive backend
boundary check for corrupted or unexpected binding metadata, not evidence
that a particular game currently reaches it.

The source and pinned generator now reject `max_binding <= min_binding`
**before** the subtraction. Valid ranges, clipping and both Vulkan
binding modes are unchanged. The source-extracted C++20 ASan/UBSan fixture
verifies ordinary, clipped, empty, reversed and max-u32 inputs. CI also checks
41-file Vulkan generator parity.

No descriptor-buffer lifetime, GPU fence, draw order, console build or
release is modified. This does not establish that FC27's HUD, freezes or
stutters are fixed.
