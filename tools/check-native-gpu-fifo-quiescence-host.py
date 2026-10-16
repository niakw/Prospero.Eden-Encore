#!/usr/bin/env python3
"""Fail-closed host witness: FIFO GPU tick behind a quiescence-blocked submit.

Shows a bounded no-progress wait cycle in the real GPU worker call graph.
The positive control models *conditionally eligible* control-plane work;
it does NOT authorize native command reordering or deferred bridge #187.
"""
from collections import deque
from pathlib import Path

root = Path(__file__).resolve().parents[1]
read = lambda p: (root / p).read_text()
worker = read("vendor/sources/eden/src/video_core/gpu_thread.cpp")
header = read("vendor/sources/eden/src/video_core/gpu_thread.h")
gpu = read("vendor/sources/eden/src/video_core/gpu.cpp")
physical = read("vendor/sources/eden/src/core/hle/kernel/physical_core.cpp")
replay = read("headless/gpu_deferred_replay.h")
workflow = read(".github/workflows/encore-core-preflight.yml")

# Source anchors: the real GPU worker cannot dispatch a later tick while
# execution of the current queue item is synchronously blocked.
assert "state.queue.PopWait(next, stop_token);" in worker
start = worker.index("if (auto* submit_list = std::get_if<SubmitListCommand>(&next.data))")
tick = worker.index("std::holds_alternative<GPUTickCommand>(next.data)")
end = worker.index("state.signaled_fence.store(next.fence);")
assert start < tick < end
assert "system.GPU().TickWork();" in worker[tick:end]
assert "PushCommand(GPUTickCommand(), false, is_async);" in worker
assert "using CommandQueue = Common::SPSCQueue<CommandDataContainer>;" in header
assert "const u64 fence = RequestSyncOperation(" in gpu
assert "gpu_thread.TickGPU(is_async);" in gpu
assert "WaitForSyncOperation(fence);" in gpu
assert "arm_interface->SignalInterrupt(thread);" in physical
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert "python3 -B tools/check-native-gpu-fifo-quiescence-host.py" in workflow


class Replay:
    def __init__(self):
        self.commands = deque(["dependent_submit", "sync_tick", "following_submit"])
        self.gpu_read_completed = False
        self.jit_exited = False
        self.executed = []
        self.pending = True
        self.failed = False

    def blocked_submit(self):
        # Quiescence request is pending until the JIT exits; that JIT
        # cannot exit until its pending GPU read synchronization completes.
        return not self.jit_exited

    def strict_fifo_step(self):
        if not self.commands:
            return False
        cmd = self.commands[0]
        if cmd == "dependent_submit" and self.blocked_submit():
            return False  # head-of-line: no later tick can run
        self.commands.popleft()
        self.executed.append(cmd)
        if cmd == "sync_tick":
            self.gpu_read_completed = True
            self.jit_exited = True
        return True

    def hypothetical_safe_control_pump(self, validated_independent):
        if not self.commands or self.commands[0] != "dependent_submit":
            return False
        if not validated_independent:
            self.failed = True
            return False  # never execute an unproven out-of-order flush
        if list(self.commands)[1] != "sync_tick":
            self.failed = True
            return False
        # NOT a native operation: models a separately proven safe control
        # path while leaving ordered graphics submits pending in the FIFO.
        self.commands.remove("sync_tick")
        self.executed.append("sync_tick")
        self.gpu_read_completed = True
        self.jit_exited = True
        return True


# Negative control: a blocking wait in SubmitListCommand prevents GPUTick
# from reaching GPU::TickWork. A bounded test avoids actually deadlocking CI.
blocked = Replay()
for _ in range(5):
    assert not blocked.strict_fifo_step()
assert not blocked.executed and not blocked.gpu_read_completed
assert not blocked.jit_exited and list(blocked.commands) == [
    "dependent_submit", "sync_tick", "following_submit"
]
print("GPU_FIFO_HOL_BLOCKED_TICK_NEGATIVE_REPRODUCED")

# Positive architectural condition, NOT native behavior: allow the requested
# CPU-read tick only after its independence from the blocked submit is proven.
possible = Replay()
assert possible.hypothetical_safe_control_pump(validated_independent=True)
assert possible.executed == ["sync_tick"]
assert list(possible.commands) == ["dependent_submit", "following_submit"]
assert possible.strict_fifo_step()
assert possible.strict_fifo_step()
assert possible.executed == ["sync_tick", "dependent_submit", "following_submit"]
assert possible.jit_exited and possible.gpu_read_completed
print("GPU_FIFO_QUALIFIED_CONTROL_PLANE_MODEL_PASS")

# Without proof of safe control bypass, fail closed rather than execute
# later commands or release graphics ordering incorrectly.
unsafe = Replay()
assert not unsafe.hypothetical_safe_control_pump(validated_independent=False)
assert unsafe.failed and not unsafe.executed and not unsafe.jit_exited
assert not unsafe.gpu_read_completed
assert list(unsafe.commands) == [
    "dependent_submit", "sync_tick", "following_submit"
]
print("GPU_FIFO_UNPROVEN_REORDER_FAIL_CLOSED")
print("GPU_FIFO_NATIVE_BRIDGE_NOT_QUALIFIED")
