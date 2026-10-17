# Native GPU command queue: moved-from slot destructors

Scope: native-derived Common::SPSCQueue only. Pinned upstream files stay unchanged.

## Confirmed generic source defect

The queue owns std::array<T, Capacity> m_data: each slot is already a constructed
T, even while its queue position is empty. Pop move-assigns its contents to the
consumer but leaves the original slot alive in a moved-from state. The next
producer overwrites that object with std::construct_at but never calls the
old object's destructor. A valid move type that retains source ownership
therefore abandons resources.

The native-derived queue header now inserts std::destroy_at immediately before
the existing std::construct_at, at BOTH pinned enqueue sites: Emplace and
EmplaceWaitWithStopToken. CMake must find exactly two sites and otherwise
fails closed. The queue's FIFO, stop handling, and move construction remain
unchanged. No change to vendor, JIT, Vulkan or guest memory synchronization.

## Executable regression

tools/check-native-gpu-queue-slot-lifetime-host.py compiles the actual pinned
queue and the native-derived queue against a legal move-only type that
deliberately keeps shared ownership in its moved-from state. Reusing two
slots twelve times leaks ten owned resources in the unchanged queue;
the repaired queue fully releases all twelve.

The fixture proves this generic lifetime bug, not that a concrete title's
commands retain a resource or that it explains the freezes, HUD or slow
frames. No console build or title test was run. Bridge #187 stays disabled.
