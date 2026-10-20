# Bootstrap context permit ownership

## Reproduced invariant

`CpuManager::RunThread` initially yields directly into the scheduler's main
thread context. That path reaches `KScheduler::Activate` before the normal
`ScheduleImplFiber` acquisition loop. The initial context semaphore contains
one free permit, while `Unload` later releases a permit for every nonterminated
current thread. The previous `KScheduler::Initialize` did not claim it.

This gives the first active bootstrap context no claimed permit, followed by
a release of an unclaimed permit. A binary-semaphore implementation whose
maximum is one has no spare capacity for that release; implementations with
a larger maximum can accumulate extra permits. The previous two-worker fixture
always acquired before releasing, so it did not exercise this initial boundary.

Compile the actual `Initialize` and `Unload` methods with real C++ semaphores:
the active bootstrap permit must be unavailable, the idle permit must remain
available for its first scheduler acquisition, and unload must restore exactly
one permit. Exercise termination separately. The old-source negative control fails this invariant. The maintained initialization
now claims the bootstrap permit with `try_acquire` and rejects an already-held
permit before publishing the current thread. It leaves the idle permit free.
The source-extracted fixture passes all 64 lifecycle iterations under ASan/UBSan.

The real PS5 compile database selects this maintained scheduler; native Clang
accepts the changed unit with its actual target flags. The exact source hash in
`check-upstream-guest-scheduler-locks.py` was requalified after verifying that
removing only this initialization block reproduces the previous reviewed unit.
The slab/header hashes and normal acquire/retry/release logic are unchanged.

This proves a context-permit lifecycle property on host. It does not prove
guest instruction progression or attribute a console freeze to this boundary.
