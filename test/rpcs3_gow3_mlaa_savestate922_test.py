#!/usr/bin/env python3
"""REWINDBOX_GOW3_MLAA_SAVESTATE_922, executed: the God of War III MLAA bypass on a resumed savestate.

Builds 721 and 723 (PIDs 47234 and 48447, executable 01.00): every session resumed from a savestate made without the
bypass reported COREPROF GOW3MLAA909 ppu=savestate_memory savestate_patched=0 and READBACK555 fault_read 72-107 per
5 s window (the 1280x720 colour buffer read back for MLAA every frame, 12-23 FPS); every fresh boot ppu=applied and
fault_read 0. The loader now applies the same guarded pair to the restored memory when it lacks it.

The driver extracts the loader's real decision statements from rpcs3/Emu/Cell/PPUModule.cpp (the savestate
condition and the condition of the single apply) and compiles them with the real rpcs3/ios/IOSGow3MlaaPatch.h over a
memory model, for fresh boots and savestates: unpatched 01.00 savestate memory gets exactly the pair (one byte, one
word) and then answers `present`; savestate memory that already holds the pair is not written; a guard failure
(flag byte 0x37, or a word that is not a call) writes nothing; the unguarded 01.03 plan is never written into a
savestate; policy off or another executable writes nothing; a fresh boot behaves as in Core 921. Negative control,
always run: the savestate condition without its `guarded` term must be caught (it writes the 01.03 pair into a
savestate). Host behaviour only: no frame rate is inferred.

    python3 test/rpcs3_gow3_mlaa_savestate922_test.py --source CORE [--cxx g++]
"""
from __future__ import annotations

import argparse
import re
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

namespace mlaa_patch = rpcs3::ios::gow3_mlaa_patch;
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }

struct memory
{
	std::map<std::uint32_t, std::uint8_t> bytes;
	std::vector<std::uint32_t> wrote;
	std::uint32_t r32(std::uint32_t a) { return std::uint32_t{bytes[a]} << 24 | std::uint32_t{bytes[a + 1]} << 16 | std::uint32_t{bytes[a + 2]} << 8 | bytes[a + 3]; }
	void w32(std::uint32_t a, std::uint32_t v) { bytes[a] = v >> 24; bytes[a + 1] = v >> 16; bytes[a + 2] = v >> 8; bytes[a + 3] = v; }
};

static memory image(std::uint32_t call_address, std::uint32_t call_word, std::uint8_t flag)
{
	memory m;
	m.w32(call_address, call_word);
	m.w32(0x52bf2c, 0x11223300u | flag);
	return m;
}

// The loader's decision, with the statements copied from PPUModule.cpp by the driver.
static bool loader(memory& m, const mlaa_patch::plan* mlaa_plan, bool ar_present, bool mlaa_policy)
{
	const void* ar = ar_present ? &m : nullptr;
	const auto mlaa_read8 = [&](std::uint32_t address) { return m.bytes[address]; };
	const auto mlaa_read32 = [&](std::uint32_t address) { return m.r32(address); };
	@SAVESTATE_FIX@
	if (@APPLY_CONDITION@)
	{
		const mlaa_patch::result r = mlaa_patch::apply(*mlaa_plan, mlaa_read8, mlaa_read32,
			[&](std::uint32_t a, std::uint8_t v) { m.bytes[a] = v; }, [&](std::uint32_t a, std::uint32_t v) { m.w32(a, v); },
			[&](std::uint32_t a) { m.wrote.push_back(a); });
		return r.what == mlaa_patch::outcome::applied;
	}
	return false;
}

int main()
{
	const mlaa_patch::plan* v100 = mlaa_patch::find("PPU-4d5c51503a81a327c2a99427390a395b8dcb3767");
	const mlaa_patch::plan* v103 = mlaa_patch::find("PPU-19724fde16a5b111b7b4d2a065f5dccaf8e01962");
	const auto present = [](memory& m, const mlaa_patch::plan& p) { return mlaa_patch::present(p, [&](std::uint32_t a) { return m.bytes[a]; }, [&](std::uint32_t a) { return m.r32(a); }); };
	{ // the build 723 case: a savestate of an unpatched 01.00 boot, MLAA flag set
		memory m = image(0x231248, 0x4bfff8d1, 1);
		check(!present(m, *v100), "the restored memory lacks the pair");
		check(loader(m, v100, true, true), "the pair is applied to the restored memory");
		check(present(m, *v100) && m.wrote == std::vector<std::uint32_t>({0x52bf2f, 0x231248}), "exactly the flag byte and the call word");
		check(m.r32(0x52bf2c) == 0x11223300u, "the other bytes of the flag word are kept");
		memory again = m; again.wrote.clear();
		check(!loader(again, v100, true, true) && again.wrote.empty(), "a savestate of that patched session is not written again");
	}
	{ // a savestate made after the game cleared its own flag: only the call changes
		memory m = image(0x231248, 0x4bfff8d1, 0);
		check(loader(m, v100, true, true) && m.wrote == std::vector<std::uint32_t>({0x231248}), "flag 0: the call alone");
	}
	{ // guard failures in restored memory write nothing
		memory flag = image(0x231248, 0x4bfff8d1, 0x37);
		const auto before = flag.bytes;
		check(!loader(flag, v100, true, true) && flag.bytes == before, "a flag byte of 0x37 is refused");
		memory word = image(0x231248, 0x7c0802a6, 1);
		const auto before2 = word.bytes;
		check(!loader(word, v100, true, true) && word.bytes == before2, "a word that is not a relative call is refused");
	}
	{ // 01.03 (unguarded, as delivered): never written into a savestate; a fresh boot keeps its behaviour
		memory m = image(0x23137c, 0x4bfff8d1, 1);
		const auto before = m.bytes;
		check(!loader(m, v103, true, true) && m.bytes == before, "the unguarded 01.03 pair is not written into a savestate");
		memory fresh = image(0x23137c, 0x4bfff8d1, 1);
		check(loader(fresh, v103, false, true) && fresh.r32(0x52bf2c) == 0 && fresh.r32(0x23137c) == mlaa_patch::nop, "01.03 fresh boot unchanged");
	}
	{ // policy off, another executable, fresh boot
		memory off = image(0x231248, 0x4bfff8d1, 1);
		const auto before = off.bytes;
		check(!loader(off, v100, true, false) && off.bytes == before, "setting Disabled: nothing on a savestate");
		memory fresh = image(0x231248, 0x4bfff8d1, 1);
		check(loader(fresh, v100, false, true) && present(fresh, *v100), "01.00 fresh boot unchanged");
		memory none = image(0x231248, 0x4bfff8d1, 1);
		check(!loader(none, nullptr, true, true), "no plan: nothing");
	}
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


SANITIZE = True


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def statements(source: Path, mutation: str | None):
    loader = (source / 'rpcs3/Emu/Cell/PPUModule.cpp').read_text('utf-8', 'surrogateescape')
    fix = re.search(r'const bool mlaa_savestate_fix = [^;]+;', loader, re.S)
    cond = re.search(r'if \(((?:\(!ar \|\| mlaa_savestate_fix\)|!ar) && mlaa_policy && mlaa_plan)\)\n', loader)
    require(fix and cond, 'the loader holds the 922 savestate condition and the apply condition')
    require(loader.count('mlaa_savestate_fix') == 2 and loader.count('mlaa_patch::apply(') == 1, 'one savestate condition, one apply')
    require('mlaa_state = ppu_state::savestate_applied;' in loader, 'a savestate application is reported apart')
    header = (source / 'rpcs3/ios/IOSGow3MlaaReport.h').read_text()
    require('case ppu_state::savestate_applied: return "savestate_applied";' in header, 'the report names it')
    text = fix.group(0)
    if mutation == 'ignore_guard':
        text = text.replace(' && mlaa_plan->guarded', '')
        require(text != fix.group(0), 'mutation applied')
    return text, cond.group(1)


def run(source: Path, cxx: str, mutation: str | None) -> tuple[int, str]:
    fix, cond = statements(source, mutation)
    with tempfile.TemporaryDirectory(prefix='mlaa922-') as temporary:
        folder = Path(temporary)
        (folder / 'harness.cpp').write_text(HARNESS.replace('@SAVESTATE_FIX@', fix).replace('@APPLY_CONDITION@', cond))
        flags = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'] if SANITIZE and Path(cxx).name.startswith('g++') and sys.platform.startswith('linux') else ['-O2']
        binary = folder / 'harness'
        build = subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, '-I', str(source / 'rpcs3'), str(folder / 'harness.cpp'), '-o', str(binary)],
                               capture_output=True, text=True)
        require(build.returncode == 0, 'harness does not build:\n' + build.stderr[-3000:])
        done = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true', help='plain -O2 build (the Core 922 driver passes it with clang)')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    global SANITIZE
    SANITIZE = not args.no_sanitizers
    source = args.source.resolve()
    code, out = run(source, args.cxx, None)
    require(code == 0 and out.strip().endswith('"failures": 0}'), 'candidate:\n' + out[-2000:])
    mcode, mout = run(source, args.cxx, 'ignore_guard')
    require(mcode != 0 and 'unguarded 01.03 pair is not written into a savestate' in mout, 'the ignore_guard mutation is not caught:\n' + mout[-1500:])
    if args.report:
        import json
        args.report.write_text(json.dumps({'passed': True, 'result': out.strip().splitlines()[-1], 'mutation': 'ignore_guard caught'}) + '\n')
    print('PASS: God of War III MLAA bypass on resumed savestates (%s); mutation ignore_guard caught' % out.strip().splitlines()[-1])
    return 0


if __name__ == '__main__':
    sys.exit(main())
