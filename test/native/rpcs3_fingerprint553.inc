class FingerprintTable final
{
public:
    static constexpr std::size_t capacity = 64;
    struct Entry { std::uint64_t fingerprint = 0, builds = 0, total_us = 0, max_us = 0; };
    struct Snapshot
    {
        std::uint64_t distinct = 0, repeated_builds = 0, dropped = 0;
        std::array<Entry, 3> costliest{}, repeated{};
        bool captured = false;
    };
    static std::uint64_t fingerprint(const PipelineContext& c) noexcept
    {
        auto mix = [](std::uint64_t seed, std::uint64_t value) noexcept
        {
            seed ^= value + 0x9e3779b97f4a7c15ull + (seed << 6) + (seed >> 2);
            return seed;
        };
        const auto result = mix(mix(mix(mix(mix(0x51ed270b27aeb4ffull, c.properties), c.renderpass), c.vertex_module), c.fragment_module), c.flags);
        return result ? result : 1;
    }
    void record(std::uint64_t key, std::uint64_t duration_us) noexcept
    {
        std::unique_lock lock(mutex_, std::try_to_lock);
        if (!lock)
        {
            dropped_.fetch_add(1, std::memory_order_relaxed);
            return;
        }
        for (std::size_t i = 0; i < capacity; ++i)
        {
            auto& entry = entries_[(key + i) % capacity];
            if (entry.fingerprint && entry.fingerprint != key) continue;
            entry.fingerprint = key;
            entry.builds++;
            entry.total_us += duration_us;
            entry.max_us = std::max(entry.max_us, duration_us);
            return;
        }
        dropped_.fetch_add(1, std::memory_order_relaxed);
    }
    Snapshot snapshot() noexcept
    {
        Snapshot result;
        std::unique_lock lock(mutex_, std::try_to_lock);
        if (!lock) return result;
        result.captured = true;
        result.dropped = dropped_.load(std::memory_order_relaxed);
        for (const auto& entry : entries_)
        {
            if (!entry.fingerprint) continue;
            result.distinct++;
            result.repeated_builds += entry.builds - 1;
            auto insert = [&entry](std::array<Entry, 3>& list, auto&& better)
            {
                for (auto& slot : list)
                {
                    if (!slot.fingerprint || better(entry, slot))
                    {
                        auto carry = entry;
                        for (auto* it = &slot; it != list.data() + list.size(); ++it) std::swap(*it, carry);
                        return;
                    }
                }
            };
            insert(result.costliest, [](const Entry& a, const Entry& b) { return a.max_us > b.max_us; });
            if (entry.builds > 1) insert(result.repeated, [](const Entry& a, const Entry& b) { return a.builds > b.builds; });
        }
        return result;
    }
    void reset() noexcept
    {
        std::lock_guard lock(mutex_);
        entries_ = {};
        dropped_.store(0, std::memory_order_relaxed);
    }
private:
    std::mutex mutex_;
    std::array<Entry, capacity> entries_{};
    std::atomic<std::uint64_t> dropped_{0};
};
