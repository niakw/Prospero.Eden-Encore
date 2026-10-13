R437 – FC27 stutter/HUD analysis (13 October 2026)

In the first heap segment, 609 five-second frame windows show 392 frames above 50 ms (max 532 ms). In the second 413 windows there are zero late 50 ms frames (max 36 ms). This is not a controlled A/B comparison, and does not prove subjective microstutters vanished.

Second segment: ~41.7 s cumulative guest buffer-mutex waiting, ~3.0 s texture-mutex waiting; 12.7 million blocked buffer acquisitions by the last sample. GPU draw-drop totals are all zero. Texture memory reports ~4.17 GiB against an expected ~4.72 GiB, memory_short=0. Missing HUD therefore cannot yet be attributed to memory shortage or dropped pipelines; synchronization/content coherency remains a candidate.

The native PS5 BufferCache template registers buffer address pages under the GPU cache mutex. R437 records those registered pages in a monotonic, separately scoped 4-KiB bitmap BEFORE publishing the page table entry. Only tiny CPU writes to pages never registered may skip the buffer mutex. Unknown ranges, out-of-space registrations, and writes >64 KiB use the original path. Previously registered pages NEVER become eligible for skipping through cache eviction.

HUD safety rule: texture_cache.WriteMemory and pipeline_cache.InvalidateRegion must run even when buffer mutex is skipped. The existing return-on-GPU-modified path remains. No modifications to shader settings, controller mapping, image fidelity, or the anti-flicker fence policy. An earlier Eden anti-flicker fence change (#4004) was later restricted due to side effects (#4010). Do not generalize it without an FC27-specific proof.

The release/acquire bitmap is conservative after a registration mark is observed, but does not establish full serialization of concurrent buffer registration and CPU writes. The source preflight includes a host multithreaded regression, and a native build plus hardware test will still be required before asserting improvement or HUD correctness.
