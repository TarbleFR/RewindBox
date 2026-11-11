#!/usr/bin/env python3
"""REWINDBOX_GOW3_MLAA_SAVESTATE_UNTOUCHED_929, executed: the restored memory of a savestate is never patched.

Core 922 (REWINDBOX_GOW3_MLAA_SAVESTATE_922) wrote the God of War III MLAA bypass pair into the restored memory of a
savestate made without it. Builds 724 and 725 (PIDs 50194 and 52378) resumed the 2,098,179,072-byte savestate that
build 723 (PID 48721) resumed: the picture broke at the first pause menu, on resumed sessions only (maintainer,
11 November 2026); build 723 left that memory as it was and no defect was reported. Upstream never applies an
executable patch to a savestate (PPUModule.cpp: patch_engine::apply receives no hash when one is restored). Core 929
returns to that rule: the pair is written at a fresh boot only.

The driver extracts the loader's real apply condition from rpcs3/Emu/Cell/PPUModule.cpp and compiles it with the real
rpcs3/ios/IOSGow3MlaaPatch.h over a memory model: the restored memory of a savestate, with or without the pair, guard
passing or failing, 01.00 or 01.03, is left byte for byte; a fresh boot writes exactly what Core 921 wrote. Negative
control, always run: the Core 922 statements put back into the harness must be caught (they write the restored
memory). Host behaviour only: no frame rate and no picture is inferred.

    python3 test/rpcs3_gow3_mlaa_savestate929_test.py --source CORE [--cxx g++]
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
	{ // the builds 723 to 725 case: a savestate of an unpatched 01.00 boot, MLAA flag set
		memory m = image(0x231248, 0x4bfff8d1, 1);
		const auto before = m.bytes;
		check(!present(m, *v100), "the restored memory lacks the pair");
		check(!loader(m, v100, true, true), "nothing is applied to the restored memory of a savestate");
		check(m.bytes == before && m.wrote.empty(), "the restored memory of a savestate is left byte for byte");
	}
	{ // a savestate made after a fresh boot with the bypass: it already holds the pair and stays as it is
		memory m = image(0x231248, 0x4bfff8d1, 1);
		check(loader(m, v100, false, true) && present(m, *v100), "the fresh boot applies the pair");
		memory resumed = m; resumed.wrote.clear();
		const auto before = resumed.bytes;
		check(!loader(resumed, v100, true, true) && resumed.bytes == before && present(resumed, *v100), "a patched savestate resumes as it was saved");
	}
	{ // a savestate whose game cleared its own flag: still not written
		memory m = image(0x231248, 0x4bfff8d1, 0);
		const auto before = m.bytes;
		check(!loader(m, v100, true, true) && m.bytes == before, "flag 0 in a savestate: nothing written");
	}
	{ // content the guard refuses: nothing written on a savestate or a fresh boot
		memory flag = image(0x231248, 0x4bfff8d1, 0x37);
		const auto before = flag.bytes;
		check(!loader(flag, v100, true, true) && flag.bytes == before, "flag byte 0x37 in a savestate: nothing");
		memory fresh = image(0x231248, 0x4bfff8d1, 0x37);
		const auto before2 = fresh.bytes;
		check(!loader(fresh, v100, false, true) && fresh.bytes == before2, "flag byte 0x37 at a fresh boot is refused");
	}
	{ // 01.03 (unguarded, as delivered): never written into a savestate; fresh boot unchanged
		memory m = image(0x23137c, 0x4bfff8d1, 1);
		const auto before = m.bytes;
		check(!loader(m, v103, true, true) && m.bytes == before, "the 01.03 pair is not written into a savestate");
		memory fresh = image(0x23137c, 0x4bfff8d1, 1);
		check(loader(fresh, v103, false, true) && fresh.r32(0x52bf2c) == 0 && fresh.r32(0x23137c) == mlaa_patch::nop, "01.03 fresh boot unchanged");
	}
	{ // fresh boot of 01.00: exactly the flag byte and the call word, as in Core 921
		memory fresh = image(0x231248, 0x4bfff8d1, 1);
		check(loader(fresh, v100, false, true) && fresh.wrote == std::vector<std::uint32_t>({0x52bf2f, 0x231248}) &&
			fresh.r32(0x52bf2c) == 0x11223300u, "01.00 fresh boot: the flag byte and the call word only");
	}
	{ // setting off, no plan
		memory off = image(0x231248, 0x4bfff8d1, 1);
		const auto before = off.bytes;
		check(!loader(off, v100, false, false) && off.bytes == before, "setting Disabled: nothing at a fresh boot");
		memory none = image(0x231248, 0x4bfff8d1, 1);
		check(!loader(none, nullptr, false, true), "no plan: nothing");
	}
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


SANITIZE = True
CORE922_FIX = ('const bool mlaa_savestate_fix = ar && mlaa_policy && mlaa_plan && mlaa_plan->guarded &&\n'
               '\t\t\t!mlaa_patch::present(*mlaa_plan, mlaa_read8, mlaa_read32);')
CORE922_CONDITION = '(!ar || mlaa_savestate_fix) && mlaa_policy && mlaa_plan'


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def statements(source: Path, mutation: str | None):
    loader = (source / 'rpcs3/Emu/Cell/PPUModule.cpp').read_text('utf-8', 'surrogateescape')
    require('REWINDBOX_GOW3_MLAA_SAVESTATE_UNTOUCHED_929' in loader, 'the loader carries the Core 929 rule')
    require('mlaa_savestate_fix' not in loader and 'ppu_state::savestate_applied' not in loader and 'restored savestate memory' not in loader,
            'no savestate application is left in the loader')
    conditions = re.findall(r'if \(([^\n]*mlaa_policy && mlaa_plan)\)\n', loader)
    require(conditions == ['!ar && mlaa_policy && mlaa_plan'], 'one apply condition, fresh boots only: %r' % conditions)
    require(loader.count('mlaa_patch::apply(') == 1, 'one apply')
    require('ppu_state mlaa_state = !mlaa_policy ? ppu_state::policy_off : ar ? ppu_state::savestate :' in loader,
            'a resumed savestate is reported as savestate_memory')
    require('rpcs3::ios::gow3_mlaa::savestate_patched.store(ar && mlaa_plan ? (mlaa_patch::present(' in loader,
            'the report still says whether the savestate holds the pair')
    header = (source / 'rpcs3/ios/IOSGow3MlaaReport.h').read_text()
    require('case ppu_state::savestate: return "savestate_memory";' in header, 'the report names a resumed savestate')
    if mutation == 'core922':
        return CORE922_FIX, CORE922_CONDITION
    return '', conditions[0]


def run(source: Path, cxx: str, mutation: str | None) -> tuple[int, str]:
    fix, cond = statements(source, mutation)
    with tempfile.TemporaryDirectory(prefix='mlaa929-') as temporary:
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
    parser.add_argument('--no-sanitizers', action='store_true', help='plain -O2 build')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    global SANITIZE
    SANITIZE = not args.no_sanitizers
    source = args.source.resolve()
    code, out = run(source, args.cxx, None)
    require(code == 0 and out.strip().endswith('"failures": 0}'), 'candidate:\n' + out[-2000:])
    mcode, mout = run(source, args.cxx, 'core922')
    require(mcode != 0 and 'the restored memory of a savestate is left byte for byte' in mout,
            'the Core 922 rule is not caught:\n' + mout[-1500:])
    if args.report:
        import json
        args.report.write_text(json.dumps({'passed': True, 'result': out.strip().splitlines()[-1], 'control': 'Core 922 rule caught'}) + '\n')
    print('PASS: God of War III savestate memory left as saved (%s); the Core 922 rule is caught' % out.strip().splitlines()[-1])
    return 0


if __name__ == '__main__':
    sys.exit(main())
