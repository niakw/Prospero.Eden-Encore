# Eden Encore — inactive deferred bridge source outside the final engine queue

**Reviewed source** | Reason it is not optimized | Evidence
--- | --- | ---
| `vendor/encore-active/eden-core/guest-bridge/memory_ps5_standard.cpp` | Dev-only M12 memory alternate, not selected in the sole production configuration; retain in source control for audit rather than modifying its behavior | Git blob `380c26971f117f1fb8e0eb5d1f646f60886fcbe6`, `headless/guest_write_deferred_bridge.cmake`, `tools/check-deferred-native-bridge-contract.py` |

The selected production core translation unit comes from `EDEN_NATIVE_GUEST_SOURCE` in `headless/CMakeLists.txt`. The alternative `EDEN_DEFERRED_CPU_SOURCE` replaces that unit **only inside** `if(EDEN_GUEST_WRITE_BRIDGE_DEV)`, and requires the native developer profile. The final release forces `EDEN_GUEST_WRITE_BRIDGE_DEV=OFF` and treats ON as a configure-time error.

**Disposition: excluded from shipping optimization scope, not "FPS optimized".** This source is still inventoried among the 491 owned files. Its hash pins the review; any code change forces renewed review.

After classification: **420/491 sources accounted for; 9 actual engine/runtime sources left to review or optimize; 62 launcher UI sources separate.** One additional file classified but no C++ source changed here.
