# R333 — native PS5 GPU producer burst budget 8 → 32

Branch: `dev/ps5-sparse-jit`; source pinned to Eden mirror `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`. This is a bounded throughput change, not a declaration that FC27 is completely smooth.

## Critical capacity discovery

The pinned upstream GPU thread owns `Common::SPSCQueue<CommandDataContainer>` with a default capacity of **4096** (`src/common/bounded_threadsafe_queue.h`). Our actual generated headless CMake replaces it with `Common::SPSCQueue<CommandDataContainer, 8>`. All of R314–R332's native PS5 builds therefore had **8 queued commands**, not the 4096 sometimes assumed from upstream. The 8-command override is an implementation cap of our PS5 port, not a GPU hardware limit.

On the user's October 11 FC27 detailed run, 36 out of 175 five-second windows have GPU-queue-full waits, and these 36 windows contain 950 of the 1,035 intervals over 50 ms. The producer-side `gpu_full_ms` correlation with late50 is ~0.82 across those windows. This identifies backpressure associated with the bad windows, **not its unique cause**: queue-full time is relatively small compared with the longest hitches, and the GPU owner's service rate, guest synchronizations and other pacing must still be investigated. When the menu was visually frozen, the producer queue was **not** full, and game/GPU work continued, so the menu freeze is a separate issue.

## Narrow change and constraints

With `PS5_NATIVE` only, substitute a bounded capacity **32** for the previous 8. Preserve all existing SPSC FIFO, queue-full stop-token condition-variable wait, command fence ordering, notification and teardown logic. Do not restore the upstream 4096-entry queue: delaying producer backpressure for thousands of commands could inflate interactive latency and hide runaway submissions. The nonnative 8-entry port behavior remains unchanged.

Expected effect: up to 32 commands can be queued before producer sleeping, absorbing a short burst that would previously overflow the 8-entry ring. This does not itself make Vulkan/RADV or guest shader compilation faster. It may only shift backpressure and cannot be claimed to fix FPS or frame pacing without representative hardware evidence.

## Qualification

`tools/check-ps5-gpu-producer-wake.py` additionally host-exercises a 32-slot queue: accepts exactly 32 entries while its consumer is inactive, blocks on 33rd, wakes on a pop, and retains FIFO ordering, alongside the previous cancellation and 4000-command tests. `tools/check-ps5-quiet-gpu-hotpaths.py` now asserts the generated PS5-only budget and preserves quiet-path properties. Both are part of the existing source and native preflights.

The Mac-local Clang/libc++ environment cannot compile the existing `std::stop_token` host fixture, and its arm64 CPU cannot compile an x86 pause intrinsic used by the existing generic quiet-GPU unit; these are host environment limitations, **not passing local tests**. Use Linux CI and the full native PS5 C++ build gates. No user console retest requested at this stage: FC27 menu input and the image/texture quality defects remain under development.
