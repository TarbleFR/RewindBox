// Executes the Build 444 JIT phase profile on the host: exclusive nested
// timing, maxima, byte figures, headroom minimum and the exchange-with-zero
// contract that the JITPROF reporter relies on. Pure diagnostics evidence; it
// proves neither iPhone compile times nor frame rate. The Python runner checks
// the wiring of the counters, the PPU cache identity, the opt-in IR passes and
// the direct relay admission in the materialized Core.
#include "Utilities/JITPhaseProfile.h"

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>

namespace
{
std::uint64_t g_clock = 0;
std::uint64_t fake_now() noexcept { return g_clock; }
}

int main()
{
	using namespace jit_phase;
	// Build 444 defined twelve phases; Build 481 appends three SPU object cache phases.
	static_assert(count == 15);
	static_assert(sizeof(names) / sizeof(names[0]) == count);
	assert(std::strcmp(names[ppu_translate], "ppu_translate") == 0);
	assert(std::strcmp(names[spu_codegen], "spu_codegen") == 0);
	assert(std::strcmp(names[spu_cache_write], "spu_cache_write") == 0);

	// Fresh registry: everything zero, no headroom sample, min reported as zero.
	auto empty = g_counters.exchange();
	for (unsigned phase = 0; phase < count; ++phase)
		assert(!empty.events[phase] && !empty.ticks[phase] && !empty.max_ticks[phase] && !empty.bytes[phase]);
	assert(!empty.headroom_samples && !empty.headroom_min_bytes);

	// Direct accumulation: events, total, maximum and bytes.
	g_counters.add(ppu_translate, 10, 100);
	g_counters.add(ppu_translate, 30, 50);
	g_counters.add(ppu_translate, 20);
	g_counters.add(static_cast<phase>(count), 999, 999); // out of range: ignored
	auto taken = g_counters.exchange();
	assert(taken.events[ppu_translate] == 3 && taken.ticks[ppu_translate] == 60);
	assert(taken.max_ticks[ppu_translate] == 30 && taken.bytes[ppu_translate] == 150);
	for (unsigned phase = 0; phase < count; ++phase)
		if (phase != ppu_translate) assert(!taken.events[phase] && !taken.ticks[phase]);
	// Exchange resets.
	taken = g_counters.exchange();
	assert(!taken.events[ppu_translate] && !taken.ticks[ppu_translate] && !taken.max_ticks[ppu_translate]);

	// Nested scopes: the enclosing phase records only its exclusive time.
	{
		scope outer(ppu_object_load, fake_now);
		g_clock += 5;
		{
			scope inner(ppu_cache_read, fake_now);
			g_clock += 40;
			inner.bytes = 4096;
		}
		g_clock += 7;
		outer.bytes = 8192;
	}
	taken = g_counters.exchange();
	assert(taken.events[ppu_cache_read] == 1 && taken.ticks[ppu_cache_read] == 40 && taken.bytes[ppu_cache_read] == 4096);
	assert(taken.events[ppu_object_load] == 1 && taken.ticks[ppu_object_load] == 12 && taken.bytes[ppu_object_load] == 8192);
	assert(taken.max_ticks[ppu_object_load] == 12 && taken.max_ticks[ppu_cache_read] == 40);

	// Two nested scopes in sequence are both subtracted; a sibling after them is not.
	{
		scope outer(ppu_codegen, fake_now);
		{ scope first(ppu_cache_write, fake_now, 1); g_clock += 3; }
		{ scope second(ppu_cache_write, fake_now, 2); g_clock += 4; }
		g_clock += 10;
	}
	{ scope sibling(ppu_verify, fake_now); g_clock += 6; }
	taken = g_counters.exchange();
	assert(taken.events[ppu_cache_write] == 2 && taken.ticks[ppu_cache_write] == 7 && taken.bytes[ppu_cache_write] == 3);
	assert(taken.ticks[ppu_codegen] == 10 && taken.events[ppu_codegen] == 1);
	assert(taken.ticks[ppu_verify] == 6 && taken.events[ppu_verify] == 1);

	// Headroom: minimum over the window, sample count, reset on exchange.
	g_counters.note_headroom(900);
	g_counters.note_headroom(300);
	g_counters.note_headroom(600);
	taken = g_counters.exchange();
	assert(taken.headroom_samples == 3 && taken.headroom_min_bytes == 300);
	taken = g_counters.exchange();
	assert(!taken.headroom_samples && !taken.headroom_min_bytes);

	// Saturation safety: a clock that does not advance records zero, never wraps.
	{ scope frozen(spu_build, fake_now, 77); }
	taken = g_counters.exchange();
	assert(taken.events[spu_build] == 1 && !taken.ticks[spu_build] && taken.bytes[spu_build] == 77);

	std::puts("PASS Build 444 JIT phase profile: exclusive nested timing, maxima, bytes, headroom minimum, exchange reset");
	return 0;
}
