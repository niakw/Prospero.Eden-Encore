# DMA command resume and side effects: actual-method host witness

Branch: dev/ps5-sparse-jit. Baseline: 06f004b. Native post-store bridge remains OFF.

## Exact source boundaries

- DmaPusher::DispatchCalls resets dma_pushbuffer_subindex to zero every
  time it is entered, calls Step() in a loop, then unconditionally calls
  GPU::FlushCommands() and GPU::OnCommandListEnd().
- DmaPusher::Step advances dma_pushbuffer_subindex only after the entire
  command header is processed, and pops the front CommandList when its
  final segment completes.
- DmaPusher::ProcessCommands uses a local command-word index. That index
  is not exposed as a resumable cursor, and method effects occur before
  the corresponding index/count update in some branches.
- The prefetch_command_list branch also processes its entire command
  span before popping its CommandList. A mid-span suspension lacks a
  native restart checkpoint.
- Step can wait in sync_cv for a rasterizer fence. A worker-deferred
  transition must preserve that fence's signaling dependencies.

## Host witness

tools/check-native-dma-resume-boundary-host.py extracts and compiles
the **unchanged pinned bodies** of DispatchCalls(), Step(),
ProcessCommands() and SetState() with narrow fake RAM, GPU and method
side effects. For both safe and unsafe guest command read variants:

1. An uninterrupted two-segment submission applies each command once,
   then flushes and signals command-list end once.
2. An artificially bounded DispatchCalls execution stops after its first
   fully completed Step; on re-entering DispatchCalls, the source resets
   the segment index, repeats the first effect, then executes the second.
   The command-list finalization also occurs twice.
3. Injecting an exception after the first method's observable effect
   exits Step before committing the segment index; calling Step again
   repeats that effect. This exception is an artificial pause witness,
   **not** a claim that native runtime currently throws at this point.
4. Calling Step twice without restarting DispatchCalls preserves the
   between-segment cursor in the fixture, but skips the DispatchCalls
   final FlushCommands / OnCommandListEnd behavior. It is not a complete
   replacement dispatcher.

These behaviors are demonstrated for the real method bodies but with
fake GPU and method effects, not real engine execution or Vulkan fences.

## Consequence

Do not add arbitrary pause points inside ProcessCommands, and do not
resume a pending pushbuffer by calling DispatchCalls again unchanged.
A safe resumable decoder would need an explicit durable checkpoint for
the current CommandList, header/segment, command-word position, method
count, non-incrementing mode, DMA offset, channel state, side-effect
commit status, and fence/end-of-list completion. It must establish
at-most-once externally visible effects even if a blocked operation is
canceled or the worker fails.

A safer alternative to research first is a true nonblocking deferral
*before* command decoding and side effects. But an early command list
envelope does not fully enumerate indirect memory dependencies and
command RAM can change before execution. A barrier before decode is
therefore not by itself a complete first-use GPU coherence solution.

No native execution change, no game fix, no console build/release and
no approval to enable bridge #187 follows from this test.
