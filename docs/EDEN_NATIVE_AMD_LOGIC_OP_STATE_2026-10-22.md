# Native AMD logic-op state — 22 October 2026

## Reviewed defect and hot path

The selected Vulkan `UpdateDynamicStates` mutated the guest Maxwell
`regs.logic_op.enable` to zero when any vertex attribute had a Float
type on AMD. The mutation persisted after the draw even if a later draw
used integer attributes and did not rewrite the logic-op register. This
could leave subsequent Vulkan host logic-op commands disabled.

It also checked every vertex attribute in every draw, including draws
whose guest logic op was disabled or whose inputs were unchanged.

## Correction

Preserve `regs.logic_op.enable` exactly. Project an effective bool to
Vulkan inside `UpdateLogicOpEnable` only when the state-tracker dirty bit
is touched and the feature is available. The existing AMD float-vertex
heuristic is retained, without extending the workaround's scope.

The Maxwell->Vulkan state tracker maps vertex attribute register writes
to `Dirty::VertexInput`. An AMD vertex-format change with enabled guest
logic op now marks `Dirty::LogicOpEnable` to force rebind. The host can
thus transition from disabled (float) back to enabled (nonfloat) without a
guest logic-op register write. The normal non-AMD path and disabled guest
logic op remain unchanged. No shader/barrier/texture ownership is
reordered.

Both the native renderer and the separately maintained, **disabled**
deferred bridge variant carry the same fix. The pinned generator oracle
reconstructs the two exact method replacements and the host regression
compiles the selected C++ `UpdateLogicOpEnable` and its real dirty
transition at -O0/-O2 under UBSan.

This is a correctness change with reduced work in the hot draw path,
not evidence of FC27 HUD repair or increased FPS. The older heuristic
checks vertex attributes, despite its historical comment describing
render targets; changing that heuristic requires a separate proof.
