# FC27: recover absent cached TIC/TSC mappings without dereferencing end()

The active Vulkan texture cache `VisitImageView` and `GetSamplerId`
call `DescriptorTable::Read`, which can return `is_new=false` when a
guest TIC/TSC descriptor has not changed. Both then dereferenced a
`channel_state` map lookup without checking whether it existed. An
unexpectedly absent cached mapping risks undefined iterator access.
Texture-binding consistency is particularly relevant to streamed HUD
and uniform/jersey image problems.

For PS5 native only, a missing image mapping now enters the existing
descriptor-validation and image-view creation path. If the guest image
is not resident, the missing mapping is materialized as NULL, preserving
the previous transient-null retry semantics. A missing sampler mapping
is similarly reconstructed using the existing `FindSampler` operation.
Valid cached views and samplers follow their existing fast paths. The
normal descriptor-table `is_new` branch is unchanged. A newly restored
image publishes `texture_bindings_serial` just as the previous NULL
recovery did, ensuring feedback-loop decisions can be recalculated.

A host test compiles the actual two native functions at O0 and O2 and
exercises valid cached mappings, missing valid/nonresident image
mappings, later recovery with the TIC unchanged, image-table updates,
tagged compute mappings, missing sampler mappings, and invalid indexes.

This is a defined behavior and safety correction; existing FC27 logs do
not prove an absent-map event occurred, and this is not yet confirmation
that the HUD or jersey bug is fixed. The production build uses the
maintained active `vulkan-cache` include tree.
