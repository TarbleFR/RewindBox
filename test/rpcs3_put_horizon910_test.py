#!/usr/bin/env python3
"""REWINDBOX_PUT_HORIZON_910, executed: texture epochs deferred to the PUT horizon never serve a texture older than
what the command could legally sample, against the witness that starts an epoch at every PUT change read.

God of War III (build 694, Core 907): about 358 texture epochs per frame while the RSX FIFO ran dry about 55 times per
frame; every epoch makes every texture hash again. The decision is rpcs3::ios::texture_validation::put_horizon::observe
(rpcs3/ios/IOSTextureValidationProfile.h), called by FIFO_control::read_put with the FIFO position.

The driver executes that real function inside a model of the guest and the RSX: a ring command buffer with wrapping
JUMPs, calls into display lists, semaphore acquires, frame ends and epochs of other sources; a guest that writes textures
and publishes commands (PUT); an RSX that validates a texture once per epoch (the hash reads guest memory then).
For every executed draw the texture version served must be one guest memory held between the moment the command's data
was ready (its publication, or the last semaphore acquire satisfied before it) and its execution. Guests:
  synced  writes a texture only while no visible command still needs it (or while the RSX waits in an acquire):
          exactly one version is legal for every draw;
  racy    writes at any time: several versions are legal, none older than the window.
Methods with several arguments are read as the FIFO reads them (the first argument after inc_get, the next ones by
read_unsafe, which looks at PUT from the word before the argument), and PUT may stop inside a method.
Two more guests (independent review of the first version):
  resets  resets the FIFO (new GET and PUT set together) onto commands it just rewrote ahead of the RSX;
  spins   publishes a jump to itself with commands behind it, writes their data while the RSX spins, then patches it.
Runs: 400 schedules per guest and RSX speed (lagging and keeping up), horizon on and off, the same schedules.
Required: no illegal version in any run with the horizon, nor in the witness (except with spins: an epoch per PUT change
never covered a patched jump); never more epochs with the horizon, the patched-jump epochs apart; in the lagging runs at
least 40 % fewer epochs and fewer hashes in total. Negative controls on the real header: the horizon bound removed, the
word at the horizon consumed from the word before it (no margin of one word), the publication inside the segment
ignored; on the model: the horizon kept across a FIFO reset, no epoch for a patched jump. Each must serve an illegal version.
Static: read_put passes the FIFO position, defers only with the Fast FIFO and keeps one epoch per PUT change when the
horizon is off; the FIFO reset and the FIFO recovery forget the horizon; a patched jump to itself starts an epoch with
the horizon on; policy Automatic = God of War III with the epochs on.

    python3 test/rpcs3_put_horizon910_test.py --source CORE [--cxx g++] [--no-sanitizers] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PROFILE_H = 'rpcs3/ios/IOSTextureValidationProfile.h'
FIFO_CPP = 'rpcs3/Emu/RSX/RSXFIFO.cpp'
POLICY_CPP = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'


def require(condition, message):
    if not condition:
        raise SystemExit(f'FAIL: {message}')


DRIVER = r'''
#include "IOSTextureValidationProfile.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <array>
#include <string>

namespace tv = rpcs3::ios::texture_validation;

struct rng
{
	std::uint64_t s;
	std::uint32_t next() { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return static_cast<std::uint32_t>(s >> 11); }
	bool chance(std::uint32_t percent) { return next() % 100 < percent; }
	std::uint32_t below(std::uint32_t n) { return next() % n; }
};

enum kind : std::uint8_t { NONE, DRAW, ACQUIRE, JUMP, CALL, RET, HDR, ARG, SPIN, NOP };
struct command { kind k = NONE; std::uint32_t arg = 0; std::uint64_t published = 0; };

constexpr std::uint32_t ring_slots = 96;      // main command buffer, 4 bytes per command
constexpr std::uint32_t sub_base = 0x10000;   // display lists (static): 3 commands each
constexpr std::uint32_t subs = 4;
constexpr std::uint32_t textures = 12;

struct result { std::uint64_t draws = 0, illegal = 0, epochs = 0, hashes = 0, deferred = 0, put_changes = 0, patch_epochs = 0, resets = 0, spins = 0, arg_draws = 0; };

// resets: the guest resets the FIFO (new GET and PUT, sys_rsx attribute 0x001) onto commands it just rewrote.
// spins: the guest publishes a jump to itself with commands behind it, writes their data while the RSX spins, then
// patches the jump. forget_on_reset / patch_epoch: what RSXThread.cpp and RSXFIFO.cpp do with the horizon on.
struct options { bool horizon_on = false, racy = false, resets = false, spins = false, forget_on_reset = true, patch_epoch = true; std::uint32_t rsx_percent = 35; };

result simulate(std::uint64_t seed, const options& o, std::uint32_t steps)
{
	const bool horizon_on = o.horizon_on, racy = o.racy;
	const std::uint32_t rsx_percent = o.rsx_percent;
	rng r{seed * 0x9E3779B97F4A7C15ull + 1};
	result out;
	std::uint64_t now = 1;

	// Guest memory: per texture, the history of (first tick, version).
	std::array<std::vector<std::pair<std::uint64_t, std::uint32_t>>, textures> history;
	std::array<std::uint32_t, textures> version{};
	for (auto& h : history) h.push_back({0, 0});
	std::array<std::uint32_t, textures> visible_uses{}; // published, not executed yet

	std::vector<command> ring(ring_slots);
	std::array<std::array<command, 3>, subs> lists;
	for (std::uint32_t i = 0; i < subs; ++i)
	{
		lists[i] = {{ {DRAW, (i * 2) % textures, 0}, {DRAW, (i * 2 + 1) % textures, 0}, {RET, 0, 0} }};
	}
	const auto uses = [&](const command& c, auto&& f)
	{
		if (c.k == DRAW || c.k == ARG) f(c.arg);
		if (c.k == CALL) { f(lists[c.arg][0].arg); f(lists[c.arg][1].arg); }
	};

	// Guest state.
	std::uint32_t wpos = 0;  // next slot to write
	std::uint32_t put = 0;   // published up to here (address)
	std::vector<std::uint32_t> staged; // slots written, not published
	bool sema_released = false;

	// RSX state.
	std::uint32_t get = 0;        // address
	std::uint32_t return_to = 0;
	bool waiting_acquire = false;
	std::uint64_t ready_since = 0; // the last satisfied acquire
	std::uint64_t epoch = 1;
	std::array<std::uint64_t, textures> valid_epoch{};
	std::array<std::uint32_t, textures> cached{};
	tv::put_horizon horizon;
	std::uint32_t last_put_seen = ~0u;
	std::uint32_t draws_in_frame = 0;
	std::uint32_t remaining = 0;     // arguments of the open method not consumed yet
	bool need_first = false;         // the header was read, its first argument not yet (inc_get)
	std::uint32_t spin_addr = ~0u;   // the last jump to itself executed (RSXFIFO.cpp m_spin_addr)
	std::uint32_t spin_slot = ~0u;   // guest: the unpatched jump to itself
	std::array<std::uint32_t, 2> spin_textures{};

	// FIFO_control::read_put: the FIFO at get_now (its internal GET) reads PUT.
	const auto see_put = [&](std::uint32_t get_now)
	{
		if (put != last_put_seen) { out.put_changes++; last_put_seen = put; }
		if (put != horizon.seen || horizon.deferred)
		{
			if (horizon.observe(get_now, put, epoch, horizon_on))
			{
				epoch++;
				horizon.started(epoch);
			}
		}
	};

	const auto write_texture = [&](std::uint32_t t)
	{
		version[t]++;
		history[t].push_back({now, version[t]});
	};
	const auto legal = [&](std::uint32_t t, std::uint32_t v, std::uint64_t from, std::uint64_t to)
	{
		const auto& h = history[t];
		for (std::size_t i = 0; i < h.size(); ++i)
		{
			const std::uint64_t begin = h[i].first;
			const std::uint64_t end = i + 1 < h.size() ? h[i + 1].first : ~0ull;
			if (h[i].second == v) return begin <= to && end > from;
		}
		return false;
	};
	const auto exec_draw = [&](std::uint32_t t, std::uint64_t published)
	{
		if (valid_epoch[t] != epoch)
		{
			cached[t] = version[t]; // the hash reads guest memory now
			valid_epoch[t] = epoch;
			out.hashes++;
		}
		out.draws++;
		const std::uint64_t ready = published > ready_since ? published : ready_since;
		if (!legal(t, cached[t], ready, now)) out.illegal++;
		if (++draws_in_frame >= 40)
		{
			draws_in_frame = 0;
			epoch++; // frame end
		}
	};

	for (std::uint32_t step = 0; step < steps; ++step, ++now)
	{
		if (r.chance(rsx_percent))
		{
			// --- RSX: read PUT at this position, then one command.
			if (waiting_acquire)
			{
				if (!sema_released) continue;
				waiting_acquire = false;
				sema_released = false;
				epoch++; // the producer released the semaphore after its writes
				ready_since = now;
				get += 4;
				continue;
			}
			if (r.chance(2)) epoch++; // an epoch of another source (flush, invalidation, RSX write)
			if (need_first || remaining)
			{
				// The arguments of a method, each one a draw (a non-incrementing method with several arguments).
				if (need_first)
				{
					see_put(get); // inc_get(true): GET is already on the first argument
					if (put == get) continue;
					need_first = false;
				}
				else
				{
					see_put(get); // read_unsafe: PUT is read from the last word consumed, the argument is the next one
					if (get + 4 == put) continue;
					get += 4;
				}
				const command a = ring[get / 4];
				if (a.k != ARG) { std::printf("FAIL: argument expected at 0x%x (seed %llu)\n", get, static_cast<unsigned long long>(seed)); std::exit(1); }
				exec_draw(a.arg, a.published);
				out.arg_draws++;
				visible_uses[a.arg]--;
				if (--remaining == 0) get += 4;
				continue;
			}
			if (get < sub_base)
			{
				see_put(get);
				if (get == put) continue; // FIFO empty
			}
			const command c = get >= sub_base ? lists[(get - sub_base) / 16][((get - sub_base) % 16) / 4] : ring[get / 4];
			if (spin_addr != ~0u)
			{
				// FIFO_control::read: a different command where the FIFO jumped to itself is the guest's patch.
				const bool patched = get == spin_addr && c.k != SPIN;
				if (patched || get != spin_addr) spin_addr = ~0u;
				if (patched)
				{
					ready_since = now; // the data of the commands behind was written before the patch
					if (horizon_on && o.patch_epoch) { epoch++; out.patch_epochs++; }
				}
			}
			const std::uint64_t published = get >= sub_base ? ring[(return_to - 4) / 4].published : c.published;
			switch (c.k)
			{
			case DRAW:
				exec_draw(c.arg, published);
				if (get < sub_base) visible_uses[c.arg]--;
				get += 4;
				break;
			case ACQUIRE:
				waiting_acquire = true;
				break;
			case JUMP:
				get = c.arg;
				break;
			case CALL:
				return_to = get + 4;
				visible_uses[lists[c.arg][0].arg]--;
				visible_uses[lists[c.arg][1].arg]--;
				get = sub_base + c.arg * 16;
				break;
			case RET:
				get = return_to;
				break;
			case HDR:
				remaining = c.arg;
				need_first = true;
				get += 4;
				break;
			case SPIN:
				spin_addr = get; // jump to itself
				break;
			case NOP:
				get += 4;
				break;
			default:
				std::printf("FAIL: RSX reached an unwritten command at 0x%x (seed %llu)\n", get, static_cast<unsigned long long>(seed));
				std::exit(1);
			}
			continue;
		}

		// --- Guest.
		const std::uint32_t action = r.below(100);
		if (waiting_acquire && !sema_released)
		{
			// The RSX waits for the guest: write the data of the commands behind the acquire, then release.
			if (action < 60) write_texture(r.below(textures));
			else sema_released = true;
			continue;
		}
		if (spin_slot != ~0u && get == spin_slot * 4 && spin_addr == get)
		{
			// The RSX spins on the jump: write the data of the commands behind it, then patch the jump.
			if (action < 60) write_texture(spin_textures[r.below(2)]);
			else { ring[spin_slot] = {NOP, 0, now}; spin_slot = ~0u; }
			continue;
		}
		if (o.resets && action == 99 && staged.empty() && r.chance(30))
		{
			// FIFO reset: new commands and their data written just ahead of the RSX, then GET and PUT set together.
			const std::uint32_t n0 = (get < sub_base ? get / 4 : return_to / 4) + 1;
			std::uint32_t count = 3 + r.below(6);
			if (n0 + count == put / 4) count++;
			if (n0 + count >= ring_slots - 2) continue;
			visible_uses.fill(0);
			for (std::uint32_t i = 0; i < count; ++i)
			{
				const std::uint32_t t = r.below(textures);
				write_texture(t);
				ring[n0 + i] = {DRAW, t, now};
				visible_uses[t]++;
			}
			wpos = n0 + count;
			put = wpos * 4;
			get = n0 * 4;
			remaining = 0; need_first = false; waiting_acquire = false; sema_released = false; spin_addr = ~0u; spin_slot = ~0u;
			if (o.forget_on_reset) horizon = {}; // FIFO_control::reset_epoch_horizon
			out.resets++;
			continue;
		}
		if (action < 25)
		{
			const std::uint32_t t = r.below(textures);
			if (racy || visible_uses[t] == 0) write_texture(t);
		}
		else if (action < 75)
		{
			// Stage one command, never over one the RSX has not executed.
			const std::uint32_t rsx_slot = (get < sub_base ? get : return_to) / 4;
			const auto free_after = [&](std::uint32_t slot) { return (rsx_slot + ring_slots - slot - 1) % ring_slots; };
			if (wpos == ring_slots - 1)
			{
				if (rsx_slot == 0 || free_after(wpos) < 2) continue; // the wrap target must be free
				ring[wpos] = {JUMP, 0, 0};
				staged.push_back(wpos);
				wpos = 0;
				continue;
			}
			if (free_after(wpos) < 3) continue;
			const std::uint32_t pick = r.below(100);
			if (pick < 18 && wpos + 3 <= ring_slots - 1 && free_after(wpos) >= 5)
			{
				// A method with two arguments, each a draw; it may be published word by word.
				ring[wpos] = {HDR, 2, 0};
				ring[wpos + 1] = {ARG, r.below(textures), 0};
				ring[wpos + 2] = {ARG, r.below(textures), 0};
				for (std::uint32_t i = 0; i < 3; ++i) staged.push_back(wpos + i);
				wpos += 3;
				continue;
			}
			if (o.spins && pick >= 96 && spin_slot == ~0u && staged.empty() && wpos + 3 <= ring_slots - 1 && free_after(wpos) >= 5)
			{
				// A jump to itself and two draws behind it, published at once; their data comes while the RSX spins.
				spin_textures = {r.below(textures), r.below(textures)};
				ring[wpos] = {SPIN, 0, now};
				ring[wpos + 1] = {DRAW, spin_textures[0], now};
				ring[wpos + 2] = {DRAW, spin_textures[1], now};
				visible_uses[spin_textures[0]]++;
				visible_uses[spin_textures[1]]++;
				spin_slot = wpos;
				wpos += 3;
				put = wpos * 4;
				out.spins++;
				continue;
			}
			command c{};
			if (pick < 80) c = {DRAW, r.below(textures), 0};
			else if (pick < 92) c = {CALL, r.below(subs), 0};
			else c = {ACQUIRE, 0, 0};
			ring[wpos] = c;
			staged.push_back(wpos);
			wpos++;
		}
		else if (!staged.empty())
		{
			// Publish: the commands become visible; their data was written before. Sometimes only the first words
			// (PUT may stop inside a method: the FIFO waits for the missing argument).
			std::size_t count = staged.size();
			bool wraps = false;
			for (const std::uint32_t slot : staged) wraps |= ring[slot].k == JUMP;
			if (!wraps && count >= 2 && r.chance(35)) count = 1 + r.below(static_cast<std::uint32_t>(count - 1));
			for (std::size_t i = 0; i < count; ++i)
			{
				const std::uint32_t slot = staged[i];
				ring[slot].published = now;
				uses(ring[slot], [&](std::uint32_t t) { visible_uses[t]++; });
			}
			put = count == staged.size() ? wpos * 4 : staged[count] * 4;
			staged.erase(staged.begin(), staged.begin() + count);
		}
	}
	out.epochs = epoch;
	out.deferred = tv::put_deferred.exchange(0);
	return out;
}

int main(int argc, char** argv)
{
	const std::uint32_t seeds = argc > 1 ? std::atoi(argv[1]) : 400;
	const std::string control = argc > 2 ? argv[2] : "";
	std::printf("{");
	bool first = true;
	int failures = 0;
	struct config { const char* name; bool racy, resets, spins; };
	for (const config& cfg : { config{"synced", false, false, false}, config{"racy", true, false, false},
		config{"resets", false, true, false}, config{"spins", false, false, true} })
	for (const std::uint32_t rsx_percent : {35u, 70u})
	{
		result on{}, off{};
		std::uint64_t more_epochs = 0;
		for (std::uint32_t seed = 1; seed <= seeds; ++seed)
		{
			options o{};
			o.racy = cfg.racy; o.resets = cfg.resets; o.spins = cfg.spins; o.rsx_percent = rsx_percent;
			o.forget_on_reset = control != "no_forget_on_reset";
			o.patch_epoch = control != "no_patch_epoch";
			o.horizon_on = true;
			const result a = simulate(seed, o, 6000);
			o.horizon_on = false;
			const result b = simulate(seed, o, 6000);
			if (a.draws != b.draws || a.put_changes != b.put_changes)
			{
				std::printf("FAIL: the two modes ran different schedules (seed %u)\n", seed);
				return 1;
			}
			if (a.epochs - a.patch_epochs > b.epochs) more_epochs++;
			on.draws += a.draws; on.illegal += a.illegal; on.epochs += a.epochs; on.hashes += a.hashes; on.deferred += a.deferred; on.put_changes += a.put_changes;
			on.patch_epochs += a.patch_epochs; on.resets += a.resets; on.spins += a.spins; on.arg_draws += a.arg_draws;
			off.draws += b.draws; off.illegal += b.illegal; off.epochs += b.epochs; off.hashes += b.hashes; off.deferred += b.deferred;
		}
		std::printf("%s\"%s_rsx%u\": {\"draws\": %llu, \"put_changes\": %llu, \"illegal_horizon\": %llu, \"illegal_witness\": %llu, "
			"\"epochs_horizon\": %llu, \"epochs_witness\": %llu, \"hashes_horizon\": %llu, \"hashes_witness\": %llu, \"deferred\": %llu, "
			"\"deferred_witness\": %llu, \"runs_with_more_epochs\": %llu, \"patch_epochs\": %llu, \"resets\": %llu, \"spins\": %llu, \"arg_draws\": %llu}",
			first ? "" : ", ", cfg.name, rsx_percent,
			(unsigned long long)on.draws, (unsigned long long)on.put_changes, (unsigned long long)on.illegal, (unsigned long long)off.illegal,
			(unsigned long long)on.epochs, (unsigned long long)off.epochs, (unsigned long long)on.hashes, (unsigned long long)off.hashes,
			(unsigned long long)on.deferred, (unsigned long long)off.deferred, (unsigned long long)more_epochs,
			(unsigned long long)on.patch_epochs, (unsigned long long)on.resets, (unsigned long long)on.spins, (unsigned long long)on.arg_draws);
		first = false;
		// The witness (one epoch per PUT change read, none for a patched jump) is not required to be legal with spins.
		failures += on.illegal || (!cfg.spins && off.illegal) || more_epochs;
	}
	std::printf("}\n");
	return failures ? 2 : 0;
}
'''

# Negative controls on the real header: (name, pattern, replacement).
BOUND = ('get_now >= get && get_now < horizon && horizon - get_now > 4 &&\n'
         '\t\t\t!(put >= get && put < horizon))')
MUTATIONS = [
    ('no_horizon_bound', BOUND, 'get_now >= get && !(put >= get && put < horizon))'),
    ('no_word_margin', BOUND, 'get_now >= get && get_now < horizon && !(put >= get && put < horizon))'),
    ('ignore_publication_inside_segment_and_bound', 'put != horizon && ' + BOUND, 'put != horizon)'),
]
MODEL_CONTROLS = {'no_forget_on_reset': 'resets', 'no_patch_epoch': 'spins'}


def build(cxx: str, include: Path, work: Path, name: str, sanitize: bool) -> Path:
    unit = work / f'{name}.cpp'
    unit.write_text(DRIVER)
    binary = work / f'{name}.bin'
    flags = ['-std=c++20', '-O2', '-g', '-Wall', '-Werror']
    if sanitize and sys.platform.startswith('linux'):
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    subprocess.run([cxx, *flags, '-I', str(include), str(unit), '-o', str(binary)], check=True)
    return binary


def static_checks(source: Path) -> None:
    fifo = (source / FIFO_CPP).read_text()
    require('m_epoch_horizon.observe(m_internal_get, put, validation::validation_epoch.load(std::memory_order_relaxed),\n'
            '\t\t\t\t\tvalidation::put_horizon_policy::enabled.load(std::memory_order_relaxed) && !g_cfg.core.rsx_fifo_accuracy))' in fifo,
            'read_put passes the FIFO position and defers only with the policy and the Fast FIFO')
    require('if (put != m_epoch_horizon.seen || m_epoch_horizon.deferred) [[unlikely]]' in fifo, 'read_put fast path')
    require(fifo.count('validation::advance_epoch(validation::epoch_source::put);') == 1 and 'm_epoch_put' not in fifo, 'one PUT epoch site')
    require('if (spin_cmd && get == m_internal_get)\n\t\t\t{\n\t\t\t\tm_spin_addr = get;\n\t\t\t\tm_spin_cmd = spin_cmd;' in fifo,
            'set_get remembers a jump to itself')
    patched = fifo.index('const bool patched = m_internal_get == m_spin_addr && m_cmd != m_spin_cmd;')
    require(fifo.count('rpcs3::ios::texture_validation::advance_epoch(rpcs3::ios::texture_validation::epoch_source::put);') == 1 and
            'if (patched && rpcs3::ios::texture_validation::put_horizon_policy::enabled.load(std::memory_order_relaxed))' in fifo and
            patched < fifo.index('if (m_cmd & RSX_METHOD_NON_METHOD_CMD_MASK) [[unlikely]]', patched) < patched + 1200,
            'a patched jump to itself starts an epoch before its command is decoded (horizon on)')
    header = (source / 'rpcs3/Emu/RSX/RSXFIFO.h').read_text()
    require('void reset_epoch_horizon() { m_epoch_horizon = {}; m_spin_addr = umax; }' in header, 'reset_epoch_horizon')
    thread = (source / 'rpcs3/Emu/RSX/RSXThread.cpp').read_text().replace('\r\n', '\n')
    require('fifo_ctrl->set_get(static_cast<u32>(get_put));\n#ifdef RPCS3_IOS\n\t\t\t\t\tfifo_ctrl->reset_epoch_horizon();' in thread and
            'fifo_ctrl->set_get(restore_point);\n#ifdef RPCS3_IOS\n\t\tfifo_ctrl->reset_epoch_horizon();' in thread and
            thread.count('reset_epoch_horizon()') == 2, 'the FIFO reset and the FIFO recovery forget the horizon')
    policy = (source / POLICY_CPP).read_text()
    require('resolved.put_epoch_horizon = resolved.texture_validation_epoch &&\n'
            '\t\tresolve_mode(g_cfg.ios_experimental.put_epoch_horizon, is_god_of_war_iii_title(title_id));' in policy,
            'Automatic = God of War III, with the epochs on')
    require('put_horizon_policy::enabled.store(resolved.put_epoch_horizon' in policy, 'policy published')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('g++') or shutil.which('clang++'))
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--seeds', type=int, default=400)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    static_checks(args.source)
    header = (args.source / PROFILE_H).read_text()
    require('REWINDBOX_PUT_HORIZON_910' in header, 'marker')
    report: dict = {'compiler': args.cxx}
    with tempfile.TemporaryDirectory(prefix='horizon910-') as temporary:
        work = Path(temporary)
        include = work / 'real'
        include.mkdir()
        (include / 'IOSTextureValidationProfile.h').write_text(header)
        binary = build(args.cxx, include, work, 'horizon', not args.no_sanitizers)
        result = subprocess.run([str(binary), str(args.seeds)], capture_output=True, text=True, timeout=1800)
        sys.stdout.write(result.stdout)
        require(result.returncode == 0, 'an illegal texture version, or more epochs with the horizon\n' + result.stderr[-2000:])
        runs = json.loads(result.stdout.strip().splitlines()[-1])
        require(len(runs) == 8, 'eight runs')
        for name, run in runs.items():
            spins = name.startswith('spins')
            require(run['draws'] > 500 * args.seeds and run['arg_draws'] > 50 * args.seeds and run['illegal_horizon'] == 0 and
                    (spins or run['illegal_witness'] == 0), f'{name}: legality: {run}')
            require(run['epochs_horizon'] - run['patch_epochs'] <= run['epochs_witness'] and run['deferred_witness'] == 0 and
                    run['runs_with_more_epochs'] == 0, name + ': epochs')
            require((run['resets'] > args.seeds) == name.startswith('resets') and (run['patch_epochs'] > args.seeds) == spins and
                    (run['spins'] > args.seeds) == spins, f'{name}: the scenario ran: {run}')
            if name.endswith('rsx35') and not spins:
                require(run['epochs_horizon'] * 10 <= run['epochs_witness'] * 6 and run['hashes_horizon'] < run['hashes_witness'],
                        f'{name}: the lagging RSX saves less than 40 % of the epochs: {run}')
        report['runs'] = runs
        report['negative_controls'] = {}
        for name, pattern, replacement in MUTATIONS:
            require(header.count(pattern) == 1, 'mutation pattern ' + name)
            mutant_include = work / name
            mutant_include.mkdir()
            (mutant_include / 'IOSTextureValidationProfile.h').write_text(header.replace(pattern, replacement))
            mutant = build(args.cxx, mutant_include, work, name, False)
            outcome = subprocess.run([str(mutant), str(args.seeds)], capture_output=True, text=True, timeout=1800)
            data = json.loads(outcome.stdout.strip().splitlines()[-1]) if outcome.stdout.strip().startswith('{') else {}
            illegal = sum(run['illegal_horizon'] for run in data.values())
            require(outcome.returncode == 2 and illegal > 0 and
                    all(run['illegal_witness'] == 0 for key, run in data.items() if not key.startswith('spins')),
                    f'negative control {name}: no illegal version served ({outcome.returncode})')
            report['negative_controls'][name] = illegal
            print(f'negative control {name}: {illegal} illegal versions served')
        for name, scenario in MODEL_CONTROLS.items():
            outcome = subprocess.run([str(binary), str(args.seeds), name], capture_output=True, text=True, timeout=1800)
            data = json.loads(outcome.stdout.strip().splitlines()[-1])
            illegal = sum(run['illegal_horizon'] for key, run in data.items() if key.startswith(scenario))
            others = sum(run['illegal_horizon'] for key, run in data.items() if not key.startswith(scenario))
            require(outcome.returncode == 2 and illegal > 0 and others == 0, f'negative control {name}: {illegal} illegal, {others} elsewhere')
            report['negative_controls'][name] = illegal
            print(f'negative control {name}: {illegal} illegal versions served')
        report['witness_illegal_with_spins'] = sum(run['illegal_witness'] for key, run in runs.items() if key.startswith('spins'))
    report['result'] = 'passed'
    print('PASS: with the PUT horizon every draw samples a version legal for its command (synced and racy guests, lagging and '
          'fast RSX, ring wrap, display lists, acquires, PUT inside a method, FIFO resets, patched jumps), never more epochs than '
          'the witness apart from the patched-jump epochs, at least 40 % fewer when the RSX lags; the negative controls serve illegal versions')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
