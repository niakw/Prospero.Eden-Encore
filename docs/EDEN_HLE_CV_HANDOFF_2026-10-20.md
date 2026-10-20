# CV waiter-flag failure must precede mutex-owner handoff

## Hypothesis

The checked key-write failure added in `b8793d2` prevents a lost wait but runs
after `RemoveUserWaiterByKey` and `next_owner_thread->EndWait`. A failed flag
write then returns before the mutex value is updated. The next owner is already
detached and runnable while guest memory still names the old owner.

Extend the existing full-`Wait` lost-mapping fixture to require no ownership
handoff, no next-owner wake and no mutex write when the flag cannot be published.
The current maintained source must fail this check before moving the checked
flag publication ahead of the handoff, under the same scheduler lock. Keep the
release fence between successful flag publication and the remaining operations.

Normal waits must still hand off the mutex, publish the flag, enter the tree and
begin waiting. Invalid initial keys and failed flag publication must cancel
sleep without those ownership side effects. This is a host state-transition
proof, not guest instruction progress or an FC27 freeze diagnosis.

## Local result

The stronger full-Wait witness failed on the prior maintained source because
the next owner had already been detached/woken. Moving checked publication
before that transfer passes both the failed-write case (no handoff/wake/tree
insertion/sleep) and the normal case (handoff, wake, flag, mutex value and wait).
Initial invalid keys still fail before all these operations. The independent
helper parity oracle, full-Wait parity oracle, isolated key-write sanitizer
fixture, four-mode CMake selection and HLE overlay checks pass locally.
Remote CI and native console execution are not established by these results.
