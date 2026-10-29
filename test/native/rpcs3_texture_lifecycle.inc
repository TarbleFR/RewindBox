// This fragment extends the retained production-storage adapters. GPU images,
// guest mappings and cache validation remain explicit host boundaries.
static_assert(sizeof(before::Section) == sizeof(after::Section));
static_assert(sizeof(before::Cache::Storage) == sizeof(after::Cache::Storage));
inline u64 lifecycle_index_checks = 0;
inline u64 lifecycle_retags = 0;
inline u64 lifecycle_negative_memberships = 0;
inline u64 lifecycle_clear_reuses = 0;

void audit_candidate(after::Cache& cache)
{
    using Block = after::Cache::Storage::block_type;
    for (auto& block : cache.m_storage)
    {
        std::vector<Block::address_entry> expected;
        u32 order = 0;
        for (auto& section : block)
        {
            if (section.valid_range())
            {
                if (block.size() > Block::address_index_threshold)
                    expected.push_back({section.get_section_base(), order, &section});
                for (auto* next = block.next_block(); next && section.get_section_range().end >= next->get_start(); next = next->next_block())
                    assert(next->unowned.contains(&section));
            }
            ++order;
        }
        std::sort(expected.begin(), expected.end(), Block::address_less);
        assert(expected.size() == block.m_address_index.size());
        for (usz i = 0; i < expected.size(); ++i)
        {
            const auto& actual = block.m_address_index[i];
            assert(actual.address == expected[i].address);
            assert(actual.order == expected[i].order);
            assert(actual.section == expected[i].section);
        }
        for (const auto* section : block.unowned)
        {
            assert(section->valid_range());
            assert(section->m_block != &block);
            assert(section->get_section_range().overlaps(block.range));
        }
    }
    ++lifecycle_index_checks;
}

void lifecycle_cases()
{
    for (u32 count : {8u, 16u, 17u, 64u})
    {
        auto old = std::make_unique<before::Cache>();
        auto now = std::make_unique<after::Cache>();
        std::vector<before::Section*> a;
        std::vector<after::Section*> b;
        for (u32 i = 0; i < count; ++i)
        {
            a.push_back(&add(*old, 0xff000 + i * 8, 0x110000, i + 1, false));
            b.push_back(&add(*now, 0xff000 + i * 8, 0x110000, i + 1, false));
        }
        audit_candidate(*now);
        for (u32 i = 0; i < count; ++i)
        {
            reset(*a[i], 0x8000 + i * 8, 128, false);
            reset(*b[i], 0x8000 + i * 8, 128, false);
            for (u32 address : {0x100000u, 0x200000u})
            {
                // The baseline retains the same slot in a non-overlapping block.
                assert(old->m_storage.block_for(address).unowned.contains(a[i]));
                assert(!now->m_storage.block_for(address).unowned.contains(b[i]));
                ++lifecycle_negative_memberships;
            }
            ++lifecycle_retags;
            audit_candidate(*now);
        }
        for (u32 i = 0; i < 500; ++i)
        {
            auto* slot = b[(i * 13) % count];
            reset(*slot, 0xff000, 0x110000, (i % 3) == 0);
            audit_candidate(*now);
            reset(*slot, 0x8000 + (i % 16) * 16, 128, false);
            audit_candidate(*now);
            lifecycle_retags += 2;
        }
        old->m_storage.clear();
        now->m_storage.clear();
        audit_candidate(*now);
    }

    // clear() retains list allocations. Check stale memberships and then reuse
    // the same slot; this is a membership failure, not a freed-memory claim.
    for (u32 count : {1u, 17u, 64u})
    {
        auto old = std::make_unique<before::Cache>();
        auto now = std::make_unique<after::Cache>();
        auto* old_first = &add(*old, 0xff000, 0x5000, 1, false);
        auto* new_first = &add(*now, 0xff000, 0x5000, 1, false);
        for (u32 i = 1; i < count; ++i)
        {
            add(*old, 0xff000 + i * 8, 0x5000, i + 1, false);
            add(*now, 0xff000 + i * 8, 0x5000, i + 1, false);
        }
        old->m_storage.block_for(0xff000).clear();
        now->m_storage.block_for(0xff000).clear();
        assert(old->m_storage.block_for(0x100000).unowned.size() == count);
        assert(now->m_storage.block_for(0x100000).unowned.empty());
        ++lifecycle_negative_memberships;
        audit_candidate(*now);
        auto* old_reused = &add(*old, 0x8000, 128, 101, false);
        auto* new_reused = &add(*now, 0x8000, 128, 101, false);
        assert(old_reused == old_first && new_reused == new_first);
        assert(old->m_storage.block_for(0x100000).unowned.contains(old_reused));
        assert(!now->m_storage.block_for(0x100000).unowned.contains(new_reused));
        assert(!old_reused->get_section_range().overlaps(old->m_storage.block_for(0x100000).range));
        ++lifecycle_negative_memberships;
        ++lifecycle_clear_reuses;
        audit_candidate(*now);
    }
}
