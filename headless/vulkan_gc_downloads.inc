    // Images the GPU wrote are copied back to guest memory before they go, behind a wait for the
    // GPU. Eden evicts them from its "expected" mark on; here they stay, as they do below that
    // mark, until memory is really short (performance.h, KeepDirtyTextures).
    const auto DirtyEvictions = [&] {
        return high_priority_mode &&
               (total_used_memory >= critical_memory || !::Eden::Performance::KeepDirtyTextures());
    };
    using DownloadMap = decltype(runtime.DownloadStagingBuffer(size_t{}));
    // Aggressive GC can process 40 images per pass. Keep those readbacks in
    // ONE scheduled batch instead of falling back to a Finish per image after
    // the former 16-descriptor cap. The separate 32-MiB BYTE cap is unchanged.
    constexpr size_t gc_prefetch_limit = 40;
    boost::container::small_vector<std::pair<ImageId, DownloadMap>, gc_prefetch_limit> gc_downloads;
    const auto ReleaseDownloads = [&] {
        if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {
            for (auto& [id, map] : gc_downloads)
                runtime.FreeDeferredStagingBuffer(map);
            gc_downloads.clear();
        }
    };
    SCOPE_EXIT { ReleaseDownloads(); };
    const auto PrefetchDownloads = [&] {
        if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {
            ReleaseDownloads();
            // No texture can be old enough before this title's first
            // age threshold. In particular, a zero cutoff would include
            // images first used at frame zero (LRU comparison is inclusive).
            if (frame_tick < ticks_to_destroy) return;
            size_t remaining = num_iterations;
            size_t bytes = 0;
            u64 usage = total_used_memory;
            // Only look ahead through independent dirty evictions. Leave all
            // deletion, alias updates and pressure-policy decisions to Cleanup.
            lru_cache.ForEachItemBelow(frame_tick - ticks_to_destroy, [&](ImageId id) {
                if (remaining == 0) return true;
                --remaining;
                auto& image = slot_images[id];
                if (True(image.flags & ImageFlagBits::IsDecoding)) return false;
                const bool dirty = IsDownloadable(image) && False(image.flags & ImageFlagBits::BadOverlap);
                if ((!aggressive_mode && True(image.flags & ImageFlagBits::CostlyLoad)) ||
                    (!DirtyEvictions() && dirty)) return false;
                if (!dirty || !image.aliased_images.empty() || !image.overlapping_images.empty() ||
                    image.HasScaled() || image.info.num_samples != 1 || gc_downloads.size() == gc_prefetch_limit ||
                    image.unswizzled_size_bytes > 32_MiB - bytes) return true;
                auto map = runtime.DownloadStagingBuffer(image.unswizzled_size_bytes, true);
                // The pinned StagingBufferRef is a POD handle, not a RAII
                // owner. The pool tracks deferred lifetime until FreeDeferred.
                gc_downloads.emplace_back(id, map);
                const auto copies = FixSmallVectorADL(FullDownloadCopies(image.info));
                image.DownloadMemory(map, copies);
                bytes += image.unswizzled_size_bytes;
                // The driver's sampled total and logical per-image
                // reclamation can diverge during alias/deferred cleanup.
                // Saturate instead of wrapping u64 and over-prefetching.
                usage = ::Eden::VulkanMemory::AfterProjectedEviction(
                    usage, ReclaimedBytes(image));
                // The original policy changes at these thresholds. Stop looking
                // ahead here so we never copy a texture that it would retain.
                return usage < (aggressive_mode || ::Eden::Performance::KeepDirtyTextures() ? critical_memory
                                                                                           : expected_memory);
            });
            if (!gc_downloads.empty()) runtime.Finish();
        }
    };
    const auto UsePrefetched = [&](ImageId id, Image& image) {
        if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {
            const auto it = std::ranges::find_if(gc_downloads, [id](const auto& entry) {
                return entry.first == id;
            });
            if (it != gc_downloads.end()) {
                const auto copies = FixSmallVectorADL(FullDownloadCopies(image.info));
                SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies,
                             it->second.mapped_span, swizzle_data_buffer);
                runtime.FreeDeferredStagingBuffer(it->second);
                gc_downloads.erase(it);
                return true;
            }
        }
        return false;
    };
