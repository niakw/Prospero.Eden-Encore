# Safe graphics uniform binding when a GPU virtual address is unmapped

## Verified failure mode

`BufferCache::BindGraphicsUniformBuffer` originally dereferenced the
`std::optional<DAddr>` returned by `gpu_memory->GpuToCpuAddress(gpu_addr)`
without checking whether the mapping existed. The result can be empty for
an unmapped GPU address, so dereferencing it is undefined behavior.
Other buffer-cache translation consumers, including compute uniform,
vertex, index, indirect and transform-feedback paths, already guard
unmapped addresses.

## Selected native fix

- For a missing GPU-to-CPU translation, retire the graphics stage's previous
  uniform binding with the existing `NULL_BINDING` sentinel and return.
- For valid translations, preserve the original binding address, size,
  buffer-id reset and downstream uniform binding sequence.
- Do not change the shader descriptor cache, buffer/texture invalidation,
  GPU work submission, or the immutable shipping backport.
- Both R437 native-source reconstruction oracles reproduce this extension.

## Source-selected regression

`tools/check-native-unmapped-uniform-buffer-host.py` compiles the actual
maintained `BindGraphicsUniformBuffer` and `DisableGraphicsUniformBuffer`
method bodies with ASan/UBSan under `-O0` and `-O2`. It verifies valid
mapping, a formerly mapped slot becoming unmapped, and subsequent remapping,
including complete retirement of stale address/size/buffer-id.

The same fast gate also verifies the zero-tick fence optimization:
`tools/check-native-zero-write-tick-fence-host.py` runs the actual
`SynchronizeBufferWrites` method under UBSan, confirming an unwritten
tick avoids the scheduler's semaphore query while all nonzero-fence
synchronization remains unchanged. Both host tests passed in the fast gate.

## Qualification boundary

A native source dereference bug is fixed; there is no recorded evidence
yet that FC27 caused this optional to be empty during its HUD/jersey
rendering. The earlier PS5 game still had observable stutter despite
stable presentation FPS. No new FC27 frame-time or graphics correctness
measurements are available. Full preflight, CodeQL C++ and the exact native
PS5 build are separately checked before asking for any console retest.
