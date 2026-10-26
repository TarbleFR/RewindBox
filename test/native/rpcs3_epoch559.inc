// CELL559 texture validation epoch. buffered_section::is_locked, protect,
// sync and discard are copied verbatim from texture_cache.cpp (555 preimage in
// namespace before, 559 source in namespace after); FIFO_control::read_put is
// the 559 body. The real protection policy and IOSTextureValidationProfile.h
// are used. Memory, page protection and the guest control register are adapters.
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include "Emu/RSX/Common/texture_cache_protection_policy.h"
#include "ios/IOSTextureValidationProfile.h"

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
inline constexpr u32 umax = 0xffffffffu;
#define ensure(x) do { if (!(x)) { std::fprintf(stderr, "ensure failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)
#define AUDIT(x) do { } while (0)
#define CELL559_REQUIRE(x) ensure(x)

namespace utils { enum class protection { rw, ro, no }; }
namespace tv = rpcs3::ios::texture_validation;

namespace rsx
{
	struct address_range32
	{
		u32 start = 1, end = 0;
		u32 length() const { return end - start + 1; }
		bool valid() const { return start <= end; }
		void invalidate() { start = 1; end = 0; }
		bool is_page_range() const { return valid() && (start & 4095) == 0 && ((end + 1) & 4095) == 0; }
		bool inside(const address_range32& other) const { return start >= other.start && end <= other.end; }
	};
	inline int page_protect_calls = 0;
	inline void memory_protect(const address_range32&, utils::protection) { ++page_protect_calls; }

#define CELL559_SECTION \
	struct buffered_section \
	{ \
		address_range32 locked_range{0x10000, 0x1ffff}, cpu_range{0x10000, 0x1ffff}, confirmed_range; \
		utils::protection protection = utils::protection::rw; \
		section_protection_strategy protection_strat = section_protection_strategy::hash; \
		u64 mem_hash = 0; \
		mutable u64 validated_epoch = 0; \
		bool locked = false; \
		const std::vector<u8>* memory = nullptr; \
		mutable int hashes = 0; \
		mutable bool advance_during_hash = false; \
		u64 fast_hash_internal() const \
		{ \
			++hashes; \
			if (advance_during_hash) { advance_during_hash = false; tv::advance_epoch(); } \
			u64 h = 1469598103934665603ull; \
			for (u8 b : *memory) { h ^= b; h *= 1099511628211ull; } \
			return h; \
		} \
		const address_range32& get_confirmed_range() const { return confirmed_range.valid() ? confirmed_range : cpu_range; } \
		bool is_locked(bool actual_page_flags = false) const; \
		void protect(utils::protection new_prot, bool force = false); \
		bool sync() const; \
		void discard(); \
	};

	namespace before
	{
		CELL559_SECTION
		@BEFORE_IS_LOCKED@
		@BEFORE_PROTECT@
		@BEFORE_SYNC@
		@BEFORE_DISCARD@
	}

	namespace after
	{
		CELL559_SECTION
		@AFTER_IS_LOCKED@
		@AFTER_PROTECT@
		@AFTER_SYNC@
		@AFTER_DISCARD@
	}
}

namespace fifo
{
	struct put_register
	{
		std::atomic<u32> value{0};
		operator u32() const { return value.load(); }
		u32 and_fetch(u32 mask) { return value.fetch_and(mask) & mask; }
	};
	struct control { put_register put; };
	class FIFO_control
	{
	public:
		control ctrl;
		control* m_ctrl = &ctrl;
		mutable u32 m_epoch_put = umax;
		template <bool Full = true>
		u32 read_put() const;
	};
	@AFTER_READ_PUT@
}

template <typename Section>
static Section locked_section(const std::vector<u8>& memory)
{
	Section s;
	s.memory = &memory;
	s.protect(utils::protection::ro);
	ensure(s.locked && s.hashes == 1);
	s.hashes = 0;
	return s;
}

int main()
{
	std::vector<u8> memory(64 * 1024);
	for (std::size_t i = 0; i < memory.size(); ++i) memory[i] = static_cast<u8>(i * 37 + 1);

	// 1. Disabled (the default outside God of War III): identical to 555, one hash per validation.
	tv::epoch_enabled = false;
	{
		auto b = locked_section<rsx::before::buffered_section>(memory);
		auto a = locked_section<rsx::after::buffered_section>(memory);
		for (int i = 0; i < 10; ++i) CELL559_REQUIRE(b.sync() == a.sync());
		CELL559_REQUIRE(b.hashes == 10 && a.hashes == 10);
		memory[100] ^= 1;
		CELL559_REQUIRE(!b.sync() && !a.sync());
		memory[100] ^= 1;
		tv::advance_epoch();
		CELL559_REQUIRE(tv::epoch_bumps.load() == 0);
	}

	// 2. Enabled: validations inside one epoch reuse the confirmed hash.
	tv::epoch_enabled = true;
	const u64 skips0 = tv::epoch_skips.load();
	u64 skipped_bytes = 0;
	{
		auto a = locked_section<rsx::after::buffered_section>(memory);
		for (int i = 0; i < 10; ++i) CELL559_REQUIRE(a.sync());
		CELL559_REQUIRE(a.hashes == 0);  // protect() confirmed it in this epoch
		skipped_bytes += 10ull * a.get_confirmed_range().length();
		// A synchronization point: the next validation hashes again and sees the change.
		memory[200] ^= 1;
		tv::advance_epoch();
		CELL559_REQUIRE(!a.sync() && a.hashes == 1);
		memory[200] ^= 1;
		// A failed validation is never remembered.
		CELL559_REQUIRE(a.validated_epoch == 0);
		CELL559_REQUIRE(a.sync() && a.hashes == 2);
		CELL559_REQUIRE(a.sync() && a.hashes == 2);
		skipped_bytes += a.get_confirmed_range().length();
	}
	// 3. The epoch is read before the bytes: an advance during the hash forces the next one.
	{
		auto a = locked_section<rsx::after::buffered_section>(memory);
		tv::advance_epoch();
		a.advance_during_hash = true;
		CELL559_REQUIRE(a.sync() && a.hashes == 1);
		CELL559_REQUIRE(a.sync() && a.hashes == 2);
		CELL559_REQUIRE(a.sync() && a.hashes == 2);
		skipped_bytes += a.get_confirmed_range().length();
	}
	// 4. Unlocking forgets the confirmation; page-locked sections never hash.
	{
		auto a = locked_section<rsx::after::buffered_section>(memory);
		a.discard();
		CELL559_REQUIRE(a.validated_epoch == 0 && !a.locked && a.sync() && a.hashes == 0);
		rsx::after::buffered_section l;
		l.memory = &memory;
		l.protect(utils::protection::no);  // GPU-owned: page lock, no hash
		CELL559_REQUIRE(l.protection_strat == rsx::section_protection_strategy::lock && l.hashes == 0 && l.sync());
	}
	CELL559_REQUIRE(tv::epoch_skips.load() - skips0 == 12);
	(void)skipped_bytes;

	// 5. Only a new PUT value opens an epoch.
	{
		fifo::FIFO_control f;
		f.ctrl.put.value = 0x100;
		const u64 e0 = tv::validation_epoch.load();
		for (int i = 0; i < 5; ++i) CELL559_REQUIRE(f.read_put() == 0x100);
		CELL559_REQUIRE(tv::validation_epoch.load() == e0 + 1);
		CELL559_REQUIRE(f.read_put<false>() == 0x100 && tv::validation_epoch.load() == e0 + 1);
		f.ctrl.put.value = 0x180;
		CELL559_REQUIRE(f.read_put<false>() == 0x180 && tv::validation_epoch.load() == e0 + 2);
		f.ctrl.put.value = 0x203;  // misaligned PUT is masked as before
		CELL559_REQUIRE(f.read_put() == 0x200 && tv::validation_epoch.load() == e0 + 3);
		tv::epoch_enabled = false;
		f.ctrl.put.value = 0x300;
		CELL559_REQUIRE(f.read_put() == 0x300 && tv::validation_epoch.load() == e0 + 3);
	}

	std::printf("{\"passed\":true,\"disabledIdenticalTo555\":true,\"hashesPerTenValidationsDisabled\":10,"
		"\"hashesPerTenValidationsInOneEpoch\":0,\"changeDetectedAfterSynchronizationPoint\":true,"
		"\"failedValidationNotRemembered\":true,\"epochReadBeforeHash\":true,\"pageLockedUnchanged\":true,"
		"\"putChangeOpensEpoch\":true,\"epochSkips\":12}\n");
	return 0;
}
