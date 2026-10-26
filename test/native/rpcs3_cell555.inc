// The Python driver inserts exact production methods and the authenticated
// pre-555 trim method. Storage/ranges and the timer are host test adapters;
// no guest writes, Vulkan work or iPhone execution is simulated here.
#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <thread>
#include <utility>
#include <vector>
#include "rpcs3/ios/IOSTextureValidationProfile.h"

using u64 = std::uint64_t;

namespace utils
{
inline thread_local u64 ticks = 0;
inline thread_local u64 timer_calls = 0;
inline u64 get_tsc()
{
    ++timer_calls;
    return ++ticks;
}
}

struct address_range32
{
    std::uint32_t bytes = 0;
    bool present = false;
    bool valid() const { return present; }
    std::uint32_t length() const { assert(present); return bytes; }
};

struct Section
{
    bool locked = true;
    bool page_protection = false;
    bool guest_changed = false;
    address_range32 cpu_range{4096, true};
    address_range32 confirmed_range{};
    unsigned synchronizations = 0;

    bool is_locked(bool actual = false) const
    {
        return locked && (!actual || page_protection);
    }

    @CONFIRMED_RANGE@

    void sync_protection()
    {
        ++synchronizations;
        utils::ticks += 7;
        if (guest_changed) locked = false;
    }
};

struct Block
{
    std::vector<Section> sections;
    unsigned get_locked_count() const
    {
        unsigned count = 0;
        for (const auto& section : sections) count += section.locked;
        return count;
    }
    auto begin() { return sections.begin(); }
    auto end() { return sections.end(); }
};

struct Storage
{
    std::vector<Block> blocks;
    std::vector<Block*> m_in_use;
    explicit Storage(std::vector<Block> input) : blocks(std::move(input))
    {
        for (auto& block : blocks) m_in_use.push_back(&block);
    }
    Storage(const Storage&) = delete;
    Storage& operator=(const Storage&) = delete;
};

namespace before
{
struct Container : Storage
{
    using Storage::Storage;
    @BEFORE_TRIM@
};
}

namespace after
{
struct Container : Storage
{
    using Storage::Storage;
    @AFTER_TRIM@
};
}

static void reset_observations()
{
    using namespace rpcs3::ios::texture_validation;
    trim_calls.store(0);
    trim_sections.store(0);
    trim_bytes.store(0);
    trim_ticks.store(0);
    utils::ticks = utils::timer_calls = 0;
}

static void observations(u64 calls, u64 sections, u64 bytes, u64 ticks)
{
    using namespace rpcs3::ios::texture_validation;
    assert(trim_calls.load() == calls);
    assert(trim_sections.load() == sections);
    assert(trim_bytes.load() == bytes);
    assert(trim_ticks.load() == ticks);
}

static void equal_sections(const Storage& control, const Storage& tested)
{
    assert(control.blocks.size() == tested.blocks.size());
    for (std::size_t b = 0; b < control.blocks.size(); ++b)
    {
        const auto& left = control.blocks[b].sections;
        const auto& right = tested.blocks[b].sections;
        assert(left.size() == right.size());
        for (std::size_t i = 0; i < left.size(); ++i)
        {
            assert(left[i].locked == right[i].locked);
            assert(left[i].synchronizations == right[i].synchronizations);
            assert(left[i].page_protection == right[i].page_protection);
        }
    }
}

static Block mixed_block(unsigned locked_count)
{
    assert(locked_count >= 2);
    Block block;
    Section pages;
    pages.page_protection = true;
    block.sections.assign(locked_count - 2, pages);
    Section partial;
    partial.cpu_range = {1024, true};
    partial.confirmed_range = {31, true};
    block.sections.push_back(partial);
    Section fallback;
    fallback.cpu_range = {2048, true};
    block.sections.push_back(fallback);
    Section unlocked;
    unlocked.locked = false;
    block.sections.push_back(unlocked);
    return block;
}

int main()
{
    using namespace rpcs3::ios::texture_validation;
    static_assert(sizeof(trim_calls) + sizeof(trim_sections) +
        sizeof(trim_bytes) + sizeof(trim_ticks) == 32);
    // Empty passes still report their fixed timer pair and no section bytes.
    reset_observations();
    before::Container old_empty(std::vector<Block>{});
    after::Container new_empty(std::vector<Block>{});
    old_empty.trim_sections();
    assert(utils::timer_calls == 0);
    new_empty.trim_sections();
    observations(1, 0, 0, 1);
    assert(utils::timer_calls == 2);
    equal_sections(old_empty, new_empty);
    after::Container empty_block({Block{}});
    empty_block.trim_sections();
    observations(2, 0, 0, 2);
    assert(utils::timer_calls == 4);

    // The byte sum must remain 64-bit even when a pass validates many large
    // ranges. These are range descriptors; the test allocates no texture RAM.
    reset_observations();
    auto large = mixed_block(257);
    for (auto& section : large.sections)
    {
        section.page_protection = false;
        section.confirmed_range = {};
        section.cpu_range = {16 * 1024 * 1024, true};
    }
    before::Container old_large({large});
    after::Container new_large({large});
    old_large.trim_sections();
    new_large.trim_sections();
    observations(1, 257, u64{257} * 16 * 1024 * 1024, 1 + 257 * 7);
    equal_sections(old_large, new_large);
    assert(utils::timer_calls == 2);

    // The threshold remains strictly greater than 256. Confirmed subranges
    // count their length, absent confirmations use the complete CPU range;
    // page-protected and unlocked sections never count as hash validation.
    for (unsigned locked_count : {255, 256, 257, 300})
    {
        reset_observations();
        before::Container old({mixed_block(locked_count)});
        after::Container current({mixed_block(locked_count)});
        const u64 validations = locked_count > 256 ? 2 : 0;
        for (unsigned pass = 1; pass <= 3; ++pass)
        {
            old.trim_sections();
            current.trim_sections();
            equal_sections(old, current);
            observations(pass, pass * validations, pass * (validations ? 2079 : 0),
                pass * (1 + 7 * validations));
            assert(utils::timer_calls == 2 * pass);
        }
    }

    // A changed section becomes unlocked identically to the control. This
    // can bring the block below the threshold for the very next pass.
    reset_observations();
    auto dirty = mixed_block(257);
    dirty.sections[255].guest_changed = true;
    before::Container old_dirty({dirty});
    after::Container new_dirty({dirty});
    old_dirty.trim_sections();
    new_dirty.trim_sections();
    observations(1, 2, 2079, 15);
    equal_sections(old_dirty, new_dirty);
    assert(new_dirty.blocks[0].get_locked_count() == 256);
    old_dirty.trim_sections();
    new_dirty.trim_sections();
    observations(2, 2, 2079, 16);
    equal_sections(old_dirty, new_dirty);
    assert(utils::timer_calls == 4);

    // Independent cache owners may report into the shared fixed-size atomic
    // counters concurrently. The adapter never shares mutable cache objects.
    reset_observations();
    constexpr unsigned threads = 8, passes = 100;
    std::vector<std::thread> workers;
    for (unsigned t = 0; t < threads; ++t)
        workers.emplace_back([] {
            before::Container old({mixed_block(300), mixed_block(256)});
            after::Container current({mixed_block(300), mixed_block(256)});
            for (unsigned i = 0; i < passes; ++i)
            {
                old.trim_sections();
                current.trim_sections();
            }
            equal_sections(old, current);
            assert(utils::timer_calls == 2 * passes);
        });
    for (auto& worker : workers) worker.join();
    observations(threads * passes, threads * passes * 2,
        threads * passes * 2079, threads * passes * 15);

    std::cout << "{\"passed\":true,\"thresholdCases\":4,\"emptyCases\":2,"
        "\"dirtyThenBelowThreshold\":true,\"byteTotalsBeyond32Bits\":true,"
        "\"confirmedRangeBytesPerPass\":2079,"
        "\"timerCallsPerPass\":2,\"concurrentPasses\":800,"
        "\"concurrentValidatedSections\":1600,\"concurrentValidatedBytes\":1663200,"
        "\"validationBehaviorMatchesControl\":true,\"physicalDeviceTested\":false}\n";
}
