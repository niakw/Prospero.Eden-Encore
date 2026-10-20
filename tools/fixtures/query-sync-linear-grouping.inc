// SPDX-License-Identifier: GPL-3.0-or-later
// Historical Encore query grouping before sorted-index coalescing.
    impl->redirect_cache.clear();
    impl->little_cache.clear();
    size_t total_size = 0;
    for (auto& sync_val : values) {
        if (sync_val.size == 0 ||
            sync_val.size > std::numeric_limits<DAddr>::max() - sync_val.address ||
            sync_val.size > std::numeric_limits<size_t>::max() - total_size) {
            throw std::overflow_error("Query sync value range overflow");
        }
        total_size += sync_val.size;
        bool found = false;
        const DAddr base = Common::AlignDown(sync_val.address, Core::DEVICE_PAGESIZE);
        // A query result may straddle a device-memory page. ObtainCPUBuffer
        // must cover the complete value, not only the page containing its start.
        const DAddr last_page = Common::AlignDown(
            sync_val.address + sync_val.size - 1, Core::DEVICE_PAGESIZE);
        if (last_page > std::numeric_limits<DAddr>::max() - Core::DEVICE_PAGESIZE) {
            throw std::overflow_error("Query sync page end overflow");
        }
        const DAddr base_end = last_page + Core::DEVICE_PAGESIZE;
        for (size_t i = 0; i < impl->little_cache.size(); i++) {
            const auto set_found = [&] {
                impl->redirect_cache.push_back(i);
                found = true;
            };
            auto& loc = impl->little_cache[i];
            if (base < loc.second && loc.first < base_end) {
                loc.first = (std::min)(loc.first, base);
                loc.second = (std::max)(loc.second, base_end);
                set_found();
                break;
            }
            if (loc.first == base_end) {
                loc.first = base;
                set_found();
                break;
            }
            if (loc.second == base) {
                loc.second = base_end;
                set_found();
                break;
            }
        }
        if (!found) {
            impl->redirect_cache.push_back(impl->little_cache.size());
            impl->little_cache.emplace_back(base, base_end);
        }
    }
