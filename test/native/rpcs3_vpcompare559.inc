// CELL559 vertex program comparison. The real RSXVertexProgram/v128 headers
// are used; vertex_program_compare::operator() and compare_properties are copied
// verbatim from the 555 preimage (before) and the 559 source (after). The x86
// AVX-512 branch is compiled out, as on the ARM64 Core.
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>
#include "util/types.hpp"
#include "util/v128.hpp"
#include "Emu/RSX/Program/RSXVertexProgram.h"
#undef ARCH_X64

namespace utils { u64 _get_main_tid() { return 0; } }
namespace rsx
{
@TEXTURE_STATE_EQUALITY@
}
#define CELL559_REQUIRE(x) do { if (!(x)) { std::fprintf(stderr, "requirement failed: %s\n", #x); std::abort(); } } while (0)

namespace before
{
struct vertex_program_compare
{
	bool operator()(const RSXVertexProgram& binary1, const RSXVertexProgram& binary2) const;
	static bool compare_properties(const RSXVertexProgram& binary1, const RSXVertexProgram& binary2);
};
@BEFORE_COMPARE@
@BEFORE_PROPERTIES@
}

namespace after
{
struct vertex_program_compare
{
	bool operator()(const RSXVertexProgram& binary1, const RSXVertexProgram& binary2) const;
	static bool compare_properties(const RSXVertexProgram& binary1, const RSXVertexProgram& binary2);
};
@AFTER_COMPARE@
@AFTER_PROPERTIES@
}

static RSXVertexProgram random_program(std::mt19937_64& rng, usz instructions, double density)
{
	RSXVertexProgram p;
	p.data.resize(instructions * 4);
	for (auto& word : p.data) word = static_cast<u32>(rng());
	std::bernoulli_distribution used(density);
	for (usz i = 0; i < instructions; ++i)
		if (used(rng)) p.instruction_mask.set(static_cast<u32>(i));
	p.ctrl = static_cast<u32>(rng() & 0xff);
	p.output_mask = static_cast<u32>(rng());
	if (rng() & 1) p.jump_table.insert(static_cast<u32>(rng() % 512));
	return p;
}

int main(int argc, char** argv)
{
	const bool benchmark = argc > 1 && std::strcmp(argv[1], "--benchmark") == 0;
	std::mt19937_64 rng(559);
	const before::vertex_program_compare old_compare;
	const after::vertex_program_compare new_compare;

	// Differential equivalence over the cases a cache lookup can meet.
	usz cases = 0, equal = 0;
	usz kinds[7]{};
	for (int round = 0; round < 40000; ++round)
	{
		const usz n = 1 + rng() % 512;
		const RSXVertexProgram a = random_program(rng, n, (rng() % 100) / 100.0);
		RSXVertexProgram b = a;
		const int kind = static_cast<int>(rng() % 7);
		switch (kind)
		{
		case 0: break; // exact repeat
		case 1: // differ in an instruction outside the mask (ignored by the cache)
		case 2: // differ in a masked instruction
		{
			std::vector<usz> pool;
			for (usz i = 0; i < n; ++i)
				if (static_cast<bool>(a.instruction_mask[static_cast<u32>(i)]) == (kind == 2)) pool.push_back(i);
			if (pool.empty()) break;
			const usz inst = pool[rng() % pool.size()];
			b.data[inst * 4 + rng() % 4] ^= 1u << (rng() % 32);
			break;
		}
		case 3: b.ctrl ^= 1; break;
		case 4: b.jump_table.insert(600); break;
		case 5: b.data.push_back(0); b.data.push_back(0); b.data.push_back(0); b.data.push_back(0); break;
		case 6: b.output_mask ^= 0x10; break;
		}
		const bool expected = old_compare(a, b);
		CELL559_REQUIRE(new_compare(a, b) == expected);
		CELL559_REQUIRE(new_compare(b, a) == old_compare(b, a));
		++cases;
		equal += expected;
		++kinds[kind];
	}
	// Empty programs and a single partial instruction stay equivalent.
	{
		RSXVertexProgram a, b;
		CELL559_REQUIRE(new_compare(a, b) == old_compare(a, b));
		a.data = {1, 2, 3};
		b.data = {1, 2, 4};
		CELL559_REQUIRE(new_compare(a, b) == old_compare(a, b));
	}

	std::printf("{\"passed\":true,\"differentialCases\":%zu,\"equalResults\":%zu,\"exactRepeat\":%zu,"
		"\"unmaskedDifference\":%zu,\"maskedDifference\":%zu,\"propertyDifference\":%zu,\"jumpTableDifference\":%zu,"
		"\"sizeDifference\":%zu,\"outputMaskDifference\":%zu",
		cases, equal, kinds[0], kinds[1], kinds[2], kinds[3], kinds[4], kinds[5], kinds[6]);

	if (benchmark)
	{
		// Successful lookups compare a key with its exact repeat. Interleave the
		// two implementations per round; report medians in nanoseconds per compare.
		std::printf(",\"benchmark\":[");
		const usz sizes[] = {64, 128, 256, 512};
		for (usz s = 0; s < 4; ++s)
		{
			const RSXVertexProgram a = random_program(rng, sizes[s], 0.9);
			const RSXVertexProgram b = a;
			constexpr int rounds = 41, iterations = 20000;
			std::vector<double> before_ns, after_ns;
			volatile usz sink = 0;
			for (int r = 0; r < rounds; ++r)
			{
				for (int which = 0; which < 2; ++which)
				{
					const bool first_old = (r & 1) == 0;
					const bool use_old = (which == 0) == first_old;
					const auto t0 = std::chrono::steady_clock::now();
					for (int i = 0; i < iterations; ++i)
						sink += use_old ? old_compare(a, b) : new_compare(a, b);
					const auto t1 = std::chrono::steady_clock::now();
					const double ns = std::chrono::duration<double, std::nano>(t1 - t0).count() / iterations;
					(use_old ? before_ns : after_ns).push_back(ns);
				}
			}
			CELL559_REQUIRE(sink == static_cast<usz>(rounds) * 2 * iterations);
			std::sort(before_ns.begin(), before_ns.end());
			std::sort(after_ns.begin(), after_ns.end());
			std::printf("%s{\"instructions\":%zu,\"beforeMedianNs\":%.2f,\"afterMedianNs\":%.2f}",
				s ? "," : "", sizes[s], before_ns[rounds / 2], after_ns[rounds / 2]);
		}
		std::printf("]");
	}
	std::printf("}\n");
	return 0;
}
