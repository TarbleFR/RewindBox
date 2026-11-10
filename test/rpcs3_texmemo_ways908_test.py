#!/usr/bin/env python3
"""REWINDBOX_TEXMEMO_WAYS_908: the texture lookup memo keeps 16 entries per sampler slot (was 4) and counts its
capacity misses.

Device input (IPA 694, 9 Nov, private logs): Assassin's Creed (BLES00158), gameplay window 40, COREPROF TEXMEMO660
lookups=99674 hits=29617 miss_empty=64461 miss_epoch=5126 lookup_ms=785: the misses are absent keys, not
invalidations. A slot sampling more than `ways` textures within an epoch evicts, by LRU, the entry it needs next.

Executed against the real rpcs3/ios/IOSTextureLookupMemo.h of the tree (and a copy with ways=4, the Core 907 value):
  1. one slot cycling N distinct textures in one epoch: with 16 ways every lookup after the first round is a hit for
     N <= 16 and none for N = 17 (LRU); with 4 ways none for N = 6; the capacity misses are counted (miss_evicted),
     a key never seen or evicted from an older epoch is not;
  2. every invalidation still drops the entries exactly as before: epoch, sampler revision, scoped range (only the
     overlapping entry), section generation, sampler refresh (context), bound render target;
  3. slots are independent: a slot cycling 17 keys leaves the entries of another slot hitting.
  4. REWINDBOX_TEXMEMO_GHOST_910 (review counterexample: 17 textures in a 16-entry slot, next epoch, the first one looked
     up again was counted as a capacity miss): an evicted key is a capacity miss only while its entry would still serve
     it: not after an epoch, a sampler revision, a section or context generation change, a scoped write over its range,
     clear(), with its target bound, or when the evicted entry was already invalid; a disjoint scoped write keeps it.
Static: ways = 16, the TEXMEMO660 line reports ways= and miss_evicted=, and the checks of a hit (validity(), called by
find()) are the Core 907 ones, in their order.

    python3 test/rpcs3_texmemo_ways908_test.py --source CORE [--baseline CORE907] [--cxx g++] [--no-sanitizers] [--report OUT.json]
                                               [--expect-ways 4]   (only the comparison witness declares 4)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

MEMO_H = 'rpcs3/ios/IOSTextureLookupMemo.h'
VALIDATION_H = 'rpcs3/ios/IOSTextureValidationProfile.h'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'


def require(condition, message):
    if not condition:
        raise SystemExit(f'FAIL: {message}')


DRIVER = r'''
#include "IOSTextureLookupMemo.h"
#include <cstdio>
#include <string>

namespace memo = rpcs3::ios::texture_lookup_memo;
namespace tv = rpcs3::ios::texture_validation;

struct desc { std::uint32_t v = 0; };
using table_t = memo::table<desc, 20>;
static table_t* T;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); ++failures; } } while (0)

static memo::key key_of(std::uint32_t n) { memo::key k{}; k.address = 0x00400000u + n * 0x10000u; k.words = {n, 0x81u, 0, 0, 0x01000100u, 0}; return k; }

// One lookup as texture_cache.h does it: find, else begin, the exact lookup, end (a direct section view).
static memo::miss lookup(std::size_t slot, std::uint32_t n, bool bound = false)
{
	const auto k = key_of(n);
	const auto found = T->find(slot, k, false, bound);
	if (found.value)
	{
		if (found.value->v != n) { std::printf("FAIL: slot %zu key %u served %u\n", slot, n, found.value->v); ++failures; }
		return memo::miss::none;
	}
	memo::count_miss(found.reason);
	const auto t = T->begin(slot, k);
	T->end(t, k, false, bound, desc{n}, true, k.address, 0x10000);
	return found.reason;
}

static std::uint64_t evicted() { return memo::counters.miss_evicted.exchange(0); }

// Lookups of one slot cycling `count` keys for `rounds` rounds; returns the hits after the first round.
static int cycle(std::size_t slot, std::uint32_t first, std::uint32_t count, int rounds)
{
	int hits = 0;
	for (int r = 0; r < rounds; ++r)
		for (std::uint32_t i = 0; i < count; ++i)
			if (lookup(slot, first + i) == memo::miss::none && r > 0) ++hits;
	return hits;
}

int main()
{
	tv::epoch_enabled.store(true);
	memo::configure(memo::mode::active);
	static table_t table;
	T = &table;
	const std::uint32_t W = memo::ways;
	std::printf("{\"ways\": %u", W);

	// 1. Capacity. The first round stores every key; later rounds hit while count <= ways.
	tv::advance_epoch();
	const int six = cycle(0, 100, 6, 4);
	const auto six_evicted = evicted();
	std::printf(", \"cycle6_hits\": %d, \"cycle6_evicted\": %llu", six, (unsigned long long)six_evicted);
	tv::advance_epoch();
	const int full = cycle(1, 200, W, 4);
	const auto full_evicted = evicted();
	tv::advance_epoch();
	const int over = cycle(2, 300, W + 1, 4);
	const auto over_evicted = evicted();
	std::printf(", \"cycle_ways_hits\": %d, \"cycle_ways_evicted\": %llu, \"cycle_over_hits\": %d, \"cycle_over_evicted\": %llu",
		full, (unsigned long long)full_evicted, over, (unsigned long long)over_evicted);
	CHECK(full == int(3 * W) && full_evicted == 0);
	CHECK(over == 0 && over_evicted == 3 * (W + 1));
	CHECK(W >= 6 ? (six == 18 && six_evicted == 0) : (six == 0 && six_evicted == 18));
	// A key never stored is a miss_empty, never a capacity miss.
	CHECK(lookup(3, 999) == memo::miss::empty && evicted() == 0);

	// 2. Invalidations, on slot 4 (keys 400, 401) and slot 5 (key 500).
	tv::advance_epoch();
	auto fill = [] { lookup(4, 400); lookup(4, 401); lookup(5, 500); };
	fill();
	CHECK(lookup(4, 400) == memo::miss::none && lookup(4, 401) == memo::miss::none && lookup(5, 500) == memo::miss::none);
	tv::advance_epoch();
	CHECK(lookup(4, 400) == memo::miss::epoch && lookup(4, 401) == memo::miss::epoch && lookup(5, 500) == memo::miss::epoch);
	CHECK(lookup(4, 400) == memo::miss::none);
	tv::sampler_revision.fetch_add(1);
	CHECK(lookup(4, 400) == memo::miss::revision);
	fill();
	T->invalidate(key_of(401).address + 0x100, 0x10); // overlaps key 401 only
	CHECK(lookup(4, 400) == memo::miss::none && lookup(4, 401) == memo::miss::range && lookup(5, 500) == memo::miss::none);
	CHECK(lookup(4, 401) == memo::miss::none);
	memo::section_changed(false);
	CHECK(lookup(4, 400) == memo::miss::section && lookup(5, 500) == memo::miss::section);
	fill();
	memo::sampler_refresh();
	CHECK(lookup(4, 400) == memo::miss::context);
	fill();
	CHECK(lookup(4, 400, true) == memo::miss::bound);
	CHECK(evicted() == 0);

	// An entry of an older epoch evicted by LRU is not a capacity miss: it would have missed on its epoch anyway.
	tv::advance_epoch();
	for (std::uint32_t i = 0; i < W; ++i) lookup(8, 800 + i);
	tv::advance_epoch();
	for (std::uint32_t i = 0; i < W; ++i) lookup(8, 900 + i);
	CHECK(lookup(8, 800) == memo::miss::empty && evicted() == 0);

		// 3. Slot independence: slot 6 keeps hitting while slot 7 cycles more keys than it holds.
	tv::advance_epoch();
	lookup(6, 600); lookup(6, 600);
	cycle(7, 700, W + 1, 3);
	CHECK(lookup(6, 600) == memo::miss::none);

	// 4. REWINDBOX_TEXMEMO_GHOST_910: an evicted key is a capacity miss only while its entry would still serve it.
	const auto fill_over = [&](std::size_t slot, std::uint32_t first, std::uint32_t extra)
	{
		tv::advance_epoch();
		evicted();
		for (std::uint32_t i = 0; i < W + extra; ++i) lookup(slot, first + i);
		CHECK(evicted() == 0);
	};
	// The reviewed counterexample: 17 keys at epoch N, epoch N + 1, the first key again.
	fill_over(9, 1000, 1);
	tv::advance_epoch();
	CHECK(lookup(9, 1000) == memo::miss::empty && evicted() == 0);
	// Control: without the epoch it is a capacity miss.
	fill_over(9, 1100, 1);
	CHECK(lookup(9, 1100) == memo::miss::empty && evicted() == 1);
	// A sampler revision, a section change, a sampler refresh.
	fill_over(10, 1200, 1);
	tv::sampler_revision.fetch_add(1);
	CHECK(lookup(10, 1200) == memo::miss::empty && evicted() == 0);
	fill_over(10, 1300, 1);
	memo::section_changed(false);
	CHECK(lookup(10, 1300) == memo::miss::empty && evicted() == 0);
	fill_over(10, 1400, 1);
	memo::sampler_refresh();
	CHECK(lookup(10, 1400) == memo::miss::empty && evicted() == 0);
	// A scoped write over the evicted entry's range drops it; a disjoint one keeps the other evicted key.
	fill_over(11, 1500, 2);
	T->invalidate(key_of(1500).address + 0x40, 0x10);
	CHECK(lookup(11, 1501) == memo::miss::empty && evicted() == 1);
	fill_over(11, 1600, 2);
	T->invalidate(key_of(1600).address + 0x40, 0x10);
	CHECK(lookup(11, 1600) == memo::miss::empty && evicted() == 0);
	// clear(), a bound target, and an entry that was already invalid when it was evicted.
	fill_over(12, 1700, 1);
	T->clear();
	CHECK(lookup(12, 1700) == memo::miss::empty && evicted() == 0);
	fill_over(12, 1800, 1);
	CHECK(lookup(12, 1800, true) == memo::miss::empty && evicted() == 0);
	tv::advance_epoch();
	evicted();
	for (std::uint32_t i = 0; i < W; ++i) lookup(13, 1900 + i);
	tv::advance_epoch();
	for (std::uint32_t i = 0; i < W; ++i) lookup(13, 2000 + i); // evicts the stale entries of the last epoch
	CHECK(lookup(13, 1900) == memo::miss::empty && evicted() == 0);
	std::printf(", \"ghost_910\": \"checked\"");

	std::printf(", \"failures\": %d}\n", failures);
	return failures ? 1 : 0;
}
'''


def build_and_run(cxx: str, header_dir: Path, work: Path, name: str, sanitize: bool) -> dict:
    unit = work / f'{name}.cpp'
    unit.write_text(DRIVER)
    binary = work / f'{name}.bin'
    flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Werror', '-Wno-unused-function']
    if sanitize and sys.platform.startswith('linux'):
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    subprocess.run([cxx, *flags, '-I', str(header_dir), str(unit), '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=300)
    sys.stdout.write(result.stdout)
    require(result.returncode == 0, f'{name}: executed check failed\n{result.stdout}{result.stderr[-3000:]}')
    return json.loads(result.stdout.strip().splitlines()[-1])


def hit_checks(text: str, end: str) -> list:
    """The checks of a hit, in their order: the lines from the generations snapshot to `end`, indentation removed."""
    begin = text.index('const auto now = generations::now();\n\t\t\tmiss reason = miss::none;' if 'found find(' in end else
                       'const auto now = generations::now();\n\t\tmiss reason = miss::none;')
    return [line.strip() for line in text[begin:text.index(end if 'found find(' not in end else 'if (reason != miss::none)', begin)].splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--baseline', type=Path, help='the Core 907 tree: find() checks must be unchanged')
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('g++') or shutil.which('clang++'))
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--expect-ways', type=int, choices=(16, 4), default=16,
                        help='the declared capacity: 16 for every reference Core, 4 only for the Assassin\'s Creed '
                             'comparison witness (the same tree with that one constant changed)')
    args = parser.parse_args()

    header = (args.source / MEMO_H).read_text()
    perf = (args.source / PERF).read_text()
    require('REWINDBOX_TEXMEMO_WAYS_908' in header and 'REWINDBOX_TEXMEMO_GHOST_910' in header, 'marker missing in ' + MEMO_H)
    declared = re.findall(r'^constexpr std::size_t ways = (\d+);$', header, re.M)
    require(declared == [str(args.expect_ways)], f'ways = {args.expect_ways} expected, the tree declares {declared}')
    require('"ways=%zu miss_evicted=%llu "' in perf and 'memo::ways, m_evicted);' in perf, 'TEXMEMO660 reports ways and miss_evicted')
    report: dict = {'compiler': args.cxx, 'header_sha256': hashlib.sha256(header.encode()).hexdigest(),
                    'declared_ways': args.expect_ways}
    if args.baseline:
        base = (args.baseline / MEMO_H).read_text()
        require('constexpr std::size_t ways = 4;' in base, 'baseline ways = 4')
        base_find = base[base.index('\tfound find(std::size_t slot, const key& k, bool compressed, bool bound) noexcept'):]
        base_checks = hit_checks(base_find, 'found find(')
        ours_validity = header[header.index('\tmiss validity(std::size_t index, const entry& e, bool compressed, bool bound) const noexcept'):]
        ours_checks = hit_checks(ours_validity, 'return reason;')
        require(len(base_checks) > 20 and ours_checks == base_checks, 'the checks of a hit changed against Core 907')
        ours_find = header[header.index('\tfound find(std::size_t slot, const key& k, bool compressed, bool bound) noexcept'):]
        ours_find = ours_find[:ours_find.index('\t\treturn { nullptr, miss::empty };')]
        require('const miss reason = validity(index, e, compressed, bound);' in ours_find and
                'if (!e.valid || !(e.k == k) || e.compressed != compressed)' in ours_find, 'find() serves through validity()')
        report['hit_checks_unchanged'] = len(base_checks)

    with tempfile.TemporaryDirectory(prefix='texmemo908-') as temporary:
        work = Path(temporary)
        for name, ways in (('ways16', 16), ('ways4', 4)):
            include = work / name
            include.mkdir()
            text = header if ways == args.expect_ways else header.replace(
                f'constexpr std::size_t ways = {args.expect_ways};', f'constexpr std::size_t ways = {ways};')
            require(f'constexpr std::size_t ways = {ways};' in text, f'the {ways}-way copy of the header')
            (include / 'IOSTextureLookupMemo.h').write_text(text)
            shutil.copy(args.source / VALIDATION_H, include / 'IOSTextureValidationProfile.h')
            report[name] = build_and_run(args.cxx, include, work, name, not args.no_sanitizers)
    require(report['ways16']['ways'] == 16 and report['ways4']['ways'] == 4 and
            report['ways16']['cycle6_hits'] == 18 and report['ways4']['cycle6_hits'] == 0,
            'six textures on one slot: hits with 16 ways, none with 4')
    report['result'] = 'passed'
    print(f'PASS (tree declares {args.expect_ways} ways): 16 ways hit a 6- and 16-texture cycle on one slot (4 ways: none), 17 overflows by LRU and is counted as '
          'capacity misses; every invalidation drops as before; slots independent; an evicted key is a capacity miss only '
          'while its entry would still serve it (epoch, revision, generations, scoped write, clear, bound)')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
