    if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {
        // Keep independent copies in one submission, then publish guest writes
        // in modification order. A staging allocation stays busy until its tick.
        using Map = decltype(runtime.DownloadStagingBuffer(size_t{}));
        // Most GPU readback calls fit entirely inside sixteen staging maps.
        // Avoid heap allocation and allocator contention on every guest read.
        // Pinned Vulkan StagingBufferRef is a non-owning value handle; the
        // staging pool owns its backing memory and deferred lifetime.
        boost::container::small_vector<std::pair<ImageId, Map>, 16> pending;
        constexpr size_t batch_limit = 32_MiB;
        size_t batch_bytes = 0;
        const auto finish_batch = [&] {
            if (pending.empty()) return;
            runtime.Finish();
            for (auto& [image_id, map] : pending) {
                Image& image = slot_images[image_id];
                const auto copies = FixSmallVectorADL(FullDownloadCopies(image.info));
                SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies, map.mapped_span,
                             swizzle_data_buffer);
            }
            pending.clear();
            batch_bytes = 0;
        };
        for (const ImageId image_id : images) {
            Image& image = slot_images[image_id];
            const size_t bytes = image.unswizzled_size_bytes;
            if (pending.size() == 16 || bytes > batch_limit - batch_bytes)
                finish_batch();
            auto map = runtime.DownloadStagingBuffer(bytes);
            const auto copies = FixSmallVectorADL(FullDownloadCopies(image.info));
            image.DownloadMemory(map, copies);
            pending.emplace_back(image_id, std::move(map));
            // Oversized images retain the original one-image allocation/wait.
            if (bytes >= batch_limit) {
                finish_batch();
            } else {
                batch_bytes += bytes;
            }
        }
        finish_batch();
        return;
    }
