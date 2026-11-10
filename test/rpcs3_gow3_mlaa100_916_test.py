#!/usr/bin/env python3
"""REWINDBOX_GOW3_MLAA_100_916, executed: the God of War III MLAA bypass on the 01.00 executable.

Build 718, BCES00510, PID 45272: the title's "God of War III MLAA Bypass" is Enabled (boot policy gow3_mlaa=1), the
executable is PPU-4d5c51503a81a327c2a99427390a395b8dcb3767 (application 01.00) and COREPROF GOW3MLAA909 shows that
nothing was applied: the Core knew the 01.03 executable only. RPCS3's patch repository holds "Disable MLAA" (illusion,
ZEROx, patch version 3.0) for both: [ byte, 0x52BF2F, 0 ] and [ be32, 0x00231248 (01.00) / 0x0023137c (01.03), nop ].

The driver compiles the real rpcs3/ios/IOSGow3MlaaPatch.h and executes its plan on a memory model: the 01.00 pair is
written only on a relative call and a flag byte of 0 or 1 (any other content: nothing written), exactly one byte and
one word change, a second application writes nothing; the 01.03 pair is the one delivered since Build 351; another
executable has no plan; `present` answers for a savestate. Static: the loader applies a plan at a fresh boot only,
under the title's setting, for the six God of War III serials, and reports the refusal. With --previous (a Core 914
tree) the defect is shown: that loader names the 01.03 executable only.
Host behaviour only: no frame rate is inferred here; the picture loses the game's own anti-aliasing when the bypass
applies, which is what the setting asks for.

    python3 test/rpcs3_gow3_mlaa100_916_test.py --source CORE [--previous CORE914] [--cxx g++]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

HARNESS = r'''
#include "ios/IOSGow3MlaaPatch.h"
#include <cstdint>
#include <cstdio>
#include <map>
#include <vector>

namespace patch = rpcs3::ios::gow3_mlaa_patch;
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }

struct memory
{
	std::map<std::uint32_t, std::uint8_t> bytes;
	std::vector<std::uint32_t> wrote;
	std::uint8_t r8(std::uint32_t a) { return bytes[a]; }
	std::uint32_t r32(std::uint32_t a) { return std::uint32_t{bytes[a]} << 24 | std::uint32_t{bytes[a + 1]} << 16 | std::uint32_t{bytes[a + 2]} << 8 | bytes[a + 3]; }
	void w8(std::uint32_t a, std::uint8_t v) { bytes[a] = v; }
	void w32(std::uint32_t a, std::uint32_t v) { bytes[a] = v >> 24; bytes[a + 1] = v >> 16; bytes[a + 2] = v >> 8; bytes[a + 3] = v; }
	patch::result apply(const patch::plan& p)
	{
		return patch::apply(p, [&](std::uint32_t a) { return r8(a); }, [&](std::uint32_t a) { return r32(a); },
			[&](std::uint32_t a, std::uint8_t v) { w8(a, v); }, [&](std::uint32_t a, std::uint32_t v) { w32(a, v); },
			[&](std::uint32_t a) { wrote.push_back(a); });
	}
};

int main()
{
	const patch::plan* v100 = patch::find("PPU-4d5c51503a81a327c2a99427390a395b8dcb3767");
	const patch::plan* v103 = patch::find("PPU-19724fde16a5b111b7b4d2a065f5dccaf8e01962");
	check(v100 && v103 && v100 != v103, "both executables have a plan");
	check(!patch::find("PPU-cc23d46d671458b37f34e08b6e06d1751084a34e") && !patch::find("") && !patch::find("PPU-4d5c51503a81a327c2a99427390a395b8dcb3768"),
		"another executable has none");
	check(v100->flag_address == 0x52bf2f && v100->call_address == 0x231248 && v100->guarded && !v100->clear_flag_word, "the 01.00 lines of the repository");
	check(v103->flag_address == 0x52bf2f && v103->call_address == 0x23137c && !v103->guarded && v103->clear_flag_word, "the 01.03 lines as delivered");
	check(patch::is_relative_call(0x4bfff8d1) && patch::is_relative_call(0x48000001) && !patch::is_relative_call(0x48000000) &&
		!patch::is_relative_call(0x48000003) && !patch::is_relative_call(0x4e800421) && !patch::is_relative_call(0x7c0802a6), "a relative call is bl only");

	const auto image = [](std::uint32_t call_address, std::uint32_t word, std::uint8_t flag)
	{
		memory m;
		m.w32(0x52bf2c, 0x01020300 | flag); // three bytes before the flag that are not the patch's
		m.w32(call_address, word);
		m.w32(call_address - 4, 0x7c0802a6);
		m.w32(call_address + 4, 0x38600000);
		return m;
	};

	{ // 01.00, the expected content
		memory m = image(0x231248, 0x4bfff8d1, 1);
		const patch::result r = m.apply(*v100);
		check(r.what == patch::outcome::applied && r.writes == 2 && r.call_word == 0x4bfff8d1 && r.flag_byte == 1, "01.00 is applied on a call and a set flag");
		check(m.r32(0x231248) == patch::nop && m.r8(0x52bf2f) == 0, "the call is a nop and the flag is 0");
		check(m.r32(0x52bf2c) == 0x01020300 && m.r32(0x231244) == 0x7c0802a6 && m.r32(0x23124c) == 0x38600000, "one byte and one word change, nothing beside them");
		check(m.wrote == std::vector<std::uint32_t>({0x52bf2f, 0x231248}), "both addresses join the loader's list");
		check(patch::present(*v100, [&](std::uint32_t a) { return m.r8(a); }, [&](std::uint32_t a) { return m.r32(a); }), "present on patched memory");
		m.wrote.clear();
		const patch::result again = m.apply(*v100);
		check(again.what == patch::outcome::already_applied && again.writes == 0 && m.wrote.empty(), "a second application writes nothing");
	}
	{ // 01.00, flag already 0
		memory m = image(0x231248, 0x48001235, 0);
		const patch::result r = m.apply(*v100);
		check(r.what == patch::outcome::applied && r.writes == 1 && m.r32(0x231248) == patch::nop && m.wrote == std::vector<std::uint32_t>({0x231248}), "01.00 with a clear flag writes the call only");
	}
	for (const std::uint32_t word : {0x7c0802a6u, 0x4e800421u, 0x48000000u, 0x00000000u, 0x4bfff8d0u})
	{ // 01.00, the word is not a relative call
		memory m = image(0x231248, word, 1);
		const auto before = m.bytes;
		const patch::result r = m.apply(*v100);
		check(r.what == patch::outcome::refused_guard && r.writes == 0 && m.bytes == before && m.wrote.empty() && r.call_word == word, "01.00 refuses a word that is not a relative call and writes nothing");
		check(!patch::present(*v100, [&](std::uint32_t a) { return m.r8(a); }, [&](std::uint32_t a) { return m.r32(a); }), "not present on unpatched memory");
	}
	{ // 01.00, the flag byte is not a flag
		memory m = image(0x231248, 0x4bfff8d1, 0x37);
		const auto before = m.bytes;
		check(m.apply(*v100).what == patch::outcome::refused_guard && m.bytes == before && m.wrote.empty(), "01.00 refuses a flag byte that is neither 0 nor 1");
	}
	{ // 01.03, as delivered: the whole word of the flag, the call, no guard
		memory m = image(0x23137c, 0x4bfff8d1, 1);
		const patch::result r = m.apply(*v103);
		check(r.what == patch::outcome::applied && m.r32(0x52bf2c) == 0 && m.r32(0x23137c) == patch::nop && m.wrote == std::vector<std::uint32_t>({0x52bf2c, 0x23137c}), "01.03 writes the delivered pair");
		memory other = image(0x23137c, 0x7c0802a6, 0x37);
		check(other.apply(*v103).what == patch::outcome::applied && other.r32(0x52bf2c) == 0 && other.r32(0x23137c) == patch::nop, "01.03 keeps its delivered behaviour (no guard)");
		memory wrong = image(0x231248, 0x4bfff8d1, 1);
		wrong.apply(*v103);
		check(wrong.r32(0x231248) == 0x4bfff8d1, "the 01.03 plan does not touch the 01.00 call");
	}
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''

SERIALS = ('BCES00510', 'BCES00799', 'BCUS98111', 'BCJS37001', 'BCAS25003', 'BCKS15003')


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def static_checks(source: Path) -> None:
    loader = (source / 'rpcs3/Emu/Cell/PPUModule.cpp').read_text('utf-8', 'surrogateescape')
    begin = loader.index('// REWINDBOX_GOW3_MLAA_100_916 (ios/IOSGow3MlaaPatch.h): one plan per known executable')
    block = loader[begin:loader.index('#endif\n', begin)]
    require(all(('title_id == "%s"' % serial) in block for serial in SERIALS) and block.count('title_id == "') == 6, 'the six God of War III serials, no other')
    # REWINDBOX_GOW3_MLAA_SAVESTATE_922 (test/rpcs3_gow3_mlaa_savestate922_test.py) extends the rule to restored
    # memory that lacks the guarded pair; this test keeps the fresh-boot rule of either form.
    require(('if (!ar && mlaa_policy && mlaa_plan)\n' in block or 'if ((!ar || mlaa_savestate_fix) && mlaa_policy && mlaa_plan)\n' in block)
            and block.count('mlaa_patch::apply(') == 1, 'a plan is applied at a fresh boot, under the setting')
    require('const mlaa_patch::plan* mlaa_plan = mlaa_patch::find(hash);' in block, 'the plan is chosen by the exact executable hash')
    require('_main.get_ptr<u8>(mlaa_plan->flag_address & ~3u, 4) && _main.get_ptr<u8>(mlaa_plan->call_address, 4)' in block,
            'a plan whose addresses are outside the image is dropped before any access')
    require('mlaa_state = ppu_state::refused_guard;' in block and 'ppu_loader.error("iOS God of War III PPU MLAA bypass refused' in block, 'a refusal is reported')
    require('PPU-19724fde' not in loader and 'PPU-4d5c5150' not in loader, 'the executable hashes live in the plan table only')
    spu = (source / 'rpcs3/Emu/Cell/lv2/sys_spu.cpp').read_text('utf-8', 'surrogateescape')
    require('{0x00005948, 0x40800094}' in spu and '{0x0000690c, 0x40800027}' in spu and 'SPU-530c255936b07b25467a58e24ceff5fd4e2960b7' in spu, 'the SPU half is unchanged')
    report = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text('utf-8', 'surrogateescape')
    require('ppu_patch=%u ppu_call_word=0x%08x savestate_patched=%d' in report, 'GOW3MLAA909 reports the plan, the replaced word and the savestate memory')
    header = (source / 'rpcs3/ios/IOSGow3MlaaReport.h').read_text()
    require('case ppu_state::refused_guard: return "refused_guard";' in header, 'the refusal has a name in the report')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--cxx', default='g++')
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    with tempfile.TemporaryDirectory(prefix='mlaa916-') as temporary:
        folder = Path(temporary)
        (folder / 'harness.cpp').write_text(HARNESS)
        results = []
        for name, flags in (('plain', ['-O2']), ('asan', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'])):
            if name == 'asan' and not (sys.platform.startswith('linux') and args.cxx.endswith('g++')):
                continue
            binary = folder / name
            build = subprocess.run([args.cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, '-I', str(source / 'rpcs3'), str(folder / 'harness.cpp'), '-o', str(binary)],
                                   capture_output=True, text=True)
            require(build.returncode == 0, name + ' does not build:\n' + build.stderr[-3000:])
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
            require(run.returncode == 0 and run.stdout.strip().endswith('"failures": 0}'), name + ':\n' + run.stdout[-2000:])
            results.append(run.stdout.strip().splitlines()[-1])
    previous = ''
    if args.previous:
        old = (args.previous / 'rpcs3/Emu/Cell/PPUModule.cpp').read_text('utf-8', 'surrogateescape')
        require('PPU-19724fde16a5b111b7b4d2a065f5dccaf8e01962' in old and '4d5c51503a81a327' not in old and
                not (args.previous / 'rpcs3/ios/IOSGow3MlaaPatch.h').exists(),
                'the previous Core is expected to know the 01.03 executable only')
        previous = '; the previous Core names the 01.03 executable only'
    print('PASS: God of War III MLAA bypass plans, 01.00 guarded (%s)%s' % (results[0], previous))
    return 0


if __name__ == '__main__':
    sys.exit(main())
