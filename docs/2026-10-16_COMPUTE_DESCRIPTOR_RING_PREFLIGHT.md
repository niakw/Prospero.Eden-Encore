# Compute descriptor ring waits outside the guest cache mutex pair

Date: 2026-10-16. Branch: `dev/ps5-sparse-jit`.

The native compute rasterizer previously entered `ComputePipeline::Configure`
under the texture and buffer cache mutexes before allocating descriptor-buffer
memory. Unlike graphics, compute always allocates a new descriptor-buffer payload
on every dispatch. An eight-frame reuse fence or exhausted last chunk may
therefore trigger `Wait` or `Finish` while both locks are held.

The compute pipeline's immutable descriptor-buffer capability and layout size
are now exposed via native-only getters in the pinned source-generator adapter.
Before acquiring either cache lock, `DispatchCompute` preflights the exact
ring frame-reuse fence and the guaranteed capacity overflow. After any GPU
worker/fence drain it flushes guest memory invalidations, reselects the compute
pipeline and checks large guest descriptor reservations again. The existing
`Allocate` waits remain the fallback for uncommon situations.

A source-extracted Clang ASan/UBSan fixture checks the production ring
`PreflightFrameReuse`, `PreflightCapacity` and `Allocate` methods together,
including no-wait, frame reuse, last-chunk exhaustion, disabled extension and
pipeline layout changes. It asserts no ring waits occur under simulated cache
locks once the preflight is applied. CI also tests source/generator parity.

No console build, release or hardware tests were performed. The graphics
descriptor-buffer conditional-reuse case remains unresolved. Host evidence
does not establish actual game performance, timing or resolution of freezes.
